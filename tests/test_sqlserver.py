"""Real SQL Server acceptance tests. Requires an explicitly supplied admin URL.

Creates and drops a unique disposable database, never uses a production DB.
"""
import concurrent.futures
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from server.app import create_app, initialize
from server.sqlserver import initialize_schema
from server.transfer import transfer
from test_system import PASSWORD, auth, payload


@pytest.fixture
def sql_database(monkeypatch):
    value = os.environ.get('QRPOINT_TEST_SQLSERVER_URL')
    if not value:
        pytest.skip('未設定測試用 SQL Server 管理員連線；需在 SQL Express 環境驗收')
    base = make_url(value)
    if 'odbc_connect' in base.query:
        pytest.fail('測試須使用標準 URL，以確保建立獨立資料庫')
    name = 'QRPointTest_' + uuid.uuid4().hex
    maintenance = create_engine(base.set(database='master'), isolation_level='AUTOCOMMIT', hide_parameters=True)
    with maintenance.connect() as c:
        c.exec_driver_sql('CREATE DATABASE [' + name + ']')
    url = base.set(database=name)
    engine = create_engine(url, hide_parameters=True)
    initialize_schema(engine)
    monkeypatch.setenv('QRPOINT_DATABASE_URL', url.render_as_string(hide_password=False))
    try:
        yield engine, url
    finally:
        engine.dispose()
        with maintenance.connect() as c:
            c.exec_driver_sql('ALTER DATABASE [' + name + '] SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
            c.exec_driver_sql('DROP DATABASE [' + name + ']')
        maintenance.dispose()


def test_sqlserver_multiple_app_instances(sql_database, tmp_path):
    engine, _ = sql_database
    initialize(tmp_path, 'test-admin', PASSWORD)
    app1, app2 = create_app(tmp_path), create_app(tmp_path)
    try:
        clients = [auth(app1), auth(app2), auth(app1), auth(app2)]
        user = clients[0].post('/api/users', json={'member_code': '049', 'display_name': 'SQL會員'}).json()
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            replies = list(pool.map(lambda c: c.post('/api/transactions/grant', json=payload(user, 0.5)), clients))
        assert all(r.status_code == 200 for r in replies), [r.text for r in replies]
        assert clients[0].get('/api/users/' + user['id']).json()['balance'] == 2
        body = payload(user, 0.5)
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            replies = list(pool.map(lambda c: c.post('/api/transactions/grant', json=body), clients))
        assert len({r.json()['id'] for r in replies}) == 1
        assert clients[0].get('/api/users/' + user['id']).json()['balance'] == 2.5
        assert len(clients[0].get('/api/transactions?member_code=049').json()) == 5
        assert clients[0].get('/api/transactions/export?member_code=049').status_code == 200
        with pytest.raises(Exception):
            with engine.begin() as c:
                c.execute(text('DELETE FROM transactions'))
        with engine.connect() as c:
            assert c.execute(text('SELECT SUM(delta) FROM transactions')).scalar() == 2.5
    finally:
        app1.state.engine.dispose()
        app2.state.engine.dispose()


def test_sqlserver_transfer_preserves_data(sql_database, tmp_path, monkeypatch):
    engine, url = sql_database
    source, target = tmp_path / 'old', tmp_path / 'new'
    target.mkdir()
    monkeypatch.delenv('QRPOINT_DATABASE_URL')
    initialize(source, 'test-admin', PASSWORD)
    old_app = create_app(source)
    client = auth(old_app)
    user = client.post('/api/users', json={'member_code': '049', 'display_name': '移轉會員'}).json()
    assert client.post('/api/transactions/grant', json=payload(user, 1.5)).status_code == 200
    old_app.state.engine.dispose()
    before = (source / 'points.db').read_bytes()
    report = transfer(source / 'points.db', source / 'secret.key', target, engine)
    assert report['transactions']['count'] == 1
    assert (source / 'points.db').read_bytes() == before
    assert (target / 'secret.key').read_bytes() == (source / 'secret.key').read_bytes()
    monkeypatch.setenv('QRPOINT_DATABASE_URL', url.render_as_string(hide_password=False))
    new_app = create_app(target)
    try:
        current = auth(new_app)
        assert current.post('/api/scan/lookup', json={'token': user['token']}).json()['balance'] == 1.5
        assert current.get('/api/transactions?member_code=049').json()[0]['delta'] == 1.5
        with pytest.raises(RuntimeError, match='非空白'):
            transfer(source / 'points.db', source / 'secret.key', target, engine)
    finally:
        new_app.state.engine.dispose()
