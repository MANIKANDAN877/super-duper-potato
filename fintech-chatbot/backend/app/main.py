import ssl
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .chatbot import find_best_answer
from .config import settings
from .database import (
    fetch_alerts,
    fetch_dashboard_data,
    fetch_questions,
    fetch_suggested_questions,
    fetch_transactions,
    save_confirmed_payment_transaction,
)
from .schemas import (
    ChatRequest,
    ChatResponse,
    DashboardResponse,
    PaymentCaptureRequest,
    PaymentCaptureResponse,
    PaymentOrderResponse,
    PaymentRequest,
    PayoutRequest,
    PayoutResponse,
)


def _safe_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _parse_iso_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def evaluate_transaction_fraud_risk(transaction: dict, recent_transactions: list[dict] | None = None, config: dict | None = None) -> dict:
    if not isinstance(transaction, dict):
        raise ValueError("A transaction dictionary is required for fraud analysis.")

    cfg = {
        "large_amount_threshold": 5000.0,
        "medium_amount_threshold": 2000.0,
        "frequency_window_minutes": 60,
        "duplicate_window_minutes": 30,
        "burst_threshold_count": 3,
        "max_score": 100,
    }
    if isinstance(config, dict):
        cfg.update(config)

    amount = abs(_safe_float(transaction.get("amount") or transaction.get("value")))
    tx_type = str(transaction.get("transaction_type") or transaction.get("type") or "debit").lower()
    description = str(transaction.get("description") or "").lower()
    counterparty = str(transaction.get("counterparty") or transaction.get("merchant") or "").lower()
    occurred_at = _parse_iso_datetime(transaction.get("occurred_at") or transaction.get("created_at"))
    recent = recent_transactions or []

    score = 0
    reasons: list[str] = []

    if amount >= cfg["large_amount_threshold"]:
        score += 35
        reasons.append("unusually_large_transaction")
    elif amount >= cfg["medium_amount_threshold"]:
        score += 15
        reasons.append("large_transaction")

    if tx_type == "debit" and amount >= cfg["medium_amount_threshold"]:
        score += 10
        reasons.append("outgoing_transfer_threshold_exceeded")

    if isinstance(recent, list) and recent:
        recent_values = [_safe_float(item.get("amount") or item.get("value")) for item in recent if isinstance(item, dict)]
        if recent_values:
            average_recent = sum(recent_values) / len(recent_values)
            if amount >= max(average_recent * 3, cfg["medium_amount_threshold"]):
                score += 20
                reasons.append("amount_spike_vs_recent_average")

        within_window = []
        for item in recent:
            if not isinstance(item, dict):
                continue
            item_time = _parse_iso_datetime(item.get("occurred_at") or item.get("created_at"))
            if item_time and occurred_at:
                delta_minutes = abs((occurred_at - item_time).total_seconds() / 60.0)
                if delta_minutes <= cfg["frequency_window_minutes"]:
                    within_window.append(item)
            elif item.get("amount") is not None:
                within_window.append(item)

        if len(within_window) >= cfg["burst_threshold_count"]:
            score += 20
            reasons.append("multiple_recent_transactions")

    suspicious_markers = [
        "repeated",
        "urgent",
        "rapid",
        "wire",
        "cash",
        "unknown",
        "suspicious",
        "flagged",
        "settlement",
    ]
    if any(marker in description or marker in counterparty for marker in suspicious_markers):
        score += 10
        reasons.append("suspicious_counterparty_or_description")

    if transaction.get("transaction_status") in {"suspicious", "flagged", "under_review"}:
        score += 15
        reasons.append("existing_risk_flag")

    if transaction.get("source_reference") and transaction.get("source_reference") in {
        item.get("source_reference") for item in recent if isinstance(item, dict) and item.get("source_reference")
    }:
        score += 10
        reasons.append("duplicate_reference_detected")

    score = min(int(score), cfg["max_score"])

    if score >= 70:
        risk_level = "HIGH"
    elif score >= 45:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    review_status = "pending_review" if risk_level != "LOW" else "not_required"
    return {
        "transaction_id": transaction.get("id") or transaction.get("transaction_id") or "unknown",
        "account_id": transaction.get("account_id"),
        "risk_score": score,
        "risk_level": risk_level,
        "review_status": review_status,
        "reasons": sorted(set(reasons)),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }


