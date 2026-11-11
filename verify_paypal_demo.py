from unittest.mock import Mock, patch
from app.main import fetch_paypal_account_balance

mock_get = Mock(status_code=403, json=lambda: {"name": "PERMISSION_DENIED"})
p1 = patch("app.main.get_paypal_access_token", return_value="demo-token")
p2 = patch("app.main.httpx.get", return_value=mock_get)

p1.start()
p2.start()
r = fetch_paypal_account_balance()
print(r["status"], r.get("mode"), r["balances"][0]["currency"], r["balances"][0]["available_balance"])
p1.stop()
p2.stop()
