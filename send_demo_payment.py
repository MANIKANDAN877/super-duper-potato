import json
import urllib.request

base = 'http://localhost:8000'

def req(url, method='GET', payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(request, timeout=20) as resp:
        body = resp.read().decode('utf-8')
        return json.loads(body) if body else {}

before = req(f'{base}/dashboard')
print('BEFORE_BALANCE', before.get('summary', {}).get('balance'))
order = req(f'{base}/payment/create-order', 'POST', {
    'amount': '1.00',
    'currency': 'USD',
    'description': 'Sandbox transfer to deepsbiswa@yahoo.com'
})
print('ORDER', order)
cap = req(f'{base}/payment/capture-order', 'POST', {
    'order_id': order.get('order_id'),
    'payer_id': 'demo-payer'
})
print('CAPTURE', cap)
after = req(f'{base}/dashboard')
print('AFTER_BALANCE', after.get('summary', {}).get('balance'))
