import uuid

import pytest

from server.app import create_app
from test_system import PASSWORD, auth, balance, payload


def product(name='咖啡', points=50.5):
    return {'id': str(uuid.uuid4()), 'name': name, 'points': points}


def save(client, templates):
    return client.put('/api/redeem-templates', json={'templates': templates})


def test_templates_permissions_persistence_and_old_settings(system):
    app, client, _, data = system
    assert client.get('/api/redeem-templates').json() == []
    item = product()
    assert save(client, [item]).json() == [item]
    client.post('/api/operators', json={'username': 'template-staff', 'password': PASSWORD, 'role': 'Staff'})
    staff = auth(app, 'template-staff')
    assert staff.get('/api/redeem-templates').json() == [item]
    assert save(staff, []).status_code == 403
    # Older clients saving unrelated system settings must not erase products.
    old_settings = client.get('/api/settings').json()
    assert client.put('/api/settings', json=old_settings).status_code == 200
    assert client.get('/api/redeem-templates').json() == [item]
    reopened = create_app(data)
    try:
        assert auth(reopened).get('/api/redeem-templates').json() == [item]
    finally:
        reopened.state.engine.dispose()


@pytest.mark.parametrize('items', [
    [product(points=0)], [product(points=-1)], [product(points=1.25)],
    [product(name='   ')], [product(name='a' * 101)], [product(points=True)],
    [product(points='50')], [product('咖啡'), product('咖啡')],
    [product(str(i)) for i in range(51)],
])
def test_invalid_templates_leave_original_unchanged(system, items):
    _, client, _, _ = system
    original = product('原商品')
    assert save(client, [original]).status_code == 200
    assert save(client, items).status_code == 422
    assert client.get('/api/redeem-templates').json() == [original]


def test_template_redeem_staff_qr_and_immutable_product_name(system):
    app, client, user, _ = system
    item = product()
    save(client, [item])
    client.post('/api/operators', json={'username': 'redeem-staff', 'password': PASSWORD, 'role': 'Staff'})
    staff = auth(app, 'redeem-staff')
    body = payload(user, 50.5, redeem_template_id=item['id'], token=user['token'], reason='商品：咖啡')
    tx = staff.post('/api/transactions/redeem', json=body)
    assert tx.status_code == 200, tx.text
    assert tx.json()['delta'] == -50.5 and tx.json()['reason'] == '商品：咖啡'
    assert balance(client, user) == -50.5
    assert staff.post('/api/transactions/redeem', json=body).json()['id'] == tx.json()['id']
    # Removing the product never rewrites the ledger or prevents successful retries.
    assert save(client, []).status_code == 200
    assert staff.post('/api/transactions/redeem', json=body).json()['id'] == tx.json()['id']
    assert client.get('/api/transactions').json()[0]['reason'] == '商品：咖啡'
    assert '商品：咖啡' in client.get('/api/transactions/export').text


def test_stale_or_tampered_templates_never_change_balance(system):
    _, client, user, _ = system
    item = product()
    save(client, [item])
    template_args = {'redeem_template_id': item['id'], 'token': user['token']}
    assert client.post('/api/transactions/redeem', json=payload(user, 0.5, **template_args)).status_code == 409
    assert client.post('/api/transactions/grant', json=payload(user, 50.5, **template_args)).status_code == 422
    assert client.post('/api/transactions/redeem', json=payload(user, 50.5, redeem_template_id=item['id'])).status_code == 404
    save(client, [{**item, 'points': 60}])
    assert client.post('/api/transactions/redeem', json=payload(user, 50.5, **template_args)).status_code == 409
    save(client, [])
    assert client.post('/api/transactions/redeem', json=payload(user, 60, **template_args)).status_code == 409
    assert balance(client, user) == 0
    assert client.get('/api/transactions').json() == []
