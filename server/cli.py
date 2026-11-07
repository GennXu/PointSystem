import argparse
import ctypes
import getpass
import json
import os
import socket
import sqlite3
import sys
import time
from pathlib import Path

import uvicorn

from server.app import initialize, ph
from server.database import snapshot


class InstanceLock:
    def __init__(self, data):
        self.path = data / 'server.lock'

    def __enter__(self):
        self.file = self.path.open('a+b')
        self.file.seek(0)
        self.file.write(b'0')
        self.file.flush()
        self.file.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return self

    def __exit__(self, *_):
        self.file.close()


def restore(data, source, username, password):
    # The server holds the same OS lock throughout its lifespan.
    with InstanceLock(data):
        db = data / 'points.db'
        with sqlite3.connect(db) as current:
            row = current.execute("SELECT password_hash FROM operators WHERE username=? AND role='Admin' AND status='active'", (username,)).fetchone()
            if not row or not ph.verify(row[0], password):
                raise RuntimeError('管理員驗證失敗')
            current_version = current.execute('SELECT version_num FROM alembic_version').fetchone()
        with sqlite3.connect(f'{Path(source).resolve().as_uri()}?mode=ro', uri=True) as candidate:
            if candidate.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('備份完整性檢查失敗')
            if candidate.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('備份外鍵檢查失敗')
            if candidate.execute('SELECT version_num FROM alembic_version').fetchone() != current_version:
                raise RuntimeError('schema 版本不相容')
            from cryptography.fernet import Fernet
            cipher = Fernet((data / 'secret.key').read_bytes())
            for record in candidate.execute("SELECT token_cipher FROM qr_credentials WHERE status='active'"):
                cipher.decrypt(record[0].encode())
        (data / 'backups').mkdir(exist_ok=True)
        snapshot(db, data / 'backups' / f'pre-restore-{time.time_ns()}.db')
        snapshot(source, db)
        with sqlite3.connect(db) as restored:
            restored.execute('DELETE FROM sessions')
            restored.execute('DELETE FROM portal_sessions')
            if restored.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('還原後完整性檢查失敗')


def main():
    parser = argparse.ArgumentParser(description='QR Point LAN server')
    parser.add_argument('command', nargs='?', default='serve', choices=['serve', 'init', 'backup', 'restore', 'check', 'stop'])
    default_data = str(Path(os.environ.get('PROGRAMDATA', '.')) / 'QRPointSystem')
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\QRPointSystem', 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                default_data = winreg.QueryValueEx(key, 'DataDir')[0]
        except OSError:
            pass
    parser.add_argument('--data-dir', default=os.environ.get('QRPOINT_DATA', default_data))
    parser.add_argument('--port', type=int)
    parser.add_argument('--file')
    args = parser.parse_args()
    data = Path(args.data_dir).resolve()
    data.mkdir(parents=True, exist_ok=True)
    config_file = data / 'config.json'
    config = json.loads(config_file.read_text(encoding='utf-8-sig')) if config_file.exists() else {}
    if bool(config.get('tls_certfile')) != bool(config.get('tls_keyfile')):
        raise RuntimeError('HTTPS 憑證與私密金鑰必須同時設定')
    scheme = 'https' if config.get('tls_certfile') else 'http'
    if args.command == 'init':
        with InstanceLock(data):
            username = input('管理員帳號： ').strip()
            password = getpass.getpass('密碼（至少 12 字元，含英文字母與數字）： ')
            if password != getpass.getpass('再次輸入密碼： '):
                raise RuntimeError('密碼不一致')
            initialize(data, username, password)
        print('管理員已建立，請啟動伺服器。')
    elif args.command == 'restore':
        if not args.file:
            parser.error('restore requires --file')
        restore(data, args.file, input('管理員帳號： '), getpass.getpass('管理員密碼： '))
        print('還原已完成並驗證，請重新啟動伺服器。')
    elif args.command == 'backup':
        backup_dir = Path(config.get('backup_dir', str(data / 'backups')))
        backup_dir.mkdir(parents=True, exist_ok=True)
        print(snapshot(data / 'points.db', backup_dir / f'manual-{time.time_ns()}.db'))
    elif args.command == 'check':
        with sqlite3.connect(data / 'points.db') as db:
            print('integrity_check:', db.execute('PRAGMA integrity_check').fetchone()[0])
            print('foreign_key_check:', db.execute('PRAGMA foreign_key_check').fetchall())
        print('區域網路位址候選：', socket.gethostbyname_ex(socket.gethostname())[2])
        print('連接埠：', args.port or config.get('port', 8080))
    elif args.command == 'stop':
        (data / 'stop.request').write_text('stop', encoding='ascii')
        print('已要求正常停止服務，請等待伺服器退出後再還原。')
    else:
        with InstanceLock(data):
            from server.app import create_app
            root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
            app = create_app(data, root / 'frontend' / 'dist', bool(config.get('tls_certfile')) or config.get('secure_cookie', False), config.get('backup_dir'))
            with app.state.engine.connect() as c:
                from sqlalchemy import text
                if not c.execute(text('SELECT count(*) FROM operators')).scalar():
                    raise RuntimeError('請先在本機執行 QRPointServer.exe init 建立管理員')
            stop_file = data / 'stop.request'
            stop_file.unlink(missing_ok=True)
            server = uvicorn.Server(uvicorn.Config(app, host='0.0.0.0', port=args.port or config.get('port', 8080), http='httptools', access_log=False, use_colors=False, ssl_certfile=config.get('tls_certfile'), ssl_keyfile=config.get('tls_keyfile')))
            import threading
            done = threading.Event()

            def watcher():
                while not done.wait(0.5):
                    if stop_file.exists():
                        server.should_exit = True
                        return
            threading.Thread(target=watcher, daemon=True).start()
            if os.name == 'nt':
                # Console close / Windows shutdown: request graceful uvicorn exit.
                callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

                @callback_type
                def console_handler(event):
                    if event in (0, 1, 2, 5, 6):
                        server.should_exit = True
                        done.wait(4)
                        return True
                    return False
                ctypes.windll.kernel32.SetConsoleCtrlHandler(console_handler, True)
            try:
                print('HTTPS 加密服務' if scheme == 'https' else 'HTTP 未加密，請僅在可信任的隔離區域網路使用。', '連接埠：', args.port or config.get('port', 8080))
                for address in socket.gethostbyname_ex(socket.gethostname())[2]:
                    if not address.startswith('127.'):
                        print(f'區域網路瀏覽網址：{scheme}://{address}:{args.port or config.get("port", 8080)}')
                server.run()
            finally:
                done.set()
                stop_file.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
