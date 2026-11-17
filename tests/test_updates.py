import concurrent.futures
import io
from datetime import datetime, timedelta, timezone

from openpyxl import Workbook

from test_system import auth, balance, grant, payload, PASSWORD


def xlsx(rows, zero_format=False):
    book = Workbook()
    for record in rows:
        book.active.append(record)
    if zero_format:
        book.active['A2'].number_format = '000'
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def test_edit_member_keeps_qr_and_ledger(system):
    _, client, user, _ = system
    grant(client, user, 1.5)
    result = client.put('/api/users/' + user['id'], json={'member_code': '049', 'display_name': '新名稱'})
    assert result.status_code == 200
    assert result.json()['id'] == user['id']
    assert result.json()['balance'] == 1.5
    assert client.post('/api/scan/lookup', json={'token': user['token']}).json()['member_code'] == '049'
    records = client.get('/api/transactions', params={'member_code': '049'}).json()
    assert len(records) == 1 and records[0]['member_name'] == '新名稱'
    assert client.get('/api/transactions', params={'member_code': '49'}).json() == []
    assert '新名稱' in client.get('/api/transactions/export?member_code=049').text
    other = client.post('/api/users', json={'member_code': '050', 'display_name': '其他'}).json()
    assert client.put('/api/users/' + other['id'], json={'member_code': '049', 'display_name': '重複'}).status_code == 409
    assert client.get('/api/users/' + other['id']).json()['member_code'] == '050'


def test_backdate_records_both_dates_and_filters(system):
    _, client, user, _ = system
    grant(client, user, 10)
    body = payload(user, 0.5, occurred_at='2020-01-02T12:30:00+08:00')
    result = client.post('/api/transactions/grant', json=body)
    assert result.status_code == 200, result.text
    tx = result.json()
    assert tx['occurred_at'] == '2020-01-02T04:30:00.000000+00:00'
    assert tx['created_at'] > tx['occurred_at']
    assert len(client.get('/api/transactions', params={'start': '2020-01-02T04:30:00.000Z', 'end': '2020-01-02T12:30:00+08:00'}).json()) == 1
    assert tx['balance_before'] == 10 and tx['balance_after'] == 10.5
    assert client.post('/api/transactions/grant', json=body).json() == tx
    assert len(client.get('/api/transactions', params={'start': '2020-01-01', 'end': '2020-01-03'}).json()) == 1
    for date in ['2020-01-01T00:00:00', (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), 'bad']:
        assert client.post('/api/transactions/grant', json=payload(user, 1, occurred_at=date)).status_code == 422


def test_half_points_concurrent_and_precision(system):
    app, client, user, _ = system
    grant(client, user, 1.5)
    assert client.post('/api/transactions/redeem', json=payload(user, 0.5, token=user['token'])).json()['balance_after'] == 1
    assert client.post('/api/transactions/adjust', json=payload(user, -0.5)).json()['balance_after'] == -0.5
    for amount in [0.25, 0.1, True, '0.5']:
        assert client.post('/api/transactions/grant', json=payload(user, amount)).status_code == 422
    clients = [auth(app) for _ in range(4)]
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda c: c.post('/api/transactions/grant', json=payload(user, 0.5)), clients))
    assert all(r.status_code == 200 for r in results)
    assert balance(client, user) == 1.5
    assert client.post('/api/transactions/adjust', json=payload(user, 4503599627370494.5)).status_code == 200
    assert client.post('/api/transactions/grant', json=payload(user, 0.5)).json()['balance_after'] == 4503599627370495
    assert client.post('/api/transactions/grant', json=payload(user, 0.5)).status_code == 409


def test_excel_import_atomic_and_leading_zero(system):
    _, client, _, _ = system
    result = client.post('/api/users/import', content=xlsx([['會員編號', '會員名稱'], [49, '會員甲'], ['050', '會員乙']], True))
    assert result.json() == {'imported': 2}
    assert client.get('/api/users?q=049').json()[0]['member_code'] == '049'
    failed = client.post('/api/users/import', content=xlsx([['會員編號', '會員名稱'], ['051', '新會員'], ['049', '重複']]))
    assert failed.status_code == 409
    assert client.get('/api/users?q=051').json() == []
    for rows in [[['wrong', 'headers']], [['會員編號', '會員名稱'], ['052', '=1+1']], [['會員編號', '會員名稱'], ['052', '甲'], ['052', '乙']]]:
        assert client.post('/api/users/import', content=xlsx(rows)).status_code == 422
    assert client.post('/api/users/import', content=b'not xlsx').status_code == 422


def test_staff_restrictions_and_half_presets(system):
    app, client, user, _ = system
    client.post('/api/operators', json={'username': 'staff-updates', 'password': PASSWORD, 'role': 'Staff'})
    staff = auth(app, 'staff-updates')
    assert staff.put('/api/users/' + user['id'], json={'member_code': '049', 'display_name': 'test'}).status_code == 403
    assert staff.post('/api/users/import', content=b'').status_code == 403
    assert staff.post('/api/transactions/grant', json=payload(user, 50, occurred_at='2020-01-01T00:00:00Z')).status_code == 403
    config = {'grant_presets': [0.5, 1.5], 'staff_limit': 1.5, 'backup_hour': 2, 'backup_keep': 14}
    assert client.put('/api/settings', json=config).status_code == 200
    assert staff.post('/api/transactions/grant', json=payload(user, 0.5)).status_code == 200
    assert staff.post('/api/transactions/grant', json=payload(user, 2)).status_code == 403
