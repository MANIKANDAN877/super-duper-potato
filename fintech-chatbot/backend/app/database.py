import queue
import threading
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

from .config import settings


def _normalize_datetime_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _normalize_datetime_values(rows):
    normalized = []
    for row in rows:
        item = dict(row)
        item["occurred_at"] = _normalize_datetime_value(item.get("occurred_at"))
        item["created_at"] = _normalize_datetime_value(item.get("created_at"))
        normalized.append(item)
    return normalized


def _fallback_transactions():
    return [
        {
            "id": 1,
            "account_id": 1,
            "transaction_type": "credit",
            "amount": 4300.00,
            "description": "Client payment received",
            "counterparty": "Northwind Labs",
            "transaction_status": "normal",
            "is_demo": False,
            "source_type": "paypal_sandbox",
            "source_reference": "PP-INV-001",
            "occurred_at": "2026-11-04T09:00:00Z",
        },
        {
            "id": 2,
            "account_id": 1,
            "transaction_type": "debit",
            "amount": 1200.00,
            "description": "Vendor payout",
            "counterparty": "CloudOps Services",
            "transaction_status": "normal",
            "is_demo": False,
            "source_type": "manual",
            "source_reference": "VENDOR-912",
            "occurred_at": "2026-11-03T18:30:00Z",
        },
        {
            "id": 3,
            "account_id": 1,
            "transaction_type": "credit",
            "amount": 6100.00,
            "description": "Incoming transfer",
            "counterparty": "Customer settlement",
            "transaction_status": "suspicious",
            "is_demo": False,
            "source_type": "manual",
            "source_reference": "IN-4421",
            "occurred_at": "2026-11-04T02:15:00Z",
        },
        {
            "id": 4,
            "account_id": 1,
            "transaction_type": "debit",
            "amount": 3200.00,
            "description": "Card payment",
            "counterparty": "Card ending 7421",
            "transaction_status": "normal",
            "is_demo": False,
            "source_type": "manual",
            "source_reference": "CARD-552",
            "occurred_at": "2026-11-03T11:45:00Z",
        },
        {
            "id": 5,
            "account_id": 1,
            "transaction_type": "debit",
            "amount": 1800.00,
            "description": "Repeated transfer",
            "counterparty": "Unknown merchant",
            "transaction_status": "flagged",
            "is_demo": True,
            "source_type": "demo",
            "source_reference": "demo-001",
            "occurred_at": "2026-11-04T14:10:00Z",
        },
    ]


def _fallback_alerts():
    return [
        {
            "id": 1,
            "account_id": 1,
            "transaction_id": 5,
            "alert_type": "repeated_transaction",
            "severity": "high",
            "status": "new",
            "message": "Multiple transfers were detected within a short period of time.",
            "risk_score": 82,
            "created_at": "2026-11-04T14:35:00Z",
        },
        {
            "id": 2,
            "account_id": 1,
            "transaction_id": 3,
            "alert_type": "unexpected_incoming_payment",
            "severity": "medium",
            "status": "under_review",
            "message": "Large inbound transfer outside the customer’s usual activity pattern.",
            "risk_score": 71,
            "created_at": "2026-11-04T02:20:00Z",
        },
    ]


def get_connection():
    result_queue = queue.Queue()

    def _connect():
        try:
            conn = psycopg2.connect(
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                dbname=settings.DB_NAME,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                connect_timeout=2,
            )
            result_queue.put(("ok", conn))
        except Exception as exc:  # pragma: no cover - fallback path for unavailable Postgres
            result_queue.put(("error", exc))

    worker = threading.Thread(target=_connect, daemon=True)
    worker.start()
    worker.join(timeout=2)

    if worker.is_alive():
        raise TimeoutError(f"PostgreSQL connection to {settings.DB_HOST}:{settings.DB_PORT} timed out.")

    if result_queue.empty():
        raise ConnectionError(f"PostgreSQL connection to {settings.DB_HOST}:{settings.DB_PORT} did not respond.")

    status, payload = result_queue.get_nowait()
    if status == "error":
        raise payload

    return payload


