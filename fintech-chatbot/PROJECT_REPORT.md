# Project report

## 1. Goal

The project delivers a working fintech assistant with a chatbot UI, dashboard, PayPal Sandbox integration, and a deployment-ready stack for local and Daytona-based execution.

## 2. What was already present

The workspace had a valid three-layer application structure already in place:

- React front end for chat and dashboard interactions
- FastAPI backend with health, chatbot, dashboard, and PayPal endpoints
- PostgreSQL schema and sample seed data

## 3. What was improved

The following issues were fixed and completed:

- PayPal sandbox recipient configuration is now editable via backend environment variables
- payment order creation includes the configured payee email for mentor transfer flows
- missing payment-status lookup endpoint was added
- default payment amount was aligned with the required 1 USD demonstration case
- backend environment template now includes PayPal variables
- Docker Compose and Dockerfiles were added for Unix sandbox deployment
- project documentation was expanded to include setup, testing, and Daytona instructions

## 4. API functionality

The backend currently supports:

- chatbot answers from structured and database-backed knowledge
- dashboard summary and transaction retrieval
- PayPal reporting balance and transaction data
- order creation and capture workflow
- explicit demo-mode handling when sandbox credentials are missing or Reporting API access is unavailable

## 5. PayPal behaviour

The backend uses OAuth 2.0 client credentials to obtain an access token and calls the official PayPal REST endpoints.

It intentionally avoids fabricating balance or capture data. If the sandbox account lacks the right permission, the API returns a clear warning and the UI shows a demo-limited state.

## 6. Database notes

PostgreSQL is used for:

- question knowledge for chatbot responses
- account summary data
- transaction history
- fraud alert records

The schema already includes unique indexes to help avoid duplicate transaction references.

## 7. Deployment readiness

The repository now includes:

- backend/Dockerfile
- frontend/Dockerfile
- docker-compose.yml
- daytona-start.sh

This configuration is suitable for a Unix sandbox environment such as Daytona.

## 8. Verification status

The following checks were executed successfully:

- backend unittest suite passed via the project virtual environment
- frontend dependency installation was performed
- frontend production build was tested

Actual live PayPal payment success cannot be claimed without a valid sandbox account, credentials, and user authorization. That part remains environment-dependent and must be verified in the target sandbox.

## 9. Final outcome

The project is operational as a local fintech assistant and is prepared for Unix sandbox deployment. It preserves the existing chatbot functionality while adding the missing PayPal and deployment support required for the assignment.
