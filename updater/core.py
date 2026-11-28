import hashlib
import http.client
import json
import os
import re
import ssl
import subprocess
import time
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

OWNED = ('QRPointServer.exe', '_internal')


class UpdateError(RuntimeError):
    pass


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_child(parent, name):
    parent = Path(parent).resolve()
    path = parent / name
    if path.is_symlink() or path.resolve().parent != parent:
        raise UpdateError('程式路徑含重新導向或不在預期目錄內，已停止更新')
    if hasattr(path, 'is_junction') and path.is_junction():
        raise UpdateError('不支援 Junction 重新導向的程式目錄')
    return path


@contextmanager
def file_lock(path):
    with Path(path).open('a+b') as stream:
        stream.seek(0)
        if not stream.read(1):
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise UpdateError('程式或另一個更新工具仍在執行，請等待正常結束') from None
        yield


def read_plan(app, data, port=None):
    app, data = Path(app).resolve(), Path(data).resolve()
    if app == Path(app.anchor) or not (app / 'QRPointServer.exe').is_file():
        raise UpdateError('請選擇含 QRPointServer.exe 的既有程式資料夾')
    for name in OWNED:
        if not safe_child(app, name).exists():
            raise UpdateError('找不到完整的舊程式（需包含 _internal），不能自動更新')
    config_path = data / 'config.json'
    if not config_path.is_file() or not (data / 'secret.key').is_file():
        raise UpdateError('資料目錄必須含原本 config.json 與 secret.key；不會建立新資料庫')
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    for key in ('tls_certfile', 'tls_keyfile'):
        if config.get(key):
            path = Path(config[key])
            config[key] = str((app / path).resolve() if not path.is_absolute() else path.resolve())
    if not config.get('database_url', '').startswith('mssql+pyodbc://') and not config.get('allow_sqlite_development'):
        raise UpdateError('需先完成 SQL Express 部署並在 config.json 設定 database_url；本工具不移轉舊 SQLite')
    for protected in (data, *(Path(config[k]).resolve() for k in ('tls_certfile', 'tls_keyfile') if config.get(k))):
        if protected == app / '_internal' or app / '_internal' in protected.parents:
            raise UpdateError('資料或 HTTPS 憑證位於 _internal 內，請由管理員先調整，避免更新覆蓋')
    if bool(config.get('tls_certfile')) != bool(config.get('tls_keyfile')):
        raise UpdateError('HTTPS 憑證設定不完整，已停止更新')
    port = int(port if port is not None else config.get('port', 8080))
    if not 1 <= port <= 65535:
        raise UpdateError('Port 設定錯誤')
    protected_files = [config_path, data / 'secret.key']
    protected_files += [Path(config[k]).resolve() for k in ('tls_certfile', 'tls_keyfile') if config.get(k)]
    return {'app': app, 'data': data, 'port': port, 'config': config,
            'protected': {str(path): sha256(path) for path in protected_files}}


def verify_protected(plan):
    if any(sha256(path) != value for path, value in plan['protected'].items()):
        raise UpdateError('原設定、會員密鑰或 HTTPS 憑證在更新期間改變，請由管理員檢查')


