import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, event

MAX_POINTS = 9007199254740991
SCHEMA = '''
CREATE TABLE operators(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('Admin','Staff')), status TEXT NOT NULL CHECK(status IN ('active','disabled')), created_at TEXT NOT NULL, last_login_at TEXT);
CREATE TABLE users(id TEXT PRIMARY KEY, member_code TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','disabled')), balance INTEGER NOT NULL DEFAULT 0 CHECK(typeof(balance)='integer' AND balance BETWEEN 0 AND 9007199254740991), created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0);
CREATE TABLE qr_credentials(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), token_hash TEXT UNIQUE NOT NULL, token_cipher TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','revoked')), issued_at TEXT NOT NULL, revoked_at TEXT, expires_at TEXT);
CREATE UNIQUE INDEX one_active_qr ON qr_credentials(user_id) WHERE status='active';
CREATE TABLE transactions(id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id), operator_id TEXT NOT NULL REFERENCES operators(id), type TEXT NOT NULL CHECK(type IN ('GRANT','REDEEM','ADJUST')), delta INTEGER NOT NULL CHECK(typeof(delta)='integer'), balance_before INTEGER NOT NULL CHECK(balance_before>=0), balance_after INTEGER NOT NULL CHECK(balance_after>=0 AND balance_after<=9007199254740991), reason TEXT NOT NULL, station_id TEXT NOT NULL, created_at TEXT NOT NULL, CHECK(balance_after=balance_before+delta));
CREATE INDEX tx_user_time ON transactions(user_id,created_at);
CREATE INDEX tx_operator_time ON transactions(operator_id,created_at);
CREATE INDEX tx_type_time ON transactions(type,created_at);
CREATE TRIGGER tx_no_update BEFORE UPDATE ON transactions BEGIN SELECT RAISE(ABORT,'ledger is immutable'); END;
CREATE TRIGGER tx_no_delete BEFORE DELETE ON transactions BEGIN SELECT RAISE(ABORT,'ledger is immutable'); END;
CREATE TABLE settings(key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, operator_id TEXT NOT NULL REFERENCES operators(id), csrf TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE login_attempts(source TEXT PRIMARY KEY, count INTEGER NOT NULL, window_start REAL NOT NULL);
'''


def engine_for(path):
    engine = create_engine('sqlite:///' + str(path), connect_args={'check_same_thread': False, 'timeout': 15})

    @event.listens_for(engine, 'connect')
    def pragmas(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=15000')
        connection.execute('PRAGMA journal_mode=WAL')

    return engine


def migrate(path):
    from alembic import command
    from alembic.config import Config
    import sys
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    config = Config()
    config.set_main_option('script_location', str(root / 'migrations'))
    config.set_main_option('sqlalchemy.url', 'sqlite:///' + str(path).replace('%', '%%'))
    command.upgrade(config, 'head')


def snapshot(path, destination):
    with sqlite3.connect(path) as source, sqlite3.connect(destination) as target:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Backup integrity check failed')
    return str(destination)
