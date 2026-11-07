import concurrent.futures
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

from server.app import create_app, initialize
from server.cli import InstanceLock, restore

PASSWORD = 'Only-For-Tests-9284'


def auth(app, username='test-admin', password=PASSWORD):
    client = TestClient(app)
    result = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert result.status_code == 200, result.text
    client.headers['X-CSRF-Token'] = result.json()['csrf']
    return client


@pytest.fixture
def system(tmp_path):
    initialize(tmp_path, 'test-admin', PASSWORD)
    app = create_app(tmp_path)
    client = auth(app)
    user = client.post('/api/users', json={'member_code': 'TEST-001', 'display_name': '測試會員'}).json()
    yield app, client, user, tmp_path
    app.state.engine.dispose()


def payload(user, amount, **kwargs):
    return {'idempotency_key': str(uuid.uuid4()), 'user_id': user['id'], 'amount': amount, 'reason': '自動測試資料', 'station_id': 'TEST-PC', **kwargs}


def grant(client, user, amount=500):
    result = client.post('/api/transactions/grant', json=payload(user, amount))
    assert result.status_code == 200, result.text
    return result


def balance(client, user):
    return client.get('/api/users/' + user['id']).json()['balance']


def test_initialization_health_and_no_default(tmp_path):
    with pytest.raises(Exception):
        initialize(tmp_path, 'admin', 'weak')
    initialize(tmp_path, 'test-admin', PASSWORD)
    with pytest.raises(RuntimeError):
        initialize(tmp_path, 'another', PASSWORD)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        assert client.get('/api/health').json() == {'status': 'ok'}
        assert client.get('/api/users').status_code == 401
        assert client.post('/api/transactions/grant', json={}).status_code == 401
        assert client.get('/openapi.json').status_code == 200


def test_500_redeem_100_and_audit(system):
    _, client, user, _ = system
    grant(client, user)
    response = client.post('/api/transactions/redeem', json=payload(user, 100, token=user['token']))
    assert response.status_code == 200
    tx = response.json()
    assert (tx['balance_before'], tx['balance_after'], tx['delta']) == (500, 400, -100)
    assert tx['operator_id'] and tx['station_id'] == 'TEST-PC' and tx['created_at'].endswith('+00:00')
    assert balance(client, user) == 400


def test_concurrent_redeem(system):
    app, client, user, _ = system
    grant(client, user)
    second = auth(app)
    requests = [payload(user, 400, token=user['token']), payload(user, 400, token=user['token'])]
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda pair: pair[0].post('/api/transactions/redeem', json=pair[1]), zip([client, second], requests)))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert balance(client, user) == 100
    assert len(client.get('/api/transactions').json()) == 2


def test_idempotent_concurrent_and_conflict(system):
    app, client, user, _ = system
    second = auth(app)
    body = payload(user, 100)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda c: c.post('/api/transactions/grant', json=body), [client, second]))
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json() == results[1].json()
    for _ in range(3):
        assert client.post('/api/transactions/grant', json=body).json() == results[0].json()
    assert balance(client, user) == 100
    assert client.post('/api/transactions/grant', json={**body, 'amount': 200}).status_code == 409
    assert client.get('/api/transactions/by-key/' + body['idempotency_key']).json()['balance_after'] == 100


def test_rollback_mid_transaction(system):
    app, client, user, _ = system
    grant(client, user)

    def failure():
        raise RuntimeError('injected disk/ledger failure')
    app.state.before_ledger = failure
    with pytest.raises(RuntimeError):
        client.post('/api/transactions/redeem', json=payload(user, 100, token=user['token']))
    app.state.before_ledger = None
    assert balance(client, user) == 500
    assert len(client.get('/api/transactions').json()) == 1


def test_qr_reissue_disabled_and_download(system):
    _, client, user, _ = system
    assert client.get('/api/users/' + user['id'] + '/qr').content.startswith(b'\x89PNG')
    new = client.post('/api/users/' + user['id'] + '/qr/reissue').json()['token']
    assert new != user['token']
    assert client.post('/api/scan/lookup', json={'token': user['token']}).status_code == 410
    assert client.post('/api/scan/lookup', json={'token': new}).status_code == 200
    assert client.post('/api/transactions/redeem', json=payload(user, 1, token=user['token'])).status_code == 410
    client.patch('/api/users/' + user['id'], json={'status': 'disabled'})
    assert client.post('/api/scan/lookup', json={'token': new}).status_code == 409
    assert client.post('/api/transactions/grant', json=payload(user, 50)).status_code == 409


