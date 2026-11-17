"""Non-destructive SQLite to SQL Express transfer into an empty database."""
import hashlib
import json
import sqlite3
import tempfile
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import select

from server.database import migrate, snapshot
from server.sqlserver import metadata, write_transaction

TABLES = ('operators', 'users', 'qr_credentials', 'transactions', 'settings')


def canonical(records):
    def value(item):
        if isinstance(item, (int, float, Decimal)):
            return str(Decimal(str(item)).normalize())
        return item
    encoded = [json.dumps({k: value(v) for k, v in row.items()}, sort_keys=True, ensure_ascii=False) for row in records]
    return hashlib.sha256('\n'.join(sorted(encoded)).encode()).hexdigest()


def transfer(source, key_file, data, engine):
    source, data = Path(source).resolve(), Path(data).resolve()
    if not source.is_file():
        raise RuntimeError('找不到來源 SQLite 檔案')
    key = Path(key_file).read_bytes()
    cipher = Fernet(key)
    destination = data / 'secret.key'
    if destination.exists() and destination.read_bytes() != key:
        raise RuntimeError('目標 secret.key 不同，拒絕覆寫；請選擇正確資料目錄')
    created_key = False
    # Upgrade only a temporary snapshot. The original DB and its schema are untouched.
    with tempfile.TemporaryDirectory(prefix='qrpoint-transfer-') as folder:
        working = Path(folder) / 'source.db'
        snapshot(source, working)
        migrate(working)
        with closing(sqlite3.connect(working)) as old:
            old.row_factory = sqlite3.Row
            if old.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or old.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('來源資料庫完整性檢查失敗')
            records = {name: [dict(r) for r in old.execute('SELECT * FROM ' + name)] for name in TABLES}
        for qr in records['qr_credentials']:
            token = cipher.decrypt(qr['token_cipher'].encode())
            if hashlib.sha256(token).hexdigest() != qr['token_hash']:
                raise RuntimeError('QR 密鑰或雜湊不符')
        totals = {r['id']: Decimal(0) for r in records['users']}
        for tx in records['transactions']:
            delta = Decimal(str(tx['delta']))
            if Decimal(str(tx['balance_before'])) + delta != Decimal(str(tx['balance_after'])):
                raise RuntimeError('帳本前後餘額不一致')
            totals[tx['user_id']] += delta
        if any(totals[r['id']] != Decimal(str(r['balance'])) for r in records['users']):
            raise RuntimeError('帳本總額與會員餘額不一致')
        try:
            with write_transaction(engine) as connection:
                for name in (*TABLES, 'sessions', 'portal_sessions', 'login_attempts'):
                    if connection.execute(select(metadata.tables[name]).limit(1)).first():
                        raise RuntimeError('目標資料庫非空白，拒絕合併或覆寫')
                report = {}
                for name in TABLES:
                    table = metadata.tables[name]
                    for record in records[name]:
                        connection.execute(table.insert().values(**record))
                    copied = [dict(r) for r in connection.execute(select(table)).mappings()]
                    checksum = canonical(records[name])
                    if len(copied) != len(records[name]) or canonical(copied) != checksum:
                        raise RuntimeError('移轉驗證失敗：' + name)
                    report[name] = {'count': len(copied), 'sha256': checksum}
                if not destination.exists():
                    with destination.open('xb') as output:
                        output.write(key)
                    created_key = True
            return report
        except BaseException:
            if created_key:
                destination.unlink()
            raise