def build_fraud_summary(transactions: list[dict] | None = None) -> dict:
    rows = transactions or []
    assessed = []
    for tx in rows:
        if not isinstance(tx, dict):
            continue
        recent = [item for item in rows if item is not tx and isinstance(item, dict)]
        assessed.append(evaluate_transaction_fraud_risk(tx, recent))

    high_risk = sum(1 for item in assessed if item["risk_level"] == "HIGH")
    medium_risk = sum(1 for item in assessed if item["risk_level"] == "MEDIUM")
    pending_review = sum(1 for item in assessed if item["review_status"] == "pending_review")
    suspicious = sum(1 for item in assessed if item["risk_score"] >= 45)

    return {
        "total_transactions": len(rows),
        "high_risk_transactions": high_risk,
        "medium_risk_transactions": medium_risk,
        "suspicious_transactions": suspicious,
        "pending_reviews": pending_review,
        "risk_distribution": {
            "HIGH": high_risk,
            "MEDIUM": medium_risk,
            "LOW": max(0, len(rows) - high_risk - medium_risk),
        },
        "risk_analysis": sorted(assessed, key=lambda item: item["risk_score"], reverse=True)[:5],
    }


def _paypal_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


def _paypal_http_error(action: str, response: httpx.Response) -> HTTPException:
    error_code = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error_code = str(payload.get("error") or payload.get("name") or "")
    except Exception:
        error_code = ""

    if error_code == "invalid_client":
        return HTTPException(
            status_code=502,
            detail=(
                "PayPal authentication failed: the Client ID and Client Secret were rejected. "
                "Open the PayPal Developer Dashboard, select Apps & Credentials, switch to Sandbox, "
                "and copy the REST API Client ID and Secret for this app into backend/.env as "
                "PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET. Sandbox credentials only work with "
                "https://api-m.sandbox.paypal.com. Restart the backend after saving .env."
            ),
        )

    return HTTPException(
        status_code=502,
        detail=f"PayPal {action} failed. Check the sandbox app credentials and try again.",
    )


def get_paypal_access_token() -> str | None:
    settings.reload_paypal()
    if not settings.paypal_credentials_configured():
        return None

    response = httpx.post(
        f"{settings.PAYPAL_BASE_URL.rstrip('/')}/v1/oauth2/token",
        data={"grant_type": "client_credentials"},
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
        headers={
            "Accept": "application/json",
            "Accept-Language": "en_US",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=20,
        verify=_paypal_ssl_context(),
    )

    if response.status_code >= 400:
        raise _paypal_http_error("authentication", response)

    token = response.json().get("access_token")
    if not token:
        raise HTTPException(status_code=502, detail="PayPal token response was empty.")

    return token


def create_paypal_checkout_order(amount: float, currency: str, description: str | None) -> dict:
    token = get_paypal_access_token()
    if not token:
        raise HTTPException(
            status_code=500,
            detail=(
                "PayPal client credentials are missing. Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET "
                "in backend/.env using Sandbox REST API values from the PayPal Developer Dashboard."
            ),
        )

    payee_email = settings.PAYPAL_RECEIVER_EMAIL or "deepsbiswa@yahoo.com"
    frontend_base = settings.FRONTEND_BASE_URL.rstrip("/")
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": currency.upper(),
                    "value": f"{amount:.2f}",
                },
                "description": description or "Fintech service payment",
                "payee": {
                    "email_address": payee_email,
                },
            }
        ],
        "application_context": {
            "brand_name": settings.APP_TITLE,
            "user_action": "PAY_NOW",
            "return_url": f"{frontend_base}/payment/success",
            "cancel_url": f"{frontend_base}/payment/cancel",
        },
    }

    response = httpx.post(
        f"{settings.PAYPAL_BASE_URL.rstrip('/')}/v2/checkout/orders",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=20,
        verify=_paypal_ssl_context(),
    )

    if response.status_code >= 400:
        raise _paypal_http_error("order creation", response)

    return response.json()


def get_payment_status(order_id: str) -> dict:
    if not order_id:
        raise HTTPException(status_code=400, detail="Order ID is required.")

    token = get_paypal_access_token()
    if not token:
        raise HTTPException(
            status_code=500,
            detail=(
                "PayPal client credentials are missing. Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET "
                "in backend/.env using Sandbox REST API values from the PayPal Developer Dashboard."
            ),
        )

    response = httpx.get(
        f"{settings.PAYPAL_BASE_URL.rstrip('/')}/v2/checkout/orders/{order_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=20,
        verify=_paypal_ssl_context(),
    )

    if response.status_code >= 400:
        raise _paypal_http_error("status lookup", response)

    payload = response.json()
    return {
        "order_id": str(payload.get("id") or order_id),
        "status": str(payload.get("status") or "UNKNOWN").upper(),
        "payer": payload.get("payer") or {},
        "purchase_units": payload.get("purchase_units") or [],
        "raw": payload,
    }