@pytest.mark.parametrize('amount', [0, -1, 1.2, '50', True, 9007199254740992])
def test_invalid_points(system, amount):
    _, client, user, _ = system
    assert client.post('/api/transactions/grant', json=payload(user, amount)).status_code == 422
    assert balance(client, user) == 0


def test_insufficient_overflow_and_adjust(system):
    _, client, user, _ = system
    assert client.post('/api/transactions/redeem', json=payload(user, 1, token=user['token'])).status_code == 409
    grant(client, user)
    result = client.post('/api/transactions/adjust', json=payload(user, 300))
    assert result.json()['delta'] == -200
    assert client.post('/api/transactions/adjust', json=payload(user, 0)).json()['balance_after'] == 0
    grant(client, user, 9007199254740991)
    assert client.post('/api/transactions/grant', json=payload(user, 1)).status_code == 409
    assert client.post('/api/transactions/adjust', json=payload(user, 100, reason='')).status_code == 422


def test_roles_scope_and_session_revocation(system):
    app, client, user, _ = system
    grant(client, user)
    staff_id = client.post('/api/operators', json={'username': 'test-staff', 'password': PASSWORD, 'role': 'Staff'}).json()['id']
    staff = auth(app, 'test-staff')
    assert staff.post('/api/transactions/grant', json=payload(user, 500)).status_code == 403
    assert staff.post('/api/transactions/grant', json=payload(user, 50)).status_code == 200
    assert staff.post('/api/transactions/adjust', json=payload(user, 300)).status_code == 403
    for route in ['/api/operators', '/api/backups']:
        assert staff.get(route).status_code == 403
    assert staff.post('/api/backup').status_code == 403
    assert len(staff.get('/api/transactions').json()) == 1
    assert 'backup_hour' not in staff.get('/api/settings').json()
    assert client.patch('/api/operators/' + staff_id, json={'status': 'disabled'}).status_code == 200
    assert staff.get('/api/auth/me').status_code == 401


def test_csrf_cookie_rate_limit_and_logout(system):
    app, client, user, _ = system
    assert 'HttpOnly' in client.cookies.jar._cookies['testserver.local']['/']['session']._rest
    token = client.headers.pop('X-CSRF-Token')
    assert client.post('/api/transactions/grant', json=payload(user, 50)).status_code == 403
    client.headers['X-CSRF-Token'] = token
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/auth/me').status_code == 401
    anonymous = TestClient(app)
    for _ in range(10):
        assert anonymous.post('/api/auth/login', json={'username': 'missing', 'password': 'wrong'}).status_code == 401
    assert anonymous.post('/api/auth/login', json={'username': 'test-admin', 'password': PASSWORD}).status_code == 429


def test_db_constraints_and_immutable_ledger(system):
    app, client, user, _ = system
    grant(client, user)
    with sqlite3.connect(app.state.db) as db:
        db.execute('PRAGMA foreign_keys=ON')
        for sql in ["UPDATE users SET balance=-1", "UPDATE users SET balance=1.5", 'DELETE FROM transactions', 'UPDATE transactions SET delta=0', "UPDATE qr_credentials SET user_id='nonexistent'"]:
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(sql)
            db.rollback()
    with app.state.engine.connect() as connection:
        assert connection.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1


def test_csv_injection_filtering_and_input(system):
    _, client, user, _ = system
    grant_body = payload(user, 50, reason=' =HYPERLINK("evil")', station_id='@evil')
    assert client.post('/api/transactions/grant', json=grant_body).status_code == 200
    result = client.get('/api/transactions/export?user_id=' + user['id'])
    assert result.content.startswith(b'\xef\xbb\xbf')
    assert "' =HYPERLINK" in result.text and "'@evil" in result.text
    assert client.get('/api/transactions?kind=REDEEM').json() == []
    assert client.post('/api/scan/lookup', json={'token': 'https://evil.example'}).status_code == 422
    assert client.get('/api/users', params={'q': "' OR 1=1 --"}).json() == []


