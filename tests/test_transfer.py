import sqlite3

import pytest
from sqlalchemy import event, text

from server.app import create_app
from server.transfer import transfer
from test_migration import legacy_database


def test_transfer_legacy_data_is_verified_and_non_destructive(tmp_path):
    source, target = tmp_path / 'source', tmp_path / 'target'
    uid, token = legacy_database(source)
    app = create_app(target)
    (target / 'secret.key').unlink()
    before = (source / 'points.db').read_bytes()
    try:
        report = transfer(source / 'points.db', source / 'secret.key', target, app.state.engine)
        assert report['users']['count'] == report['transactions']['count'] == 1
        assert len(report['transactions']['sha256']) == 64
        assert (source / 'points.db').read_bytes() == before
        assert (target / 'secret.key').read_bytes() == (source / 'secret.key').read_bytes()
        with app.state.engine.connect() as c:
            assert c.execute(text('SELECT balance FROM users WHERE id=:id'), {'id': uid}).scalar() == 500
            assert c.execute(text('SELECT julianday(occurred_at)=julianday(created_at) FROM transactions')).scalar() == 1
            assert c.execute(text('SELECT count(*) FROM sessions')).scalar() == 0
        with pytest.raises(RuntimeError, match='非空白'):
            transfer(source / 'points.db', source / 'secret.key', target, app.state.engine)
    finally:
        app.state.engine.dispose()


def test_transfer_rollback_and_key_mismatch(tmp_path):
    source, target = tmp_path / 'source', tmp_path / 'target'
    legacy_database(source)
    app = create_app(target)
    try:
        with pytest.raises(RuntimeError, match='secret.key'):
            transfer(source / 'points.db', source / 'secret.key', target, app.state.engine)
        (target / 'secret.key').unlink()

        def fail(connection, cursor, statement, parameters, context, many):
            if statement.startswith('INSERT INTO transactions'):
                raise RuntimeError('injected transfer failure')

        event.listen(app.state.engine, 'before_cursor_execute', fail)
        try:
            with pytest.raises(RuntimeError, match='injected'):
                transfer(source / 'points.db', source / 'secret.key', target, app.state.engine)
        finally:
            event.remove(app.state.engine, 'before_cursor_execute', fail)
        assert not (target / 'secret.key').exists()
        with app.state.engine.connect() as c:
            assert c.execute(text('SELECT count(*) FROM operators')).scalar() == 0
            assert c.execute(text('SELECT count(*) FROM users')).scalar() == 0
        with sqlite3.connect(source / 'points.db') as old:
            old.execute('UPDATE users SET balance=123')
        with pytest.raises(RuntimeError, match='帳本總額'):
            transfer(source / 'points.db', source / 'secret.key', target, app.state.engine)
    finally:
        app.state.engine.dispose()
