# Fintech Chatbot with PayPal Sandbox and Daytona deployment

This project is a full-stack fintech assistant built with React, FastAPI, PostgreSQL, and PayPal Sandbox integration. It supports:

- chatbot-style finance answers
- PayPal Sandbox balance retrieval
- recent transaction history with credit/debit classification
- payment order creation and capture workflow
- PostgreSQL-backed dashboard data
- local and Daytona-compatible deployment scripts

## 1. Architecture

### Frontend

- React + Vite
- Dashboard for account balance, recent transactions, alerts, and PayPal status
- Payment form for creating sandbox orders
- Loading/error states for financial data retrieval

### Backend

- FastAPI service
- REST endpoints for chatbot, dashboard, PayPal reporting, and payment operations
- OAuth 2.0 token acquisition against PayPal Sandbox
- secure environment handling via backend/.env

### Database

- PostgreSQL 17
- schema loaded from database/schema.sql
- seeded finance data from database/seed.sql

## 2. Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 17
- Docker + Docker Compose (for Daytona and local container workflow)

## 3. Environment setup

Create backend/.env from the sample file:

```powershell
Set-Location 'D:\newassign\fintech-chatbot\backend'
Copy-Item .env.example .env
```

The sample includes:

```env
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=
PAYPAL_CLIENT_SECRET=
PAYPAL_WEBHOOK_ID=
PAYPAL_RECEIVER_EMAIL=deepsbiswa@yahoo.com
```

Important:

- Never commit .env files.
- Client secret must remain server-side only.
- PayPal Sandbox credentials must be real values from the PayPal Developer Dashboard.

## 4. PostgreSQL setup

```powershell
$env:Path += ';C:\Program Files\PostgreSQL\17\bin'
psql -U postgres -c "CREATE DATABASE fintech_chatbot;"
psql -U postgres -d fintech_chatbot -f D:\newassign\fintech-chatbot\database\schema.sql
psql -U postgres -d fintech_chatbot -f D:\newassign\fintech-chatbot\database\seed.sql
```

## 5. Start locally

### Backend

```powershell
Set-Location 'D:\newassign\fintech-chatbot\backend'
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```powershell
Set-Location 'D:\newassign\fintech-chatbot\frontend'
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

For remote Daytona or containerized preview builds, set `VITE_API_URL=http://host.docker.internal:8000` or the backend preview URL if the frontend is not on the same machine.

## 6. PayPal Sandbox setup

1. Open the PayPal Developer Dashboard.
2. Create a Sandbox app.
3. Copy the REST API Client ID and Secret into backend/.env.
4. Keep PAYPAL_MODE=sandbox.
5. Set PAYPAL_RECEIVER_EMAIL to the sandbox recipient account you want to pay.
6. Confirm the email belongs to a valid sandbox account before attempting a payment.

If the configured account does not expose Reporting API access, the backend clearly returns a demo-mode limitation instead of inventing a balance.

## 7. API endpoints

### Chatbot

- POST /chat
- GET /questions
- GET /health

### Dashboard

- GET /dashboard
- GET /transactions
- GET /alerts

### PayPal

- GET /paypal/balance
- GET /paypal/transactions
- GET /payment/status/{order_id}
- POST /payment/create-order
- POST /payment/capture-order

## 8. Payment workflow

1. User enters a payment amount and currency.
2. Backend creates a PayPal order with the configured recipient email.
3. User approves in the PayPal Sandbox flow.
4. Backend captures the approved order.
5. Transaction is stored in PostgreSQL when confirmation succeeds.
6. Balance data is refreshed from the live reporting API when available.

## 9. Credit / debit classification

The PayPal reporting layer normalizes transaction data and labels it as:

- CREDIT: incoming payment
- DEBIT: outgoing payment

It also keeps status information such as pending, completed, denied, refunded, and reversed.

## 10. Daytona / Unix sandbox deployment

Use the provided Docker Compose stack:

```bash
chmod +x daytona-start.sh
./daytona-start.sh
```

This prepares:

- PostgreSQL
- FastAPI backend
- Vite frontend

The stack exposes:

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- PostgreSQL: localhost:5432

## 11. Tests

Backend tests:

```powershell
Set-Location 'D:\newassign\fintech-chatbot\backend'
.\.venv\Scripts\python.exe -m unittest tests.test_chatbot -q
```

Frontend build check:

```powershell
Set-Location 'D:\newassign\fintech-chatbot\frontend'
npm install
npm run build
```

## 12. Troubleshooting

- If PayPal balance returns 403, enable the Reporting API in the sandbox app and allow a few minutes for the report to refresh.
- If the backend cannot connect to PostgreSQL, confirm the database is running and DB_HOST/DB_PORT values match your environment.
- If the frontend cannot reach the backend, verify VITE_API_URL or the backend host/port.
- If the payment order is declined, confirm the sandbox recipient email is valid and the app credentials are correct.

## 13. Security notes

- Client Secret stays on the backend only.
- Frontend never receives secret material.
- Payment results are only treated as successful after PayPal confirms capture.
- Demo and permission-limited flows are clearly labelled as such.

## 14. Important limitation

Actual PayPal Sandbox payments require a real sandbox account, valid credentials, and explicit user approval. This project does not fabricate balance or payment success data.