def test_backup_restore_reopen_and_lock(system):
    app, client, user, data = system
    grant(client, user)
    name = client.post('/api/backup').json()['filename']
    saved = data / 'backups' / name
    assert saved.exists()
    grant(client, user, 100)
    app.state.engine.dispose()
    with InstanceLock(data):
        with pytest.raises(OSError):
            restore(data, saved, 'test-admin', PASSWORD)
    restore(data, saved, 'test-admin', PASSWORD)
    restored = create_app(data)
    new_client = auth(restored)
    assert balance(new_client, user) == 500
    assert new_client.post('/api/scan/lookup', json={'token': user['token']}).status_code == 200
    assert new_client.get('/api/users/' + user['id'] + '/qr').status_code == 200
    assert len(new_client.get('/api/transactions').json()) == 1
    with sqlite3.connect(restored.state.db) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    restored.state.engine.dispose()


def test_full_business_scenario(system):
    app, admin, user, _ = system
    admin.post('/api/operators', json={'username': 'test-pc2', 'password': PASSWORD, 'role': 'Staff'})
    admin.post('/api/operators', json={'username': 'test-pc3', 'password': PASSWORD, 'role': 'Staff'})
    pc2, pc3 = auth(app, 'test-pc2'), auth(app, 'test-pc3')
    grant(admin, user)
    assert pc2.post('/api/scan/lookup', json={'token': user['token']}).json()['balance'] == 500
    assert pc2.post('/api/transactions/redeem', json=payload(user, 100, token=user['token'], station_id='TEST-PC02')).json()['balance_after'] == 400
    assert pc3.post('/api/scan/lookup', json={'token': user['token']}).json()['balance'] == 400
    assert pc3.post('/api/transactions/redeem', json=payload(user, 50, token=user['token'], station_id='TEST-PC03')).json()['balance_after'] == 350
    assert admin.post('/api/transactions/adjust', json=payload(user, 300, reason='測試修正原因')).json()['delta'] == -50
    assert [tx['delta'] for tx in reversed(admin.get('/api/transactions').json())] == [500, -100, -50, -50]


def test_reopen_preserves_idempotency(system):
    app, client, user, data = system
    body = payload(user, 200)
    original = client.post('/api/transactions/grant', json=body).json()
    app.state.engine.dispose()
    reopened = create_app(data)
    after_restart = auth(reopened)
    assert after_restart.post('/api/transactions/grant', json=body).json() == original
    assert balance(after_restart, user) == 200
    reopened.state.engine.dispose()


def test_restore_rejects_invalid_backup(system):
    app, client, user, data = system
    grant(client, user)
    invalid = data / 'invalid.db'
    with sqlite3.connect(invalid) as db:
        db.execute('CREATE TABLE dummy(x)')
    app.state.engine.dispose()
    with pytest.raises(sqlite3.Error):
        restore(data, invalid, 'test-admin', PASSWORD)
    assert balance(client, user) == 500


def test_custom_backup_directory_and_staff_settings(system):
    app, client, user, data = system
    grant(client, user)
    external = data / 'external-backups'
    custom = create_app(data, backup_dir=external)
    custom_client = auth(custom)
    result = custom_client.post('/api/backup')
    assert (external / result.json()['filename']).exists()
    config = {'grant_presets': [25, 500], 'staff_limit': 25, 'backup_hour': 3, 'backup_keep': 2}
    assert custom_client.put('/api/settings', json=config).status_code == 200
    custom_client.post('/api/operators', json={'username': 'test-limited', 'password': PASSWORD, 'role': 'Staff'})
    staff = auth(custom, 'test-limited')
    assert staff.post('/api/transactions/grant', json=payload(user, 500)).status_code == 403
    assert staff.post('/api/transactions/grant', json=payload(user, 25)).status_code == 200
    assert staff.put('/api/settings', json=config).status_code == 403
    custom.state.engine.dispose()
