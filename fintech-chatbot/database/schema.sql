CREATE TABLE IF NOT EXISTS questions (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    category TEXT NOT NULL,
    keywords TEXT NOT NULL,
    source_url TEXT,
    last_verified_at DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE INDEX IF NOT EXISTS idx_questions_category
    ON questions (category);

CREATE INDEX IF NOT EXISTS idx_questions_keywords
    ON questions ((lower(keywords)));

CREATE TYPE transaction_type AS ENUM ('credit', 'debit');
CREATE TYPE transaction_status AS ENUM ('normal', 'suspicious', 'under_review', 'flagged');
CREATE TYPE alert_severity AS ENUM ('low', 'medium', 'high', 'critical');

CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    account_name VARCHAR(100) NOT NULL,
    account_number VARCHAR(32) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    balance NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    transaction_type transaction_type NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    description VARCHAR(255) NOT NULL,
    counterparty VARCHAR(255),
    transaction_status transaction_status NOT NULL DEFAULT 'normal',
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    source_type VARCHAR(32) NOT NULL DEFAULT 'manual',
    source_reference VARCHAR(120),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fraud_alerts (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    alert_type VARCHAR(80) NOT NULL,
    severity alert_severity NOT NULL DEFAULT 'medium',
    status VARCHAR(32) NOT NULL DEFAULT 'new',
    message TEXT NOT NULL,
    risk_score INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_account_id
    ON transactions (account_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_fraud_alerts_account_id
    ON fraud_alerts (account_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_accounts_account_number
    ON accounts (account_number);

CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_source_reference
    ON transactions (source_reference)
    WHERE source_reference IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_fraud_alerts_transaction_id
    ON fraud_alerts (transaction_id)
    WHERE transaction_id IS NOT NULL;

INSERT INTO accounts (account_name, account_number, currency, balance)
VALUES ('Primary Operating Account', '**** 4876', 'USD', 5000.00)
ON CONFLICT (account_number) DO NOTHING;

INSERT INTO transactions (account_id, transaction_type, amount, description, counterparty, transaction_status, is_demo, source_type, source_reference, occurred_at)
VALUES
    (1, 'credit', 4300.00, 'Client payment received', 'Northwind Labs', 'normal', false, 'paypal_sandbox', 'PP-INV-001', NOW() - INTERVAL '2 days'),
    (1, 'debit', 1200.00, 'Vendor payout', 'CloudOps Services', 'normal', false, 'manual', 'VENDOR-912', NOW() - INTERVAL '1 day'),
    (1, 'credit', 6100.00, 'Incoming transfer', 'Customer settlement', 'suspicious', false, 'manual', 'IN-4421', NOW() - INTERVAL '8 hours'),
    (1, 'debit', 3200.00, 'Card payment', 'Card ending 7421', 'normal', false, 'manual', 'CARD-552', NOW() - INTERVAL '5 hours'),
    (1, 'debit', 1800.00, 'Repeated transfer', 'Unknown merchant', 'flagged', true, 'demo', 'demo-001', NOW() - INTERVAL '30 minutes')
ON CONFLICT (source_reference) WHERE source_reference IS NOT NULL DO NOTHING;

INSERT INTO fraud_alerts (account_id, transaction_id, alert_type, severity, status, message, risk_score)
VALUES
    (1, 5, 'repeated_transaction', 'high', 'new', 'Multiple transfers were detected within a short period of time.', 82),
    (1, 3, 'unexpected_incoming_payment', 'medium', 'under_review', 'Large inbound transfer outside the customer’s normal patterns.', 71)
ON CONFLICT (transaction_id) WHERE transaction_id IS NOT NULL DO NOTHING;
