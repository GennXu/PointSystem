import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from updater.core import UpdateError, extract_payload, perform_update, read_plan


def fixture_install(tmp_path):
    app, data = tmp_path / 'app', tmp_path / 'data'
    app.mkdir()
    data.mkdir()
    (app / 'QRPointServer.exe').write_bytes(b'old exe')
    (app / '_internal').mkdir()
    (app / '_internal/old.dll').write_bytes(b'old runtime')
    (app / 'user-notes.txt').write_text('keep me')
    (data / 'config.json').write_text(json.dumps({'database_url': 'mssql+pyodbc://test', 'port': 8080}))
    (data / 'secret.key').write_bytes(b'original member secret')
    (data / 'points.db').write_bytes(b'never change user database')
    payload = tmp_path / 'payload.zip'
    members = {'QRPointServer.exe': b'new exe', '_internal/new.dll': b'new runtime',
               '_internal/frontend/dist/index.html': b'new UI'}
    with zipfile.ZipFile(payload, 'w') as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    manifest = {'archive_sha256': hashlib.sha256(payload.read_bytes()).hexdigest(),
                'files': {name: hashlib.sha256(value).hexdigest() for name, value in members.items()}}
    return app, data, payload, manifest


class FakeRuntime:
    def __init__(self, ready=True, preflight=True):
        self.running = [123]
        self.readiness, self.preflight_ok = ready, preflight
        self.starts, self.stops = 0, 0

    def preflight(self, staged):
        if not self.preflight_ok:
            raise UpdateError('SQL preflight failed')

    def stop(self, process=None):
        self.stops += 1

    def start(self, log):
        self.starts += 1
        return object()

    def ready(self, process):
        return self.readiness or self.starts > 1


def test_update_only_replaces_owned_runtime_and_preserves_data(tmp_path):
    app, data, payload, manifest = fixture_install(tmp_path)
    original = {p.name: p.read_bytes() for p in data.iterdir()}
    runtime = FakeRuntime()
    result = perform_update(read_plan(app, data), payload, manifest, runtime)
    assert (app / 'QRPointServer.exe').read_bytes() == b'new exe'
    assert (app / '_internal/new.dll').read_bytes() == b'new runtime'
    assert (Path(result['backup']) / 'QRPointServer.exe').read_bytes() == b'old exe'
    assert (Path(result['backup']) / '_internal/old.dll').read_bytes() == b'old runtime'
    assert (app / 'user-notes.txt').read_text() == 'keep me'
    assert all((data / name).read_bytes() == value for name, value in original.items())
    assert runtime.starts == runtime.stops == 1


def test_failed_start_restores_original_program(tmp_path):
    app, data, payload, manifest = fixture_install(tmp_path)
    runtime = FakeRuntime(ready=False)
    with pytest.raises(UpdateError, match='已還原原程式'):
        perform_update(read_plan(app, data), payload, manifest, runtime)
    assert (app / 'QRPointServer.exe').read_bytes() == b'old exe'
    assert (app / '_internal/old.dll').read_bytes() == b'old runtime'
    assert runtime.starts == 2


def test_preflight_failure_does_not_stop_or_replace_original(tmp_path):
    app, data, payload, manifest = fixture_install(tmp_path)
    runtime = FakeRuntime(preflight=False)
    with pytest.raises(UpdateError, match='SQL preflight'):
        perform_update(read_plan(app, data), payload, manifest, runtime)
    assert (app / 'QRPointServer.exe').read_bytes() == b'old exe'
    assert runtime.starts == runtime.stops == 0


def test_corrupt_payload_and_legacy_config_are_rejected(tmp_path):
    app, data, payload, manifest = fixture_install(tmp_path)
    payload.write_bytes(b'corrupt archive')
    runtime = FakeRuntime()
    with pytest.raises(UpdateError, match='校驗失敗'):
        perform_update(read_plan(app, data), payload, manifest, runtime)
    assert runtime.stops == 0
    (data / 'config.json').write_text('{}')
    with pytest.raises(UpdateError, match='SQL Express'):
        read_plan(app, data)


def test_payload_path_traversal_is_rejected(tmp_path):
    payload = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(payload, 'w') as archive:
        archive.writestr('../outside.txt', 'bad')
    manifest = {'archive_sha256': hashlib.sha256(payload.read_bytes()).hexdigest(),
                'files': {'../outside.txt': hashlib.sha256(b'bad').hexdigest()}}
    with pytest.raises(UpdateError, match='非預期路徑'):
        extract_payload(payload, manifest, tmp_path / 'staged')
    assert not (tmp_path / 'outside.txt').exists()


def test_data_or_certificates_inside_runtime_are_rejected(tmp_path):
    app, data, _, _ = fixture_install(tmp_path)
    (app / '_internal/cert.pem').write_text('do not replace')
    config = json.loads((data / 'config.json').read_text())
    config.update(tls_certfile=str(app / '_internal/cert.pem'), tls_keyfile=str(app / '_internal/cert.pem'))
    (data / 'config.json').write_text(json.dumps(config))
    with pytest.raises(UpdateError, match='位於 _internal'):
        read_plan(app, data)


@pytest.mark.skipif(os.name != 'nt', reason='Windows updater process discovery')
def test_windows_parameters_and_owner_are_preserved(tmp_path, monkeypatch):
    from updater import windows
    app, data, _, _ = fixture_install(tmp_path)
    command = subprocess.list2cmdline([str(app / 'QRPointServer.exe'), 'serve', '--data-dir', str(data), '--port', '9443'])
    process = {'pid': 123, 'path': str(app / 'QRPointServer.exe'), 'command': command, 'owner': windows.current_account()}
    monkeypatch.setattr(windows, 'processes', lambda: [process])
    assert windows.launch_options(process) == (data.resolve(), 9443)
    assert windows.target_processes(app.resolve(), data.resolve())[0]['port'] == 9443
    process['owner'] = 'OTHER\\Administrator'
    with pytest.raises(UpdateError, match='原 API 執行帳號'):
        windows.target_processes(app.resolve(), data.resolve())


def test_update_check_is_read_only_for_test_database(system):
    app, _, _, data = system
    app.state.engine.dispose()
    (data / 'config.json').write_text(json.dumps({'allow_sqlite_development': True}))
    original = {p.name: p.read_bytes() for p in (data / 'points.db', data / 'secret.key', data / 'config.json')}
    result = subprocess.run([sys.executable, '-m', 'server.cli', 'update-check', '--data-dir', str(data)],
                            capture_output=True, check=True)
    assert json.loads(result.stdout) == {'status': 'ok', 'schema': '0003'}
    assert all((data / name).read_bytes() == value for name, value in original.items())