def capture_paypal_order(order_id: str) -> dict:
    token = get_paypal_access_token()
    if not token:
        raise HTTPException(
            status_code=500,
            detail=(
                "PayPal client credentials are missing. Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET "
                "in backend/.env using Sandbox REST API values from the PayPal Developer Dashboard."
            ),
        )

    response = httpx.post(
        f"{settings.PAYPAL_BASE_URL.rstrip('/')}/v2/checkout/orders/{order_id}/capture",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=20,
        verify=_paypal_ssl_context(),
    )

    if response.status_code >= 400:
        raise _paypal_http_error("capture", response)

    return response.json()


def _extract_paypal_capture_amount(paypal_data: dict) -> float:
    try:
        for purchase_unit in paypal_data.get("purchase_units", []):
            payments = purchase_unit.get("payments", {})
            for capture in payments.get("captures", []):
                amount = capture.get("amount") or {}
                value = amount.get("value")
                if value is not None:
                    return float(value)
    except Exception:
        return 0.0
    return 0.0


def _extract_paypal_capture_currency(paypal_data: dict) -> str:
    try:
        for purchase_unit in paypal_data.get("purchase_units", []):
            payments = purchase_unit.get("payments", {})
            for capture in payments.get("captures", []):
                amount = capture.get("amount") or {}
                currency = amount.get("currency_code")
                if currency:
                    return str(currency).upper()
    except Exception:
        return "USD"
    return "USD"


def _paypal_reporting_permission_message(action: str) -> str:
    return (
        f"PayPal {action} is unavailable. The Sandbox app may not have the required Reporting API permission, "
        "or the report has not refreshed yet. Grant the Reporting API scope in the PayPal Developer Dashboard "
        "and wait a few minutes before retrying. This app does not invent balances or transactions."
    )


def _paypal_money_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        return _paypal_money_float(value.get("value") or value.get("amount") or value.get("total"))
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


PAYPAL_PAYOUT_ELIGIBLE_COUNTRIES = {
    "AE", "AR", "AT", "AU", "BE", "BR", "CA", "CH", "CL", "CN", "CO", "DE", "DK", "ES",
    "FI", "FR", "GB", "GR", "HK", "ID", "IE", "IN", "IT", "JP", "KR", "MX", "MY", "NL",
    "NO", "NZ", "PE", "PH", "PL", "PT", "QA", "SA", "SE", "SG", "TH", "TW", "US", "VN",
    "ZA",
}


def _validate_paypal_payout_country() -> tuple[bool, str]:
    if settings.PAYPAL_MODE != "sandbox":
        if not settings.PAYPAL_LIVE_PAYOUTS_ENABLED:
            return False, "Live payouts are disabled. Keep PAYPAL_LIVE_PAYOUTS_ENABLED=false in sandbox mode."
        return True, "Live PayPal payouts are enabled for the connected account."

    country = (settings.PAYPAL_BUSINESS_COUNTRY or "").strip().upper()
    if not country:
        return False, (
            "PayPal payout eligibility is not yet confirmed. Set PAYPAL_BUSINESS_COUNTRY to the home country "
            "for the connected Sandbox business account before sending payouts."
        )
    if country not in PAYPAL_PAYOUT_ELIGIBLE_COUNTRIES:
        return False, (
            f"The connected PayPal business country '{country}' is not currently eligible for the Payouts API. "
            "Review the account country restrictions before attempting a payout."
        )
    return True, f"The connected Sandbox business account country '{country}' is eligible for payouts."


def _paypal_reporting_get(endpoint: str, action: str, params: dict | None = None) -> dict:
    token = get_paypal_access_token()
    if not token:
        raise HTTPException(
            status_code=500,
            detail=(
                "PayPal client credentials are missing. Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET "
                "in backend/.env using Sandbox REST API values from the PayPal Developer Dashboard."
            ),
        )

    response = httpx.get(
        f"{settings.PAYPAL_BASE_URL.rstrip('/')}{endpoint}",
        params=params or {},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        timeout=20,
        verify=_paypal_ssl_context(),
    )

    if response.status_code == 403:
        raise HTTPException(status_code=403, detail=_paypal_reporting_permission_message(action))

    if response.status_code >= 400:
        raise _paypal_http_error(action, response)

    try:
        payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PayPal {action} returned an invalid response.") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail=f"PayPal {action} returned an unexpected payload.")

    return payload


