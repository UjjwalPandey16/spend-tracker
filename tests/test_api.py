from fastapi.testclient import TestClient
import pytest
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'test.db')) as client:
        yield client


def add(client, amount='10.00', category='food', date='2026-09-10', note=''):
    return client.post('/expenses', json=dict(amount=amount, category=category, date=date, note=note))


def test_create_and_persist(tmp_path):
    path = tmp_path / 'persistent.db'
    with TestClient(create_app(path)) as first:
        response = add(first, '12.30', ' Food ', note='Lunch')
        assert response.status_code == 201
        assert response.json() == dict(id=1, amount='12.30', category='food', note='Lunch', date='2026-09-10')
    with TestClient(create_app(path)) as second:
        assert second.get('/expenses').json() == [response.json()]


@pytest.mark.parametrize('patch', [
    {'amount':0}, {'amount':-1}, {'amount':'1.001'}, {'amount':'NaN'},
    {'amount':'Infinity'}, {'amount':'1000000000'}, {'amount':True},
    {'category':'   '}, {'category':'x'*81}, {'note':'x'*501},
    {'date':'2026-02-30'}, {'date':'not-a-date'}, {'amount':None},
])
def test_invalid_expenses(client, patch):
    payload = dict(amount='1.00', category='food', date='2026-09-10')
    payload.update(patch)
    assert client.post('/expenses', json=payload).status_code == 422
    assert client.get('/expenses').json() == []


def test_missing_fields_and_malformed_json(client):
    assert client.post('/expenses', json={}).status_code == 422
    assert client.post('/expenses', content='{', headers={'Content-Type':'application/json'}).status_code == 422


def test_filters_inclusive_and_order(client):
    add(client, date='2026-09-01')
    add(client, date='2026-09-30')
    add(client, category='travel', date='2026-09-15')
    add(client, date='2026-10-01')
    rows = client.get('/expenses', params=dict(category=' FOOD ', start_date='2026-09-01', end_date='2026-09-30')).json()
    assert [r['date'] for r in rows] == ['2026-09-30','2026-09-01']
    assert len(client.get('/expenses', params=dict(limit=1, offset=1)).json()) == 1
    assert client.get('/expenses', params={'category':"food' OR 1=1 --"}).json() == []


@pytest.mark.parametrize('query', [
    {'start_date':'2026-10-01','end_date':'2026-09-01'},
    {'start_date':'yesterday'}, {'limit':0}, {'limit':501}, {'offset':-1},
])
def test_invalid_filters(client, query):
    assert client.get('/expenses', params=query).status_code == 422


def test_exact_money_and_month_change(client):
    add(client, '0.10', date='2026-08-31')
    add(client, '0.10', date='2026-09-01')
    add(client, '0.20', date='2026-09-30')
    add(client, '999.00', date='2026-10-01')
    summary = client.get('/summary?month=2026-09').json()
    assert summary['total_spend'] == '0.30'
    assert summary['previous_month_total'] == '0.10'
    assert summary['spend_by_category'] == {'food':'0.30'}
    assert summary['month_over_month_change_percent'] == 200
    assert summary['insights'] == [{'category':'food','increase_percent':200}]


def test_empty_and_zero_baseline(client):
    summary = client.get('/summary?month=2026-09').json()
    assert summary['total_spend'] == '0.00'
    assert summary['spend_by_category'] == {}
    assert summary['month_over_month_change_percent'] is None
    add(client)
    summary = client.get('/summary?month=2026-09').json()
    assert summary['month_over_month_change_percent'] is None
    assert summary['insights'] == []


def test_year_rollover_decline_and_threshold(client):
    add(client, '100', category='food', date='2025-12-31')
    add(client, '120', category='food', date='2026-01-01')
    add(client, '100', category='travel', date='2025-12-01')
    summary = client.get('/summary?month=2026-01').json()
    assert summary['previous_month_total'] == '200.00'
    assert summary['month_over_month_change_percent'] == -40
    assert summary['insights'] == []  # Exactly 20% is not more than 20%.
    add(client, '0.01', date='2026-01-31')
    assert client.get('/summary?month=2026-01').json()['insights'] == [{'category':'food','increase_percent':20.01}]


@pytest.mark.parametrize('month', ['2026-13','2026-1','hello','0001-01','9999-12'])
def test_invalid_month(client, month):
    assert client.get('/summary', params={'month':month}).status_code == 422


def test_ui_assets(client):
    assert client.get('/').status_code == 200
    assert 'expense-form' in client.get('/').text
    assert client.get('/static/app.js').status_code == 200

