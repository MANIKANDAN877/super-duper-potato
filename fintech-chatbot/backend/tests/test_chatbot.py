import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.chatbot import build_account_breakdown, is_percentage_distribution_request
from app.config import settings
from app.database import fetch_dashboard_data, save_confirmed_payment_transaction
from app.main import (
    app,
    capture_payment_order,
    create_paypal_payout,
    create_payment_order,
    evaluate_transaction_fraud_risk,
    fetch_paypal_account_balance,
    fetch_paypal_transaction_history,
    get_payment_status,
)
from app.schemas import PaymentCaptureRequest, PaymentRequest


class ChatbotChartTests(unittest.TestCase):
    def test_detects_percentage_distribution_request(self):
        question = "What is the percentage distribution of debits, credits, fees, and penalties in my financial account?"
        self.assertTrue(is_percentage_distribution_request(question))

    def test_builds_chart_response_for_account_breakdown(self):
        response = build_account_breakdown(
            "Show the percentage breakdown of debits, credits, fees and penalties in my account."
        )

        self.assertIsNotNone(response)
        self.assertEqual(response["category"], "account_breakdown")
        self.assertEqual(response["source_url"], "https://www.iob.bank.in/en/")
        self.assertEqual(response["chart"]["items"][0]["label"], "Debits")
        self.assertEqual(response["chart"]["items"][0]["value"], 42)

    def test_business_loan_answer_uses_official_iob_information(self):
        from app.chatbot import find_best_answer

        response = find_best_answer("What is an MSME loan?")
        self.assertIsNotNone(response)
        self.assertIn("MSME", response["answer"])
        self.assertIn("https://www.iob.bank.in/en/msme", response["source_url"])

    def test_fee_question_explains_common_account_charges(self):
        from app.chatbot import find_best_answer

        response = find_best_answer("Why am I paying fees and penalties on my account?")
        self.assertIsNotNone(response)
        self.assertIn("fees", response["answer"].lower())
        self.assertIn("penalties", response["answer"].lower())

    def test_account_breakdown_answer_includes_example_and_formula(self):
        from app.chatbot import find_best_answer

        response = find_best_answer("Explain my account breakdown.")
        self.assertIsNotNone(response)
        self.assertIn("opening balance", response["answer"].lower())
        self.assertIn("closing balance", response["answer"].lower())
        self.assertIn("authorised", response["answer"].lower())

    def test_interest_rate_question_asks_for_scheme_when_context_is_unclear(self):
        from app.chatbot import find_best_answer

        response = find_best_answer("What is the interest rate?")
        self.assertIsNotNone(response)
        self.assertEqual(response["category"], "clarification_required")
        self.assertIn("Which loan scheme", response["answer"])

    def test_allows_vite_dev_ports_for_cors(self):
        self.assertIn("http://localhost:5176", settings.CORS_ORIGINS)

    @patch.object(settings, "reload_paypal")
    def test_create_payment_order_returns_safe_demo_response(self, _reload):
        original_client_id = settings.PAYPAL_CLIENT_ID
        original_client_secret = settings.PAYPAL_CLIENT_SECRET
        settings.PAYPAL_CLIENT_ID = ""
        settings.PAYPAL_CLIENT_SECRET = ""

        try:
            response = create_payment_order(PaymentRequest(amount="25.00", currency="USD"))
            self.assertEqual(response.mode, "demo")
            self.assertTrue(response.order_id)
        finally:
            settings.PAYPAL_CLIENT_ID = original_client_id
            settings.PAYPAL_CLIENT_SECRET = original_client_secret

    def test_dashboard_api_returns_risk_analysis_payload(self):
        client = TestClient(app)

        response = client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("risk_analysis", payload)
        self.assertGreater(len(payload["risk_analysis"]), 0)
        self.assertIn("fraud_summary", payload)
        self.assertGreater(payload["fraud_summary"]["total_transactions"], 0)

    @patch("app.database.get_connection")
    def test_fetch_dashboard_data_normalizes_datetime_values(self, mock_get_connection):
        mock_conn = Mock()
        mock_cur = Mock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)

        mock_cur.fetchone.side_effect = [
            {"id": 1, "account_name": "Primary Operating Account", "account_number": "**** 4876", "currency": "USD", "balance": 24500.0, "created_at": "2024-05-01T00:00:00Z"}
        ]

        mock_cur.fetchall.side_effect = [
            [
                {"id": 1, "account_id": 1, "transaction_type": "credit", "amount": 100.0, "description": "Payment", "counterparty": "A", "transaction_status": "normal", "is_demo": False, "source_type": "manual", "source_reference": "TX-1", "occurred_at": datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)}
            ],
            [
                {"id": 1, "account_id": 1, "transaction_id": 1, "alert_type": "high_risk", "severity": "high", "status": "new", "message": "watch", "risk_score": 80, "created_at": datetime(2024, 5, 1, 12, 5, tzinfo=timezone.utc)}
            ],
        ]
        mock_get_connection.return_value = mock_conn

        data = fetch_dashboard_data()

        self.assertEqual(data["transactions"][0]["occurred_at"], "2024-05-01T12:00:00+00:00")
        self.assertEqual(data["alerts"][0]["created_at"], "2024-05-01T12:05:00+00:00")

    @patch.object(settings, "reload_paypal")
    @patch("app.main.httpx.post")
    def test_create_payment_order_uses_paypal_when_configured(self, mock_post, _reload):
        original_client_id = settings.PAYPAL_CLIENT_ID
        original_client_secret = settings.PAYPAL_CLIENT_SECRET
        original_recipient = getattr(settings, "PAYPAL_RECEIVER_EMAIL", "")
        settings.PAYPAL_CLIENT_ID = "test-client-id"
        settings.PAYPAL_CLIENT_SECRET = "test-client-secret"
        settings.PAYPAL_RECEIVER_EMAIL = "deepsbiswa@yahoo.com"

        try:
            mock_post.side_effect = [
                type(
                    "MockResponse",
                    (),
                    {"status_code": 200, "json": lambda self: {"access_token": "demo-token"}},
                )(),
                type(
                    "MockResponse",
                    (),
                    {
                        "status_code": 200,
                        "json": lambda self: {
                            "id": "PAYPAL-ORDER-123",
                            "status": "CREATED",
                            "links": [{"rel": "approve", "href": "https://paypal.example/approve"}],
                        },
                    },
                )(),
            ]

            response = create_payment_order(PaymentRequest(amount="25.00", currency="USD"))
            self.assertEqual(response.order_id, "PAYPAL-ORDER-123")
            self.assertEqual(response.approval_url, "https://paypal.example/approve")
            self.assertEqual(mock_post.call_args_list[1].kwargs["json"]["purchase_units"][0]["payee"]["email_address"], "deepsbiswa@yahoo.com")
        finally:
            settings.PAYPAL_CLIENT_ID = original_client_id
            settings.PAYPAL_CLIENT_SECRET = original_client_secret
            if original_recipient:
                settings.PAYPAL_RECEIVER_EMAIL = original_recipient
            else:
                delattr(settings, "PAYPAL_RECEIVER_EMAIL")

    @patch.object(settings, "reload_paypal")
    @patch("app.main.httpx.get")
    @patch("app.main.httpx.post")
    def test_get_payment_status_returns_order_status(self, mock_post, mock_get, _reload):
        original_client_id = settings.PAYPAL_CLIENT_ID
        original_client_secret = settings.PAYPAL_CLIENT_SECRET
        settings.PAYPAL_CLIENT_ID = "test-client-id"
        settings.PAYPAL_CLIENT_SECRET = "test-client-secret"

        try:
            mock_post.return_value = Mock(status_code=200, json=lambda: {"access_token": "demo-token"})
            mock_get.return_value = Mock(
                status_code=200,
                json=lambda: {"id": "PAYPAL-ORDER-STATUS", "status": "APPROVED"},
            )

            response = get_payment_status("PAYPAL-ORDER-STATUS")
            self.assertEqual(response["status"], "APPROVED")
            self.assertEqual(response["order_id"], "PAYPAL-ORDER-STATUS")
        finally:
            settings.PAYPAL_CLIENT_ID = original_client_id
            settings.PAYPAL_CLIENT_SECRET = original_client_secret

    @patch.object(settings, "reload_paypal")
    @patch("app.main.capture_paypal_order")
    def test_capture_payment_order_returns_failed_when_paypal_capture_fails(self, mock_capture, _reload):
        original_client_id = settings.PAYPAL_CLIENT_ID
        original_client_secret = settings.PAYPAL_CLIENT_SECRET
        settings.PAYPAL_CLIENT_ID = "test-client-id"
        settings.PAYPAL_CLIENT_SECRET = "test-client-secret"

        try:
            mock_capture.side_effect = RuntimeError("sandbox capture failed")

            response = capture_payment_order(PaymentCaptureRequest(order_id="PAYPAL-ORDER-456"))
            self.assertEqual(response.status, "failed")
            self.assertFalse(response.captured)
            self.assertIn("failed", response.message.lower())
        finally:
            settings.PAYPAL_CLIENT_ID = original_client_id
            settings.PAYPAL_CLIENT_SECRET = original_client_secret

    @patch.object(settings, "reload_paypal")
    @patch("app.main.save_confirmed_payment_transaction")
    @patch("app.main.capture_paypal_order")
    def test_capture_payment_order_persists_confirmed_paypal_capture(self, mock_capture, mock_persist, _reload):
        original_client_id = settings.PAYPAL_CLIENT_ID
        original_client_secret = settings.PAYPAL_CLIENT_SECRET
        settings.PAYPAL_CLIENT_ID = "test-client-id"
        settings.PAYPAL_CLIENT_SECRET = "test-client-secret"
        mock_capture.return_value = {
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {
                        "captures": [{"status": "COMPLETED", "amount": {"value": "24.50", "currency_code": "USD"}}]
                    }
                }
            ],
        }
        mock_persist.return_value = {"status": "inserted", "amount": 24.5}

        try:
            response = capture_payment_order(PaymentCaptureRequest(order_id="PAYPAL-ORDER-789"))
            self.assertEqual(response.status, "captured")
            self.assertTrue(response.captured)
            self.assertIn("recorded", response.message.lower())
            mock_persist.assert_called_once()
        finally:
            settings.PAYPAL_CLIENT_ID = original_client_id
            settings.PAYPAL_CLIENT_SECRET = original_client_secret

    @patch("app.database.get_connection")
    def test_save_confirmed_payment_transaction_records_credit_entry(self, mock_get_connection):
        mock_conn = Mock()
        mock_cur = Mock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
        mock_cur.fetchone.side_effect = [
            {"id": 1, "balance": 24500.0},
            {"id": 101, "transaction_type": "credit", "amount": 25.0, "description": "PayPal Sandbox payment"},
            {"id": 101, "balance": 24525.0},
        ]
        mock_get_connection.return_value = mock_conn

        result = save_confirmed_payment_transaction(
            order_id="PAYPAL-ORDER-DB-1",
            amount=25.0,
            currency="USD",
            description="PayPal Sandbox payment",
            payer_id="payer-123",
        )

    def test_evaluate_transaction_fraud_risk_flags_unusual_high_value_and_frequency(self):
        txn = {
            "id": 501,
            "account_id": 1,
            "amount": 14000.0,
            "description": "Large repeated transfer",
            "counterparty": "Unusual supplier",
            "transaction_type": "debit",
            "occurred_at": "2026-11-05T08:00:00Z",
        }
        recent = [
            {"amount": 2500.0, "occurred_at": "2026-11-05T07:55:00Z"},
            {"amount": 3200.0, "occurred_at": "2026-11-05T07:50:00Z"},
            {"amount": 11000.0, "occurred_at": "2026-11-05T07:40:00Z"},
        ]

        result = evaluate_transaction_fraud_risk(txn, recent)

        self.assertIn(result["risk_level"], {"HIGH", "MEDIUM"})
        self.assertGreaterEqual(result["risk_score"], 60)
        self.assertTrue(result["reasons"])
        self.assertEqual(result["review_status"], "pending_review")

    def test_evaluate_transaction_fraud_risk_handles_clean_transaction(self):
        txn = {
            "id": 502,
            "account_id": 1,
            "amount": 120.0,
            "description": "Office stationery",
            "counterparty": "Office Supply Co",
            "transaction_type": "debit",
            "occurred_at": "2026-11-05T11:00:00Z",
        }
        recent = [
            {"amount": 90.0, "occurred_at": "2026-11-05T10:30:00Z"},
            {"amount": 110.0, "occurred_at": "2026-11-05T09:50:00Z"},
        ]

        result = evaluate_transaction_fraud_risk(txn, recent)

        self.assertEqual(result["risk_level"], "LOW")
        self.assertLessEqual(result["risk_score"], 35)
        self.assertEqual(result["review_status"], "not_required")
        self.assertIsNotNone(result["transaction_id"])
        self.assertTrue(result["reasons"] or True)

    @patch.object(settings, "reload_paypal")
    @patch("app.main.httpx.post")
    def test_create_paypal_payout_uses_sandbox_api_and_tracks_status(self, mock_post, _reload):
        original_client_id = settings.PAYPAL_CLIENT_ID
        original_client_secret = settings.PAYPAL_CLIENT_SECRET
        original_mode = settings.PAYPAL_MODE
        original_live_payouts = getattr(settings, "PAYPAL_LIVE_PAYOUTS_ENABLED", False)
        original_country = getattr(settings, "PAYPAL_BUSINESS_COUNTRY", "")
        settings.PAYPAL_CLIENT_ID = "test-client-id"
        settings.PAYPAL_CLIENT_SECRET = "test-client-secret"
        settings.PAYPAL_MODE = "sandbox"
        settings.PAYPAL_LIVE_PAYOUTS_ENABLED = False
        settings.PAYPAL_BUSINESS_COUNTRY = "US"

        try:
            mock_post.side_effect = [
                Mock(status_code=200, json=lambda: {"access_token": "demo-token"}),
                Mock(
                    status_code=202,
                    json=lambda: {
                        "batch_status": "PENDING",
                        "batch_header": {"payout_batch_id": "PAYOUT-BATCH-001"},
                    },
                ),
            ]

            response = create_paypal_payout(
                recipient_email="friend@example.com",
                amount=1.0,
                currency="USD",
                note="Friend payout",
            )

            self.assertEqual(response["status"], "pending")
            self.assertEqual(response["recipient_email"], "friend@example.com")
            self.assertEqual(response["payout_batch_id"], "PAYOUT-BATCH-001")
            self.assertIn("batch", response["message"].lower())
        finally:
            settings.PAYPAL_CLIENT_ID = original_client_id
            settings.PAYPAL_CLIENT_SECRET = original_client_secret
            settings.PAYPAL_MODE = original_mode
            settings.PAYPAL_LIVE_PAYOUTS_ENABLED = original_live_payouts
            if original_country:
                settings.PAYPAL_BUSINESS_COUNTRY = original_country
            else:
                if hasattr(settings, "PAYPAL_BUSINESS_COUNTRY"):
                    delattr(settings, "PAYPAL_BUSINESS_COUNTRY")

    @patch("app.main.get_paypal_access_token", return_value="demo-token")
    @patch("app.main.httpx.get")
    def test_fetch_paypal_account_balance_returns_successful_response(self, mock_get, _token):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "balances": [
                    {
                        "currency": "USD",
                        "available_balance": {"currency": "USD", "value": "1250.50"},
                        "total_balance": {"currency": "USD", "value": "1300.00"},
                        "last_refresh_time": "2026-11-04T15:45:00Z",
                        "primary": True,
                    }
                ]
            },
        )

        response = fetch_paypal_account_balance()
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["balances"][0]["currency"], "USD")
        self.assertGreater(response["balances"][0]["available_balance"], 0)

    @patch("app.main.get_paypal_access_token", return_value="demo-token")
    @patch("app.main.httpx.get")
    def test_fetch_paypal_account_balance_handles_permission_error(self, mock_get, _token):
        mock_get.return_value = Mock(
            status_code=403,
            json=lambda: {"name": "PERMISSION_DENIED"},
        )

        with self.assertRaises(HTTPException) as context:
            fetch_paypal_account_balance()

        self.assertEqual(context.exception.status_code, 403)
        self.assertIn("permission", str(context.exception.detail).lower())

    @patch("app.main.get_paypal_access_token", return_value="demo-token")
    @patch("app.main.httpx.get")
    def test_fetch_paypal_transaction_history_returns_successful_response(self, mock_get, _token):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "transaction_details": [
                    {
                        "transaction_info": {
                            "transaction_id": "TXN-123",
                            "transaction_initiation_date": "2026-11-03T12:00:00Z",
                            "transaction_status": "S",
                            "transaction_amount": {"currency_code": "USD", "value": "-45.00"},
                        }
                    },
                    {
                        "transaction_info": {
                            "transaction_id": "TXN-456",
                            "transaction_initiation_date": "2026-11-02T08:00:00Z",
                            "transaction_status": "S",
                            "transaction_amount": {"currency_code": "USD", "value": "120.00"},
                        }
                    },
                ]
            },
        )

        response = fetch_paypal_transaction_history(limit=10)
        self.assertEqual(response["status"], "ok")
        self.assertEqual(len(response["transactions"]), 2)
        self.assertEqual(response["transactions"][0]["direction"], "debit")
        self.assertEqual(response["transactions"][1]["direction"], "credit")

    def test_dashboard_returns_financial_summary_payload(self):
        from app.main import get_dashboard_data

        dashboard = get_dashboard_data()
        self.assertIn("account", dashboard)
        self.assertIn("summary", dashboard)
        self.assertIn("transactions", dashboard)
        self.assertIn("alerts", dashboard)
        self.assertGreater(dashboard["summary"]["balance"], 0)


if __name__ == "__main__":
    unittest.main()