def fetch_paypal_account_profile(token: str | None = None) -> dict:
    token = token or get_paypal_access_token()
    if not token:
        return {
            "connected": False,
            "email": None,
            "account_status": "unconfigured",
            "country": settings.PAYPAL_BUSINESS_COUNTRY or "UNKNOWN",
        }

    response = httpx.get(
        f"{settings.PAYPAL_BASE_URL.rstrip('/')}/v1/identity/openidconnect/userinfo?schema=openid",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        timeout=20,
        verify=_paypal_ssl_context(),
    )

    if response.status_code >= 400:
        return {
            "connected": False,
            "email": None,
            "account_status": "access_denied",
            "country": settings.PAYPAL_BUSINESS_COUNTRY or "UNKNOWN",
        }

    payload = response.json() if hasattr(response, "json") else {}
    if not isinstance(payload, dict):
        return {
            "connected": False,
            "email": None,
            "account_status": "unknown",
            "country": settings.PAYPAL_BUSINESS_COUNTRY or "UNKNOWN",
        }

    return {
        "connected": True,
        "email": payload.get("email") or payload.get("user_id") or None,
        "account_status": payload.get("account_status") or "active",
        "country": (payload.get("country") or settings.PAYPAL_BUSINESS_COUNTRY or "UNKNOWN").upper(),
    }


def fetch_paypal_account_balance() -> dict:
    payload = _paypal_reporting_get(
        "/v1/reporting/balances",
        "balance report",
        params={"page_size": 100},
    )

    account_info = fetch_paypal_account_profile()
    balances = payload.get("balances") or payload.get("items") or payload.get("records") or []
    if not isinstance(balances, list):
        balances = []

    normalized = []
    last_refresh = None
    for entry in balances:
        if not isinstance(entry, dict):
            continue
        total = entry.get("total_balance") or entry.get("totalBalance") or entry.get("total") or {}
        available = entry.get("available_balance") or entry.get("availableBalance") or entry.get("available") or {}
        currency = (
            entry.get("currency")
            or (total.get("currency") if isinstance(total, dict) else None)
            or (available.get("currency") if isinstance(available, dict) else None)
            or entry.get("currency_code")
            or "USD"
        )
        entry_refresh = entry.get("last_refresh_time") or entry.get("last_refresh") or entry.get("last_updated") or entry.get("as_of") or None
        if entry_refresh and not last_refresh:
            last_refresh = entry_refresh
        normalized.append(
            {
                "currency": str(currency).upper(),
                "available_balance": _paypal_money_float(available),
                "total_balance": _paypal_money_float(total),
                "last_refresh_time": entry_refresh,
                "is_primary": bool(entry.get("primary") or entry.get("is_primary")),
            }
        )

    connected_account = account_info.get("email") or settings.PAYPAL_RECEIVER_EMAIL or "Business account unavailable"
    country_status = _validate_paypal_payout_country()
    return {
        "status": "ok",
        "account_mode": settings.PAYPAL_MODE,
        "business_account": {
            "connected": account_info.get("connected", False),
            "email": connected_account,
            "status": account_info.get("account_status") or "active",
            "country": account_info.get("country") or settings.PAYPAL_BUSINESS_COUNTRY or "UNKNOWN",
            "last_updated": last_refresh or None,
        },
        "balances": normalized,
        "account_status": country_status[1],
        "message": "PayPal Sandbox balance data loaded from the Reporting API.",
        "reporting_delay_notice": "Balances may take several minutes to appear after a payment is approved.",
    }


_PAYOUT_HISTORY: set[str] = set()