def extract_payload(payload, manifest, destination):
    if sha256(payload) != manifest['archive_sha256']:
        raise UpdateError('更新檔校驗失敗，請重新取得完整更新檔')
    expected = manifest['files']
    with zipfile.ZipFile(payload) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())) or set(archive.namelist()) != set(expected):
            raise UpdateError('更新檔內容與清單不符')
        for entry in archive.infolist():
            name = PurePosixPath(entry.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in entry.filename or name.parts[0] not in OWNED:
                raise UpdateError('更新檔含非預期路徑')
            target = destination.joinpath(*name.parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise UpdateError('更新檔路徑越界')
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open('wb') as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            if sha256(target) != expected[entry.filename]:
                raise UpdateError('程式檔校驗失敗：' + entry.filename)
    if not (destination / 'QRPointServer.exe').is_file() or not (destination / '_internal/frontend/dist/index.html').is_file():
        raise UpdateError('更新程式不完整')


def health(plan, timeout=1):
    config = plan['config']
    if config.get('tls_certfile'):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        connection = http.client.HTTPSConnection('127.0.0.1', plan['port'], timeout=timeout, context=context)
    else:
        connection = http.client.HTTPConnection('127.0.0.1', plan['port'], timeout=timeout)
    try:
        connection.connect()
        if config.get('tls_certfile'):
            # Local-only readiness probe pins the exact configured leaf certificate.
            # It does not modify Windows/phone trust or bypass identity verification.
            pem = Path(config['tls_certfile']).read_text(encoding='ascii')
            leaf = re.search(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', pem, re.S)
            if not leaf or connection.sock.getpeercert(binary_form=True) != ssl.PEM_cert_to_DER_cert(leaf[0]):
                return False
        connection.request('GET', '/api/health', headers={'Connection': 'close'})
        response = connection.getresponse()
        return response.status == 200 and json.loads(response.read(65536)) == {'status': 'ok'}
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        connection.close()


class Runtime:
    def __init__(self, plan, running):
        self.plan, self.running = plan, running

    def preflight(self, staged):
        command = [str(staged / 'QRPointServer.exe'), 'update-check', '--data-dir', str(self.plan['data'])]
        result = subprocess.run(command, cwd=self.plan['app'], capture_output=True, timeout=40,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode != 0:
            raise UpdateError('新版啟動前檢查失敗，舊程式未更動。請確認執行帳號、SQL 權限與憑證；檢查輸出：\n' +
                              result.stderr.decode('utf-8', errors='replace')[-2500:])

    def stop(self, process=None):
        from updater.windows import wait_process
        ids = [process.pid] if process is not None else [p['pid'] for p in self.running]
        if ids:
            (self.plan['data'] / 'stop.request').write_text('stop', encoding='ascii')
            for pid in ids:
                if not wait_process(pid, 45):
                    raise UpdateError('服務未能正常停止；沒有強制結束程序，請管理員處理')

    def start(self, log):
        return subprocess.Popen([str(self.plan['app'] / 'QRPointServer.exe'), 'serve',
                                 '--data-dir', str(self.plan['data']), '--port', str(self.plan['port'])],
                                cwd=self.plan['app'], stdout=log, stderr=log,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def ready(self, process):
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return False
            if health(self.plan):
                time.sleep(1)
                return process.poll() is None and health(self.plan)
            time.sleep(0.4)
        return False


def perform_update(plan, payload, manifest, runtime, emit=lambda message: None):
    app = plan['app']
    updates = safe_child(app, '.point-updates')
    updates.mkdir(exist_ok=True)
    with file_lock(updates / 'update.lock'):
        work = updates / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
        staged, backup, failed = work / 'new', work / 'backup', work / 'failed'
        for path in (staged, backup, failed):
            path.mkdir(parents=True)
        with (work / 'update.log').open('a', encoding='utf-8') as log:
            def report(message):
                log.write(message + '\n')
                log.flush()
                emit(message)
            report('校驗並解開更新程式…')
            extract_payload(payload, manifest, staged)
            report('檢查新版程式、SQL 與 HTTPS 設定（不變更資料庫）…')
            runtime.preflight(staged)
            verify_protected(plan)
            report('正常停止原服務…')
            runtime.stop()
            backed_up, installed = [], []
            process = None
            try:
                with file_lock(plan['data'] / 'server.lock'):
                    verify_protected(plan)
                    for name in OWNED:
                        os.replace(safe_child(app, name), safe_child(backup, name))
                        backed_up.append(name)
                    report('原程式已保留，正在安裝新版…')
                    for name in OWNED:
                        os.replace(safe_child(staged, name), safe_child(app, name))
                        installed.append(name)
                    verify_protected(plan)
                report('啟動新版並檢查 API…')
                process = runtime.start(log)
                if not runtime.ready(process):
                    raise UpdateError('新版未通過啟動檢查')
                verify_protected(plan)
                report('更新完成，服務已在背景啟動。')
                return {'backup': str(backup), 'log': str(work / 'update.log')}
            except Exception as error:
                report('更新失敗，嘗試還原原程式…')
                try:
                    if process is not None:
                        runtime.stop(process)
                    with file_lock(plan['data'] / 'server.lock'):
                        for name in reversed(installed):
                            os.replace(safe_child(app, name), safe_child(failed, name))
                        for name in reversed(backed_up):
                            os.replace(safe_child(backup, name), safe_child(app, name))
                    if runtime.running:
                        old = runtime.start(log)
                        if not runtime.ready(old):
                            raise UpdateError('檔案已還原，但原服務無法自動啟動')
                except Exception as recovery_error:
                    raise UpdateError(f'需管理員處理：{recovery_error}\n原程式備份／記錄：{work}') from error
                raise UpdateError(f'{error}\n已還原原程式，更新工具未覆寫設定與會員密鑰。\n記錄：{work}') from error