def fetch_questions():
    try:
        conn = get_connection()
    except Exception:
        return []

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, question, answer, category, keywords, source_url, last_verified_at
                FROM questions
                ORDER BY id
                """
            )
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    except Exception:
        return []
    finally:
        if "conn" in locals():
            conn.close()


def fetch_transactions(limit: int = 20):
    try:
        conn = get_connection()
    except Exception:
        return _fallback_transactions()[:limit]

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    t.id,
                    t.account_id,
                    t.transaction_type,
                    t.amount,
                    t.description,
                    t.counterparty,
                    t.transaction_status,
                    t.is_demo,
                    t.source_type,
                    t.source_reference,
                    t.occurred_at
                FROM transactions t
                ORDER BY t.occurred_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            return _normalize_datetime_values([dict(row) for row in rows])
    except Exception:
        return _fallback_transactions()[:limit]
    finally:
        if "conn" in locals():
            conn.close()


def fetch_alerts(limit: int = 10):
    try:
        conn = get_connection()
    except Exception:
        return _fallback_alerts()[:limit]

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    id,
                    account_id,
                    transaction_id,
                    alert_type,
                    severity,
                    status,
                    message,
                    risk_score,
                    created_at
                FROM fraud_alerts
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            return _normalize_datetime_values([dict(row) for row in rows])
    except Exception:
        return _fallback_alerts()[:limit]
    finally:
        if "conn" in locals():
            conn.close()


def fetch_dashboard_data():
    try:
        conn = get_connection()
    except Exception:
        transactions = _fallback_transactions()
        alerts = _fallback_alerts()
        account = {
            "id": 1,
            "account_name": "Primary Operating Account",
            "account_number": "**** 4876",
            "currency": "USD",
            "balance": 5000.00,
            "last_updated": "2026-11-04T14:10:00Z",
        }
        credits = sum(item["amount"] for item in transactions if item["transaction_type"] == "credit")
        debits = sum(item["amount"] for item in transactions if item["transaction_type"] == "debit")
        fraud_summary = {
            "total_transactions": len(transactions),
            "high_risk_transactions": 0,
            "medium_risk_transactions": 0,
            "suspicious_transactions": 0,
            "pending_reviews": 0,
            "risk_distribution": {"HIGH": 0, "MEDIUM": 0, "LOW": len(transactions)},
            "risk_analysis": [],
        }
        return {
            "account": account,
            "summary": {
                "balance": account["balance"],
                "total_credits": round(credits, 2),
                "total_debits": round(debits, 2),
                "transactions_count": len(transactions),
                "alerts_count": len(alerts),
            },
            "transactions": transactions,
            "alerts": alerts,
            "fraud_summary": fraud_summary,
            "risk_analysis": fraud_summary["risk_analysis"],
        }

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, account_name, account_number, currency, balance, created_at
                FROM accounts
                ORDER BY id
                LIMIT 1
                """
            )
            account_row = cur.fetchone()
            if not account_row:
                account = {
                    "id": 1,
                    "account_name": "Primary Operating Account",
                    "account_number": "**** 4876",
                    "currency": "USD",
                    "balance": 5000.00,
                    "last_updated": "2026-11-04T14:10:00Z",
                }
            else:
                created_at = account_row.get("created_at")
                account = {
                    "id": account_row["id"],
                    "account_name": account_row["account_name"],
                    "account_number": account_row["account_number"],
                    "currency": account_row["currency"],
                    "balance": float(account_row["balance"] or 0),
                    "last_updated": _normalize_datetime_value(created_at) if created_at else "2026-11-04T00:00:00Z",
                }

            cur.execute(
                """
                SELECT id, account_id, transaction_type, amount, description, counterparty,
                       transaction_status, is_demo, source_type, source_reference, occurred_at
                FROM transactions
                ORDER BY occurred_at DESC
                LIMIT 20
                """
            )
            transactions = _normalize_datetime_values([dict(row) for row in cur.fetchall()])

            cur.execute(
                """
                SELECT id, account_id, transaction_id, alert_type, severity, status,
                       message, risk_score, created_at
                FROM fraud_alerts
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
            alerts = _normalize_datetime_values([dict(row) for row in cur.fetchall()])

        credits = sum(float(item["amount"]) for item in transactions if str(item["transaction_type"]).lower() == "credit")
        debits = sum(float(item["amount"]) for item in transactions if str(item["transaction_type"]).lower() == "debit")
        fraud_summary = {
            "total_transactions": len(transactions),
            "high_risk_transactions": 0,
            "medium_risk_transactions": 0,
            "suspicious_transactions": 0,
            "pending_reviews": 0,
            "risk_distribution": {"HIGH": 0, "MEDIUM": 0, "LOW": len(transactions)},
            "risk_analysis": [],
        }
        return {
            "account": account,
            "summary": {
                "balance": float(account["balance"]),
                "total_credits": round(credits, 2),
                "total_debits": round(debits, 2),
                "transactions_count": len(transactions),
                "alerts_count": len(alerts),
            },
            "transactions": transactions,
            "alerts": alerts,
            "fraud_summary": fraud_summary,
            "risk_analysis": fraud_summary["risk_analysis"],
        }
    except Exception:
        transactions = _fallback_transactions()
        alerts = _fallback_alerts()
        fraud_summary = {
            "total_transactions": len(transactions),
            "high_risk_transactions": 0,
            "medium_risk_transactions": 0,
            "suspicious_transactions": 0,
            "pending_reviews": 0,
            "risk_distribution": {"HIGH": 0, "MEDIUM": 0, "LOW": len(transactions)},
            "risk_analysis": [],
        }
        return {
            "account": {
                "id": 1,
                "account_name": "Primary Operating Account",
                "account_number": "**** 4876",
                "currency": "USD",
                "balance": 5000.00,
                "last_updated": "2026-11-04T14:10:00Z",
            },
            "summary": {
                "balance": 5000.00,
                "total_credits": 10400.00,
                "total_debits": 6200.00,
                "transactions_count": len(transactions),
                "alerts_count": len(alerts),
            },
            "transactions": transactions,
            "alerts": alerts,
            "fraud_summary": fraud_summary,
            "risk_analysis": fraud_summary["risk_analysis"],
        }
    finally:
        if "conn" in locals():
            conn.close()


def save_confirmed_payment_transaction(
    order_id: str,
    amount: float,
    currency: str = "USD",
    description: str = "PayPal Sandbox payment",
    payer_id: str | None = None,
    counterparty: str = "PayPal Sandbox",
):
    normalized_amount = float(amount or 0)
    if not order_id or normalized_amount <= 0:
        return None

    try:
        conn = get_connection()
    except Exception:
        return None

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, balance
                FROM accounts
                ORDER BY id ASC
                LIMIT 1
                """
            )
            account_row = cur.fetchone()
            if account_row is None:
                return None

            source_reference = order_id
            cur.execute(
                """
                INSERT INTO transactions (
                    account_id,
                    transaction_type,
                    amount,
                    description,
                    counterparty,
                    transaction_status,
                    is_demo,
                    source_type,
                    source_reference,
                    occurred_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (source_reference) DO NOTHING
                RETURNING id, account_id, transaction_type, amount, description, counterparty,
                          transaction_status, is_demo, source_type, source_reference, occurred_at
                """,
                (
                    account_row["id"],
                    "credit",
                    normalized_amount,
                    description,
                    counterparty,
                    "normal",
                    False,
                    "paypal_sandbox",
                    source_reference,
                ),
            )
            row = cur.fetchone()
            if row is not None:
                cur.execute(
                    """
                    UPDATE accounts
                    SET balance = balance + %s
                    WHERE id = %s
                    RETURNING balance
                    """,
                    (normalized_amount, account_row["id"]),
                )
                balance_row = cur.fetchone()
                conn.commit()
                result = dict(row)
                result["updated_balance"] = float(balance_row["balance"]) if balance_row else float(account_row["balance"])
                result["currency"] = currency
                result["payer_id"] = payer_id
                return result

            conn.commit()
            return {
                "status": "already_recorded",
                "order_id": order_id,
                "currency": currency,
                "payer_id": payer_id,
                "amount": normalized_amount,
            }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    finally:
        if "conn" in locals():
            conn.close()


def fetch_suggested_questions(limit: int = 5):
    rows = fetch_questions()
    if not rows:
        return []
    return rows[:limit]