def create_paypal_payout(
    recipient_email: str,
    amount: float,
    currency: str = "USD",
    note: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    if not recipient_email or "@" not in recipient_email:
        raise HTTPException(status_code=400, detail="A valid recipient email is required for PayPal payout submission.")

    try:
        amount_value = float(amount)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Payout amount must be a valid number.") from exc

    if amount_value <= 0:
        raise HTTPException(status_code=400, detail="Payout amount must be greater than zero.")

    settings.reload_paypal()
    if settings.PAYPAL_MODE == "live" and not settings.PAYPAL_LIVE_PAYOUTS_ENABLED:
        raise HTTPException(
            status_code=400,
            detail="Live payout submission is disabled. Keep PAYPAL_LIVE_PAYOUTS_ENABLED=false for Sandbox testing.",
        )

    country_ok, country_message = _validate_paypal_payout_country()
    if not country_ok:
        raise HTTPException(status_code=403, detail=country_message)

    token = get_paypal_access_token()
    if not token:
        raise HTTPException(status_code=500, detail="PayPal Client ID and Client Secret are required before payout submission.")

    payout_key = (idempotency_key or f"{recipient_email}:{currency.upper()}:{amount_value:.2f}:{note or ''}").strip().lower()
    if payout_key in _PAYOUT_HISTORY:
        raise HTTPException(status_code=409, detail="This payout request has already been submitted. Use a new amount or unique idempotency key.")
    _PAYOUT_HISTORY.add(payout_key)

    batch_id = f"payout-{uuid.uuid4().hex[:12]}"
    payload = {
        "sender_batch_header": {
            "sender_batch_id": batch_id,
            "email_message": note or "PayPal Sandbox payout from the connected business account.",
            "recipient_type": "EMAIL",
            "note": note or "Funds sent to recipient",
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "amount": {"value": f"{amount_value:.2f}", "currency": currency.upper()},
                "note": note or "PayPal Sandbox payout",
                "receiver": recipient_email,
                "sender_item_id": f"item-{uuid.uuid4().hex[:8]}",
            }
        ],
    }

    response = httpx.post(
        f"{settings.PAYPAL_BASE_URL.rstrip('/')}/v1/payments/payouts",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": batch_id,
        },
        timeout=30,
        verify=_paypal_ssl_context(),
    )

    if response.status_code >= 400:
        raise _paypal_http_error("payout submission", response)

    data = response.json() if hasattr(response, "json") else {}
    batch_header = data.get("batch_header") if isinstance(data, dict) else {}
    payout_batch_id = batch_header.get("payout_batch_id") if isinstance(batch_header, dict) else data.get("payout_batch_id")
    batch_status_raw = (
        (batch_header.get("batch_status") if isinstance(batch_header, dict) else None)
        or data.get("batch_status")
        or "PENDING"
    )
    batch_status = str(batch_status_raw).upper()
    account_info = fetch_paypal_account_profile(token=token)

    return {
        "status": batch_status.lower(),
        "payout_batch_id": payout_batch_id or batch_id,
        "recipient_email": recipient_email,
        "amount": amount_value,
        "currency": currency.upper(),
        "actual_paypal_status": batch_status,
        "message": f"PayPal payout submitted. Current PayPal batch status: {batch_status}.",
        "account_email": account_info.get("email") or settings.PAYPAL_RECEIVER_EMAIL,
        "account_status": account_info.get("account_status") or "active",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "raw": data,
    }


