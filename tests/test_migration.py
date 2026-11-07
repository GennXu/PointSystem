import sqlite3
import uuid

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine

from server.app import create_app, digest, ph
from server.database import SCHEMA


def legacy_database(data):
    data.mkdir(exist_ok=True)
    uid, oid, qid, txid = [str(uuid.uuid4()) for _ in range(4)]
    key = Fernet.generate_key()
    (data / 'secret.key').write_bytes(key)
    token = 'a' * 43
    with sqlite3.connect(data / 'points.db') as db:
        db.executescript(SCHEMA)
        db.execute('CREATE TABLE alembic_version(version_num TEXT PRIMARY KEY)')
        db.execute("INSERT INTO alembic_version VALUES('0001')")
        db.execute("INSERT INTO operators VALUES(?,?,?,'Admin','active',?,NULL)", (oid, 'legacy-admin', ph.hash('Legacy-Test-9284'), '2026-10-27T00:00:00+00:00'))
        db.execute("INSERT INTO users VALUES(?,? ,?,'active',500,?,?,1)", (uid, 'LEGACY-001', '升級測試會員', '2026-10-27T00:00:00+00:00', '2026-10-27T00:00:00+00:00'))
        db.execute("INSERT INTO qr_credentials VALUES(?,?,?,?, 'active',?,NULL,NULL)", (qid, uid, digest(token), Fernet(key).encrypt(token.encode()).decode(), '2026-10-27T00:00:00+00:00'))
        db.execute("INSERT INTO transactions VALUES(?,?,?,?,?,'GRANT',500,0,500,?,?,?)", (txid, 'legacy-idempotency-key', 'legacy-request-hash', uid, oid, '升級前測試發點', 'TEST-PC01', '2026-10-27T00:00:00+00:00'))
    return uid, token


def tables(path):
    with sqlite3.connect(path) as db:
        return {name: db.execute('SELECT * FROM ' + name + ' ORDER BY id').fetchall() for name in ('operators', 'users', 'transactions', 'qr_credentials')}


def test_legacy_upgrade_preserves_all_data_and_qr(tmp_path):
    uid, token = legacy_database(tmp_path)
    before = tables(tmp_path / 'points.db')
    app = create_app(tmp_path)
    assert tables(tmp_path / 'points.db') == before
    with sqlite3.connect(tmp_path / 'points.db') as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0002'
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'tx_no_%'").fetchone()[0] == 2
    assert list((tmp_path / 'backups').glob('pre-start-*.db'))
    client = TestClient(app)
    login = client.post('/api/auth/login', json={'username': 'legacy-admin', 'password': 'Legacy-Test-9284'})
    client.headers['X-CSRF-Token'] = login.json()['csrf']
    assert client.get('/api/users/' + uid + '/qr').content.startswith(b'\x89PNG')
    assert client.post('/api/scan/lookup', json={'token': token}).json()['balance'] == 500
    body = {'idempotency_key': str(uuid.uuid4()), 'user_id': uid, 'amount': 700, 'reason': '升級後負點測試', 'station_id': 'TEST-PC02', 'token': token}
    assert client.post('/api/transactions/redeem', json=body).json()['balance_after'] == -200
    app.state.engine.dispose()


def test_failed_upgrade_rolls_back_schema_and_data(tmp_path):
    legacy_database(tmp_path)
    before = tables(tmp_path / 'points.db')

    def fail_before_completion(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('CREATE TABLE portal_sessions'):
            raise RuntimeError('injected migration failure')

    event.listen(Engine, 'before_cursor_execute', fail_before_completion)
    try:
        with pytest.raises(RuntimeError, match='injected migration failure'):
            create_app(tmp_path)
    finally:
        event.remove(Engine, 'before_cursor_execute', fail_before_completion)
    assert tables(tmp_path / 'points.db') == before
    with sqlite3.connect(tmp_path / 'points.db') as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0001'
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('UPDATE users SET balance=-1')
        db.rollback()
    # A retry without the injected failure must be usable.
    app = create_app(tmp_path)
    app.state.engine.dispose()
