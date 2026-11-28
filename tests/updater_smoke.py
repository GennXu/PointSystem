"""Real EXE update and rollback against isolated test data, never production data."""
import http.cookiejar
import json
import logging
import os
import shutil
import socket
import ssl
import sys
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.app import initialize  # noqa: E402
from server.https_setup import configure_https  # noqa: E402
from updater.core import Runtime, UpdateError, perform_update, read_plan, sha256  # noqa: E402
from updater.windows import target_processes  # noqa: E402


def main():
    os.environ.pop('QRPOINT_DATABASE_URL', None)
    os.environ.pop('QRPOINT_DATA', None)
    folder = ROOT / 'work' / ('updater-smoke-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    app, data = folder / 'app', folder / 'data'
    shutil.copytree(ROOT / 'output/windows/QRPointServer', app)
    (app / '_internal/old-ui-marker.txt').write_text('original runtime')
    initialize(data, 'test-admin', 'Only-For-Tests-9284')
    logging.shutdown()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    (data / 'config.json').write_text(json.dumps({'allow_sqlite_development': True, 'port': port}))
    configure_https(data, ['127.0.0.1'], [], 'Updater-Test-CA-9284', port)
    plan = read_plan(app, data)
    protected = dict(plan['protected'])
    payload = ROOT / 'work/updater-payload/payload.zip'
    manifest = json.loads((payload.parent / 'manifest.json').read_text())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(data / 'https/root-ca.pem'))),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    base = f'https://127.0.0.1:{port}/api'
    csrf = ''

    def request(path, body=None):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json', 'X-CSRF-Token': csrf})
        with opener.open(req, timeout=5) as result:
            return json.loads(result.read())

    with (folder / 'initial-server.log').open('a', encoding='utf-8') as log:
        runtime = Runtime(plan, [])
        process = runtime.start(log)
        try:
            assert runtime.ready(process), 'Original test server could not start'
            csrf = request('/auth/login', {'username': 'test-admin', 'password': 'Only-For-Tests-9284'})['csrf']
            member = request('/users', {'member_code': 'UPDATE-TEST', 'display_name': '更新保留測試會員'})
            request('/transactions/grant', {'user_id': member['id'], 'amount': 1250.5, 'reason': '更新前交易',
                    'station_id': 'TEST', 'idempotency_key': str(uuid.uuid4())})
            running = target_processes(app.resolve(), data.resolve())
            assert len(running) == 1
            result = perform_update(plan, payload, manifest, Runtime(plan, running), print)
            assert (Path(result['backup']) / '_internal/old-ui-marker.txt').is_file()
            assert not (app / '_internal/old-ui-marker.txt').exists()
            assert request('/users/' + member['id'])['balance'] == 1250.5
            assert len(request('/transactions')) == 1
            assert all(sha256(path) == value for path, value in protected.items())
            assert request('/redeem-templates') == []
            print('PASS: real EXE update, normal stop/restart, original account, pinned HTTPS, preserved session/member/ledger/config/keys')

            class FailedNewRuntime(Runtime):
                starts = 0

                def start(self, output):
                    self.starts += 1
                    return super().start(output)

                def ready(self, candidate):
                    ready = super().ready(candidate)
                    return ready and self.starts > 1

            marker = app / '_internal/rollback-marker.txt'
            marker.write_text('must survive failed update')
            running = target_processes(app.resolve(), data.resolve())
            try:
                perform_update(plan, payload, manifest, FailedNewRuntime(plan, running), print)
                raise AssertionError('Expected rollback')
            except UpdateError as error:
                assert '已還原原程式' in str(error), str(error)
            assert marker.read_text() == 'must survive failed update'
            assert request('/users/' + member['id'])['balance'] == 1250.5
            assert len(request('/transactions')) == 1
            assert all(sha256(path) == value for path, value in protected.items())
            print('PASS: injected startup-check failure restored original EXE/runtime and restarted original service')
        finally:
            Runtime(plan, target_processes(app.resolve(), data.resolve())).stop()
            if process.poll() is None:
                process.wait(timeout=10)


if __name__ == '__main__':
    main()