def fetch_paypal_payout_status(payout_batch_id: str) -> dict:
    if not payout_batch_id:
        raise HTTPException(status_code=400, detail="A payout batch ID is required.")

    token = get_paypal_access_token()
    if not token:
        raise HTTPException(status_code=500, detail="PayPal Client ID and Client Secret are required before payout status checks.")

    response = httpx.get(
        f"{settings.PAYPAL_BASE_URL.rstrip('/')}/v1/payments/payouts/{payout_batch_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        timeout=30,
        verify=_paypal_ssl_context(),
    )

    if response.status_code >= 400:
        raise _paypal_http_error("payout status lookup", response)

    data = response.json() if hasattr(response, "json") else {}
    batch_header = data.get("batch_header") if isinstance(data, dict) else {}
    batch_status_raw = (
        (batch_header.get("batch_status") if isinstance(batch_header, dict) else None)
        or data.get("batch_status")
        or "UNKNOWN"
    )
    batch_status = str(batch_status_raw).upper()
    account_info = fetch_paypal_account_profile()
    items = data.get("items") or []

    return {
        "status": batch_status.lower(),
        "payout_batch_id": payout_batch_id,
        "batch_status": batch_status,
        "account_email": account_info.get("email") or settings.PAYPAL_RECEIVER_EMAIL,
        "items": items,
        "message": f"PayPal payout batch status: {batch_status}.",
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def _require_owner_payout_authorization(request: Request) -> None:
    owner_token = (settings.PAYPAL_OWNER_TOKEN or "").strip()
    if not owner_token:
        raise HTTPException(
            status_code=403,
            detail="Owner payout authorization is not configured. Real payouts are blocked until the business owner enables a payout token.",
        )

    provided = (request.headers.get("x-paypal-owner-token") or request.headers.get("authorization") or "").strip()
    if provided.lower().startswith("bearer "):
        provided = provided[7:].strip()
    if provided != owner_token:
        raise HTTPException(
            status_code=403,
            detail="Only the PayPal business account owner may submit a payout. Shared read-only users can view the account and balance only.",
        )


def _paypal_transaction_direction(transaction_info: dict, amount_value: float) -> str:
    event_code = str(
        transaction_info.get("transaction_event_code")
        or transaction_info.get("event_code")
        or transaction_info.get("transaction_type")
        or ""
    ).upper()
    event_text = event_code.lower()
    if "received" in event_text or "credit" in event_text:
        return "credit"
    if "sent" in event_text or "debit" in event_text or "withdraw" in event_text:
        return "debit"
    if amount_value >= 0:
        return "credit"
    return "debit"


def fetch_paypal_transaction_history(limit: int = 10, start_date: str | None = None, end_date: str | None = None) -> dict:
    params = {"page_size": limit, "sort_by": "transaction_date", "sort_order": "DESC"}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    payload = _paypal_reporting_get(
        "/v1/reporting/transactions",
        "transaction report",
        params=params,
    )

    transactions = payload.get("transaction_details") or payload.get("transactions") or payload.get("items") or payload.get("records") or []
    if not isinstance(transactions, list):
        transactions = []

    normalized = []
    for entry in transactions:
        if not isinstance(entry, dict):
            continue
        transaction_info = entry.get("transaction_info") if isinstance(entry.get("transaction_info"), dict) else entry
        if not isinstance(transaction_info, dict):
            continue

        amount = transaction_info.get("transaction_amount") or transaction_info.get("amount") or {}
        amount_value = amount.get("value") if isinstance(amount, dict) else amount
        parsed_amount = _paypal_money_float(amount_value)
        currency = (
            (amount.get("currency_code") if isinstance(amount, dict) else None)
            or transaction_info.get("currency_code")
            or "USD"
        )
        tx_id = (
            transaction_info.get("transaction_id")
            or transaction_info.get("id")
            or entry.get("id")
            or "N/A"
        )
        transaction_date = (
            transaction_info.get("transaction_initiation_date")
            or transaction_info.get("transaction_date")
            or transaction_info.get("transaction_updated_date")
            or transaction_info.get("time_posted")
            or None
        )
        status = transaction_info.get("transaction_status") or transaction_info.get("status") or "UNKNOWN"
        payer = transaction_info.get("payer_info") or transaction_info.get("payer") or {}
        payee = transaction_info.get("payee_info") or transaction_info.get("payee") or {}
        sender = (
            payer.get("email_address")
            or payer.get("email")
            or payer.get("payer_email")
            or payer.get("name")
            or (payer.get("address", {}).get("country_code") if isinstance(payer.get("address"), dict) else None)
            or None
        )
        receiver = (
            payee.get("email_address")
            or payee.get("email")
            or payee.get("receiver_email")
            or payee.get("name")
            or None
        )
        direction = _paypal_transaction_direction(transaction_info, parsed_amount)

        normalized.append(
            {
                "transaction_id": str(tx_id),
                "transaction_date": transaction_date,
                "amount": parsed_amount,
                "currency": str(currency).upper(),
                "status": str(status),
                "direction": direction,
                "sender": sender,
                "receiver": receiver,
                "payment_status": str(status),
            }
        )

    return {
        "status": "ok",
        "account_mode": settings.PAYPAL_MODE,
        "transactions": normalized,
        "message": "PayPal Sandbox transaction history loaded from the Reporting API.",
        "reporting_delay_notice": "Reporting data can lag behind a payment approval by a few minutes.",
    }


app = FastAPI(title=settings.APP_TITLE, version=settings.APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": settings.APP_TITLE}


@app.get("/questions")
def get_questions():
    try:
        rows = fetch_suggested_questions(limit=10)
        return {"questions": rows}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Database error: {str(exc)}") from exc


@app.post("/chat", response_model=ChatResponse)
def chat_with_bot(payload: ChatRequest):
    question = payload.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        result = find_best_answer(question)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Database error: {str(exc)}") from exc

    if result is None:
        return ChatResponse(
            question=question,
            answer=(
                "I could not find a strong match in the current knowledge base. "
                "This chatbot is an educational prototype and is not an official Indian Overseas Bank service. "
                "Please check the official IOB website for the latest policy, eligibility, rates, and documents."
            ),
            category="unmatched",
            source_url="https://www.iob.bank.in/en/",
            confidence=0,
            match_found=False,
        )

    return ChatResponse(
        question=question,
        answer=result["answer"],
        category=result["category"],
        source_url=result.get("source_url"),
        confidence=result.get("confidence", 0),
        match_found=True,
        chart=result.get("chart"),
    )


@app.get("/dashboard", response_model=DashboardResponse)
def get_dashboard_data():
    data = fetch_dashboard_data()
    transactions = data.get("transactions", []) if isinstance(data, dict) else []
    fraud_summary = build_fraud_summary(transactions)
    data["fraud_summary"] = fraud_summary
    data["risk_analysis"] = fraud_summary["risk_analysis"]
    return data


@app.get("/fraud/monitor")
def get_fraud_monitor():
    transactions = fetch_transactions()
    fraud_summary = build_fraud_summary(transactions)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": fraud_summary,
        "transactions": [
            {
                **txn,
                **evaluate_transaction_fraud_risk(txn, [item for item in transactions if item.get("id") != txn.get("id")]),
            }
            for txn in transactions
        ],
    }


@app.post("/fraud/analyze")
def analyze_fraud_transaction(payload: dict):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Transaction payload must be a JSON object.")

    transaction = payload.get("transaction") or payload
    if not isinstance(transaction, dict):
        raise HTTPException(status_code=400, detail="A valid transaction object is required.")

    recent = fetch_transactions(limit=10)
    result = evaluate_transaction_fraud_risk(transaction, [item for item in recent if item.get("id") != transaction.get("id")])
    return result


@app.get("/transactions")
def list_transactions():
    return {"transactions": fetch_transactions()}


@app.get("/alerts")
def list_alerts():
    return {"alerts": fetch_alerts()}


@app.get("/paypal/balance")
def get_paypal_balance_report():
    try:
        return fetch_paypal_account_balance()
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(
            status_code=502,
            detail=(
                "PayPal Sandbox balance retrieval failed. The Reporting API may require additional permissions "
                "or the report may still be refreshing."
            ),
        ) from exc


@app.get("/paypal/transactions")
def get_paypal_transactions_report():
    try:
        return fetch_paypal_transaction_history(limit=10)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(
            status_code=502,
            detail=(
                "PayPal Sandbox transaction history retrieval failed. The Reporting API may require additional "
                "permissions or the report may still be refreshing."
            ),
        ) from exc


@app.get("/paypal/account")
def get_paypal_account_details():
    try:
        balance = fetch_paypal_account_balance()
        profile = fetch_paypal_account_profile()
        return {
            "connected": profile.get("connected", False),
            "account_email": profile.get("email") or settings.PAYPAL_RECEIVER_EMAIL,
            "account_status": profile.get("account_status") or "active",
            "country": profile.get("country") or settings.PAYPAL_BUSINESS_COUNTRY or "UNKNOWN",
            "mode": settings.PAYPAL_MODE,
            "balance": balance.get("balances", []),
            "last_updated": balance.get("business_account", {}).get("last_updated") or None,
            "read_only_access": True,
            "message": "Read-only access to the connected PayPal business account is available without exposing OAuth credentials.",
        }
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=502, detail="Unable to read the connected PayPal account details.") from exc


@app.post("/paypal/payout", response_model=PayoutResponse)
def submit_paypal_payout(payload: PayoutRequest, request: Request):
    _require_owner_payout_authorization(request)
    try:
        result = create_paypal_payout(
            recipient_email=str(payload.recipient_email),
            amount=float(payload.amount),
            currency=(payload.currency or "USD").upper(),
            note=payload.note,
            idempotency_key=payload.idempotency_key,
        )
        return PayoutResponse(
            status=result["status"],
            payout_batch_id=result.get("payout_batch_id"),
            recipient_email=result["recipient_email"],
            amount=result["amount"],
            currency=result["currency"],
            actual_paypal_status=result.get("actual_paypal_status"),
            message=result["message"],
            account_email=result.get("account_email"),
            account_status=result.get("account_status"),
            last_updated=result.get("last_updated"),
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=502, detail="The PayPal payout request could not be processed.") from exc


@app.get("/paypal/payout-status/{payout_batch_id}")
def get_paypal_payout_status_route(payout_batch_id: str):
    try:
        return fetch_paypal_payout_status(payout_batch_id)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=502, detail=f"Unable to fetch PayPal payout status for batch {payout_batch_id}.") from exc


@app.get("/payment/status/{order_id}")
def payment_status(order_id: str):
    try:
        return get_payment_status(order_id)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=502, detail=f"Unable to fetch PayPal payment status for order {order_id}.") from exc


@app.post("/payment/create-order", response_model=PaymentOrderResponse)
def create_payment_order(payload: PaymentRequest):
    try:
        amount = float(payload.amount)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Payment amount must be a valid number.") from exc

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero.")

    order_id = f"demo-order-{uuid.uuid4().hex[:12]}"
    currency = (payload.currency or "USD").upper()
    settings.reload_paypal()

    if not settings.paypal_credentials_configured():
        return PaymentOrderResponse(
            status="demo",
            order_id=order_id,
            amount=f"{amount:.2f}",
            currency=currency,
            mode="demo",
            message="Payment order created in demo mode. This is not a live PayPal Sandbox payment.",
            approval_url=None,
        )

    if currency == "INR":
        return PaymentOrderResponse(
            status="demo",
            order_id=order_id,
            amount=f"{amount:.2f}",
            currency="INR",
            mode="demo",
            message=(
                f"Payment order created for ₹{amount:.2f} in demo mode. "
                "PayPal Sandbox REST checkout supports USD/EUR; INR is kept in demo mode."
            ),
            approval_url=None,
        )

    try:
        paypal_data = create_paypal_checkout_order(amount, currency, payload.description)
        approval_url = next(
            (link["href"] for link in paypal_data.get("links", []) if link.get("rel") == "approve"),
            None,
        )

        return PaymentOrderResponse(
            status=paypal_data.get("status", "created").lower(),
            order_id=paypal_data.get("id", order_id),
            amount=f"{amount:.2f}",
            currency=currency,
            mode=settings.PAYPAL_MODE,
            message="PayPal Sandbox order created successfully.",
            approval_url=approval_url,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "PayPal order creation failed. The transaction was not completed and cannot be marked successful. "
                "Check the Sandbox credentials and verify the App ID and secret in backend/.env."
            ),
        ) from exc


@app.post("/payment/capture-order", response_model=PaymentCaptureResponse)
def capture_payment_order(payload: PaymentCaptureRequest):
    if not payload.order_id:
        raise HTTPException(status_code=400, detail="Order ID is required.")

    settings.reload_paypal()
    if not settings.paypal_credentials_configured() or payload.order_id.startswith("demo-"):
        return PaymentCaptureResponse(
            status="demo",
            order_id=payload.order_id,
            captured=False,
            message="Demo capture is not a real PayPal Sandbox transaction. No live payment was captured.",
        )

    try:
        paypal_data = capture_paypal_order(payload.order_id)
        captured = paypal_data.get("status", "").upper() == "COMPLETED"
        if not captured:
            return PaymentCaptureResponse(
                status="failed",
                order_id=payload.order_id,
                captured=False,
                message="PayPal capture did not complete successfully. The payment was not marked as captured.",
            )

        captured_amount = _extract_paypal_capture_amount(paypal_data)
        captured_currency = _extract_paypal_capture_currency(paypal_data)
        persisted = save_confirmed_payment_transaction(
            order_id=payload.order_id,
            amount=captured_amount,
            currency=captured_currency,
            description=(
                f"PayPal Sandbox payment captured for order {payload.order_id}"
                if captured_amount > 0
                else "PayPal Sandbox payment captured"
            ),
            payer_id=payload.payer_id,
            counterparty="PayPal Sandbox",
        )

        if persisted is None:
            return PaymentCaptureResponse(
                status="captured",
                order_id=payload.order_id,
                captured=True,
                message=(
                    "PayPal Sandbox payment was confirmed, but the local PostgreSQL transaction history could not be updated. "
                    "The payment itself is valid and complete."
                ),
            )

        return PaymentCaptureResponse(
            status="captured",
            order_id=payload.order_id,
            captured=True,
            message="PayPal Sandbox payment captured successfully and recorded in the transaction history.",
        )
    except HTTPException as exc:
        return PaymentCaptureResponse(
            status="failed",
            order_id=payload.order_id,
            captured=False,
            message=(
                "PayPal capture failed. This payment must not be treated as successful. "
                "Verify the Sandbox order ID and the PayPal credentials before retrying."
            ),
        )
    except Exception as exc:
        return PaymentCaptureResponse(
            status="failed",
            order_id=payload.order_id,
            captured=False,
            message=(
                "PayPal capture failed. This payment must not be treated as successful. "
                "Verify the Sandbox order ID and the PayPal credentials before retrying."
            ),
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.BACKEND_HOST, port=settings.BACKEND_PORT, reload=True)
