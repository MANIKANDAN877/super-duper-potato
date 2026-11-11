import { useEffect, useRef, useState } from "react";
import "./App.css";

const DEFAULT_SUGGESTIONS = [
  "What is a business loan?",
  "What is an MSME loan?",
  "Explain my account breakdown.",
  "What is the percentage distribution of debits, credits, fees, and penalties in my account?",
  "Why am I paying fees and penalties on my account?",
  "How can I save money each month?",
];

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

function ChartPanel({ chart }) {
  if (!chart || !Array.isArray(chart.items)) {
    return null;
  }

  return (
    <div className="chart-panel">
      <h3>{chart.title}</h3>
      {chart.items.map((item) => (
        <div key={item.label} className="chart-row">
          <div className="chart-meta">
            <span
              className="chart-swatch"
              style={{ backgroundColor: item.color || "#38bdf8" }}
            />
            <span>{item.label}</span>
          </div>
          <div className="chart-bar-track">
            <div
              className="chart-bar-fill"
              style={{
                width: `${item.value}%`,
                background: item.color || "#38bdf8",
              }}
            />
          </div>
          <span className="chart-value">{item.value}%</span>
        </div>
      ))}
    </div>
  );
}

function PaymentPage() {
  const [amount, setAmount] = useState("1.00");
  const [currency, setCurrency] = useState("USD");
  const [status, setStatus] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [approvalUrl, setApprovalUrl] = useState("");
  const [orderId, setOrderId] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const payerId = params.get("PayerID") || params.get("payerId");
    const pendingOrderId = sessionStorage.getItem("pendingPayPalOrderId");

    if (!token || !pendingOrderId) {
      return;
    }

    const completeCapturedPayment = async () => {
      setStatus("PayPal approved the sandbox payment. Capturing the order...");

      try {
        const response = await fetch(`${API_URL}/payment/capture-order`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            order_id: pendingOrderId,
            payer_id: payerId || "",
          }),
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Unable to capture the payment.");
        }

        setOrderId(pendingOrderId);
        setStatus(data.message || "Payment capture status received.");
        sessionStorage.removeItem("pendingPayPalOrderId");
      } catch (error) {
        setOrderId(pendingOrderId);
        setStatus(error.message || "Payment capture failed.");
        sessionStorage.removeItem("pendingPayPalOrderId");
      }
    };

    completeCapturedPayment();
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setStatus("");
    setApprovalUrl("");
    setOrderId("");
    setIsSubmitting(true);

    try {
      const response = await fetch(`${API_URL}/payment/create-order`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          amount,
          currency,
          description: "Fintech service payment",
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Unable to create the payment order.");
      }

      const nextOrderId = data.order_id || "";
      setApprovalUrl(data.approval_url || "");
      setOrderId(nextOrderId);
      setStatus(
        `${data.message}${data.approval_url ? " Redirecting to PayPal Sandbox to complete payment." : ""}`,
      );

      if (data.approval_url) {
        if (nextOrderId) {
          sessionStorage.setItem("pendingPayPalOrderId", nextOrderId);
        }
        window.location.href = data.approval_url;
      }
    } catch (error) {
      setStatus(error.message || "Payment request failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCapture = async () => {
    if (!orderId) {
      setStatus("Create an order first before capturing a payment.");
      return;
    }

    setStatus("Capturing payment...");

    try {
      const response = await fetch(`${API_URL}/payment/capture-order`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ order_id: orderId }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Unable to capture the payment.");
      }

      setStatus(data.message || "Payment capture status received.");
    } catch (error) {
      setStatus(error.message || "Payment capture failed.");
    }
  };

  return (
    <div className="payment-panel">
      <div className="payment-header">
        <p className="eyebrow">Secure payment</p>
        <h2>Pay for a service</h2>
      </div>

      <form className="payment-form" onSubmit={handleSubmit}>
        <div className="recipient-banner">Recipient: deepsbiswa@yahoo.com</div>
        <label>
          Amount
          <input
            type="number"
            min="1"
            step="0.01"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            placeholder="1.00"
          />
        </label>

        <label>
          Currency
          <select
            value={currency}
            onChange={(event) => setCurrency(event.target.value)}
          >
            <option value="USD">USD ($) - PayPal Sandbox</option>
            <option value="EUR">EUR (€) - PayPal Sandbox</option>
            <option value="INR">INR (₹) - Demo Mode</option>
          </select>
        </label>

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Processing..." : "Create Payment Order"}
        </button>
      </form>

      {approvalUrl ? (
        <div className="payment-actions">
          <a
            href={approvalUrl}
            target="_blank"
            rel="noreferrer"
            className="paypal-link"
          >
            Continue to PayPal
          </a>
          <button type="button" className="capture-btn" onClick={handleCapture}>
            Capture Payment
          </button>
        </div>
      ) : orderId ? (
        <div className="payment-actions">
          <button type="button" className="capture-btn" onClick={handleCapture}>
            Capture Demo Payment
          </button>
        </div>
      ) : null}

      {orderId && <div className="order-id">Order ID: {orderId}</div>}
      {status && <div className="payment-status">{status}</div>}
    </div>
  );
}

function PayPalReportingPanel({
  balances = [],
  transactions = [],
  isLoading,
  error,
  onRefresh,
  reportingNotice,
}) {
  const formatMoney = (currency, value) => {
    const numericValue = Number(value || 0);
    return `${currency} ${numericValue.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  };

  return (
    <div className="paypal-report-panel">
      <div className="report-header">
        <div>
          <p className="eyebrow">PayPal Sandbox reporting</p>
          <h3>Reporting account balance and transaction history</h3>
        </div>
        <button
          type="button"
          className="report-refresh-btn"
          onClick={onRefresh}
        >
          Refresh
        </button>
      </div>

      {reportingNotice && <div className="info-banner">{reportingNotice}</div>}

      {error && <div className="error-banner">{error}</div>}

      {isLoading ? (
        <div className="empty-state">Loading PayPal report data...</div>
      ) : balances.length === 0 && transactions.length === 0 ? (
        <div className="empty-state">
          No PayPal Sandbox reporting data is available yet. Check whether the
          Reporting API permission is enabled and allow a few minutes for the
          balance and transaction report to refresh.
        </div>
      ) : (
        <>
          <div className="report-balance-grid">
            {balances.map((balance) => (
              <div
                key={`${balance.currency}-${balance.is_primary ? "primary" : "secondary"}`}
                className="summary-card"
              >
                <span>
                  {balance.is_primary ? "Primary balance" : "Available balance"}
                </span>
                <strong>
                  {formatMoney(balance.currency, balance.available_balance)}
                </strong>
                <small>
                  Total: {formatMoney(balance.currency, balance.total_balance)}
                </small>
                <small>
                  Last refresh:{" "}
                  {balance.last_refresh_time || "Not yet reported"}
                </small>
              </div>
            ))}
          </div>

          <div className="paypal-transaction-block">
            <h4>Recent PayPal transactions</h4>
            <div className="transaction-list">
              {transactions.map((transaction) => (
                <div
                  key={transaction.transaction_id}
                  className={`transaction-row ${transaction.direction === "credit" ? "credit" : "debit"}`}
                >
                  <div>
                    <div className="transaction-title">
                      {transaction.transaction_id}
                    </div>
                    <div className="transaction-meta">
                      {transaction.transaction_date || "Date unavailable"} ·{" "}
                      {transaction.status}
                    </div>
                  </div>
                  <div className="transaction-side">
                    <div
                      className={`transaction-amount ${transaction.direction === "credit" ? "credit" : "debit"}`}
                    >
                      {transaction.direction === "credit" ? "+" : "-"}
                      {formatMoney(transaction.currency, transaction.amount)}
                    </div>
                    <small>
                      {transaction.direction === "credit"
                        ? "Incoming"
                        : "Outgoing"}
                    </small>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function PayoutPanel({ accountDetails }) {
  const [recipientEmail, setRecipientEmail] = useState("friend@example.com");
  const [amount, setAmount] = useState("1.00");
  const [currency, setCurrency] = useState("USD");
  const [note, setNote] = useState("Sandbox payout to friend");
  const [statusText, setStatusText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    setIsSubmitting(true);
    setStatusText("");

    try {
      const response = await fetch(`${API_URL}/paypal/payout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          recipient_email: recipientEmail,
          amount,
          currency,
          note,
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || "Unable to submit the sandbox payout.");
      }

      const displayStatus =
        data.actual_paypal_status || data.status || "SUBMITTED";
      setStatusText(
        `${data.message || "Payout submitted."} Actual PayPal status: ${displayStatus}.`,
      );
    } catch (error) {
      setStatusText(error.message || "Unable to submit the payout.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const connectedEmail =
    accountDetails?.business_account?.email ||
    "Connected business account unavailable";
  const connectedStatus = accountDetails?.business_account?.status || "unknown";
  const connectedCountry =
    accountDetails?.business_account?.country ||
    accountDetails?.country ||
    "UNKNOWN";
  const payoutEligibilityMessage =
    accountDetails?.account_status ||
    "PayPal payout eligibility is not yet confirmed.";
  const payoutsBlocked =
    /not yet confirmed|not eligible|disabled|blocked/i.test(
      payoutEligibilityMessage,
    ) || !payoutEligibilityMessage;

  return (
    <div className="paypal-report-panel">
      <div className="report-header">
        <div>
          <p className="eyebrow">Sandbox payout</p>
          <h3>Send money to friend</h3>
        </div>
      </div>

      <div className="info-banner">
        Connected account: {connectedEmail} · Status: {connectedStatus} ·
        Country: {connectedCountry} · Eligibility: {payoutEligibilityMessage}
      </div>

      <div className="payment-form">
        <label>
          Recipient email
          <input
            type="email"
            value={recipientEmail}
            onChange={(event) => setRecipientEmail(event.target.value)}
          />
        </label>

        <label>
          Amount
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </label>

        <label>
          Currency
          <select
            value={currency}
            onChange={(event) => setCurrency(event.target.value)}
          >
            <option value="USD">USD</option>
            <option value="EUR">EUR</option>
            <option value="GBP">GBP</option>
          </select>
        </label>

        <label>
          Note
          <input
            type="text"
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>

        <button
          type="button"
          onClick={handleSubmit}
          disabled={isSubmitting || payoutsBlocked}
        >
          {isSubmitting
            ? "Submitting payout..."
            : payoutsBlocked
              ? "Payout blocked"
              : "Send payout"}
        </button>
      </div>

      {statusText && <div className="payment-status">{statusText}</div>}
    </div>
  );
}

function DashboardPanel({
  dashboard,
  isLoading,
  error,
  paypalBalance,
  paypalTransactions,
  paypalLoading,
  paypalError,
  onRefreshPayPalData,
}) {
  if (isLoading) {
    return (
      <div className="dashboard-panel">
        <div className="empty-state">Loading dashboard...</div>
      </div>
    );
  }

  if (!dashboard || !dashboard.account) {
    return (
      <div className="dashboard-panel">
        <div className="empty-state">Dashboard data is unavailable.</div>
      </div>
    );
  }

  const {
    account,
    summary,
    transactions = [],
    alerts = [],
    fraud_summary = {},
    risk_analysis = [],
  } = dashboard;

  return (
    <div className="dashboard-panel">
      <div className="dashboard-header">
        <div>
          <p className="eyebrow">Fraud control</p>
          <h2>{account.account_name}</h2>
        </div>
        <div className="account-pill">
          {account.account_number} · {account.currency}
        </div>
      </div>

      <div className="summary-grid">
        <div className="summary-card balance-card">
          <span>Account balance</span>
          <strong>
            {account.currency}{" "}
            {Number(summary.balance || 0).toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </strong>
        </div>
        <div className="summary-card">
          <span>Total credits</span>
          <strong>
            {account.currency}{" "}
            {Number(summary.total_credits || 0).toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </strong>
        </div>
        <div className="summary-card">
          <span>Total debits</span>
          <strong>
            {account.currency}{" "}
            {Number(summary.total_debits || 0).toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </strong>
        </div>
        <div className="summary-card">
          <span>Open alerts</span>
          <strong>{summary.alerts_count || 0}</strong>
        </div>
        <div className="summary-card risk-card">
          <span>Suspicious</span>
          <strong>{fraud_summary.suspicious_transactions || 0}</strong>
        </div>
        <div className="summary-card risk-card">
          <span>High risk</span>
          <strong>{fraud_summary.high_risk_transactions || 0}</strong>
        </div>
        <div className="summary-card risk-card">
          <span>Pending review</span>
          <strong>{fraud_summary.pending_reviews || 0}</strong>
        </div>
      </div>

      <div className="dashboard-grid">
        <section className="panel-block">
          <h3>Recent financial activity</h3>
          <div className="transaction-list">
            {transactions.slice(0, 6).map((transaction) => (
              <div key={transaction.id} className="transaction-row">
                <div>
                  <div className="transaction-title">
                    {transaction.description}
                  </div>
                  <div className="transaction-meta">
                    {transaction.counterparty || "Internal transfer"} ·{" "}
                    {transaction.source_type}
                  </div>
                </div>
                <div
                  className={`transaction-amount ${transaction.transaction_type === "credit" ? "credit" : "debit"}`}
                >
                  {transaction.transaction_type === "credit" ? "+" : "-"}
                  {account.currency}{" "}
                  {Number(transaction.amount || 0).toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel-block">
          <h3>Fraud alerts</h3>
          <div className="alert-list">
            {alerts.length === 0 ? (
              <div className="empty-state">No active fraud alerts.</div>
            ) : (
              alerts.map((alert) => (
                <div
                  key={alert.id}
                  className={`alert-row severity-${alert.severity || "medium"}`}
                >
                  <div className="alert-head">
                    <span className="alert-tag">{alert.alert_type}</span>
                    <span className="alert-status">{alert.status}</span>
                  </div>
                  <p>{alert.message}</p>
                  <small>Risk score: {alert.risk_score}</small>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      <section className="panel-block risk-panel">
        <h3>Risk analysis</h3>
        {risk_analysis.length === 0 ? (
          <div className="empty-state">
            No recent risk assessments available.
          </div>
        ) : (
          <div className="risk-list">
            {risk_analysis.map((item) => (
              <div key={item.transaction_id} className="risk-item">
                <div>
                  <div className="transaction-title">
                    Transaction #{item.transaction_id}
                  </div>
                  <div className="transaction-meta">{item.review_status}</div>
                </div>
                <div className="risk-score-wrap">
                  <span
                    className={`risk-badge risk-${String(item.risk_level).toLowerCase()}`}
                  >
                    {item.risk_level}
                  </span>
                  <strong>{item.risk_score}</strong>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <PayPalReportingPanel
        balances={paypalBalance?.balances || []}
        transactions={paypalTransactions?.transactions || []}
        isLoading={paypalLoading}
        error={paypalError}
        onRefresh={onRefreshPayPalData}
        reportingNotice={
          paypalBalance?.reporting_delay_notice ||
          paypalTransactions?.reporting_delay_notice ||
          "This section shows external PayPal Sandbox Reporting data, not the local PostgreSQL account ledger."
        }
      />

      <PayoutPanel accountDetails={paypalBalance} />

      {error && <div className="error-banner">{error}</div>}
    </div>
  );
}

function App() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: "bot",
      text: "Hello! I am the Eazily Done financial assistant. I can help with account breakdowns, fee explanations, savings guidance, business loans, MSME loans, eligibility, interest rates, and required documents.",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState("");
  const [dashboardData, setDashboardData] = useState(null);
  const [paypalBalance, setPaypalBalance] = useState({ balances: [] });
  const [paypalTransactions, setPaypalTransactions] = useState({
    transactions: [],
  });
  const [paypalLoading, setPaypalLoading] = useState(false);
  const [paypalError, setPaypalError] = useState("");
  const [error, setError] = useState("");
  const [suggestions, setSuggestions] = useState(DEFAULT_SUGGESTIONS);
  const [view, setView] = useState("dashboard");
  const endOfMessagesRef = useRef(null);

  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading, view]);

  const loadPaypalReporting = async () => {
    setPaypalLoading(true);
    setPaypalError("");

    try {
      const [balanceResponse, transactionResponse] = await Promise.all([
        fetch(`${API_URL}/paypal/balance`),
        fetch(`${API_URL}/paypal/transactions`),
      ]);

      const balanceData = await balanceResponse.json().catch(() => ({}));
      const transactionData = await transactionResponse
        .json()
        .catch(() => ({}));

      if (!balanceResponse.ok && balanceData.detail) {
        throw new Error(balanceData.detail);
      }

      if (!transactionResponse.ok && transactionData.detail) {
        throw new Error(transactionData.detail);
      }

      setPaypalBalance(balanceData || { balances: [] });
      setPaypalTransactions(transactionData || { transactions: [] });
    } catch (error) {
      setPaypalError(
        error.message ||
          "PayPal Sandbox reporting is unavailable. Check the Reporting API permission and try again later.",
      );
      setPaypalBalance({ balances: [] });
      setPaypalTransactions({ transactions: [] });
    } finally {
      setPaypalLoading(false);
    }
  };

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        setDashboardLoading(true);
        const response = await fetch(`${API_URL}/dashboard`);
        if (!response.ok) {
          throw new Error("Unable to load the fraud dashboard.");
        }
        const data = await response.json();
        setDashboardData(data);
      } catch (err) {
        setDashboardError(err.message || "Dashboard unavailable.");
      } finally {
        setDashboardLoading(false);
      }
    };

    const loadSuggestions = async () => {
      try {
        const response = await fetch(`${API_URL}/questions`);
        if (!response.ok) {
          return;
        }
        const data = await response.json();
        if (Array.isArray(data.questions) && data.questions.length > 0) {
          const nextSuggestions = data.questions
            .slice(0, 5)
            .map((item) => item.question);
          setSuggestions(nextSuggestions);
        }
      } catch (error) {
        console.error("Failed to load suggestions", error);
      }
    };

    loadDashboard();
    loadSuggestions();
    loadPaypalReporting();
  }, []);

  const addMessage = (sender, text, chart = null) => {
    setMessages((current) => [
      ...current,
      {
        id: Date.now() + Math.random(),
        sender,
        text,
        chart,
      },
    ]);
  };

  const handleSubmit = async (questionText = input) => {
    const trimmedQuestion = questionText.trim();
    if (!trimmedQuestion || isLoading) {
      return;
    }

    setInput("");
    setError("");
    addMessage("user", trimmedQuestion);
    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: trimmedQuestion }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(
          errorData.detail || "Unable to reach the chatbot service right now.",
        );
      }

      const data = await response.json();
      addMessage("bot", data.answer, data.chart || null);
    } catch (err) {
      const message = err.message || "Something went wrong. Please try again.";
      setError(message);
      addMessage(
        "bot",
        "The service is temporarily unavailable. Please check whether the backend is running and try again, or ask a simpler finance question such as business loan eligibility or account fees.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const clearChat = () => {
    setMessages([
      {
        id: 1,
        sender: "bot",
        text: "Chat cleared. Ask me about business loans, MSME loans, eligibility, interest rates, fees, penalties, or savings guidance.",
      },
    ]);
    setError("");
  };

  return (
    <div className="app-shell">
      <div className="chat-card">
        <header className="topbar">
          <div>
            <p className="eyebrow">Eazily Done</p>
            <h1>Fraud Monitoring Dashboard</h1>
          </div>
          <div className="topbar-actions">
            <button
              className={`nav-btn ${view === "dashboard" ? "is-active" : ""}`}
              onClick={() => setView("dashboard")}
              type="button"
            >
              Dashboard
            </button>
            <button
              className={`nav-btn ${view === "chat" ? "is-active" : ""}`}
              onClick={() => setView("chat")}
              type="button"
            >
              Chatbot
            </button>
            <button
              className={`nav-btn ${view === "payment" ? "is-active" : ""}`}
              onClick={() => setView("payment")}
              type="button"
            >
              Payment
            </button>
            {view === "chat" && (
              <button className="clear-btn" onClick={clearChat} type="button">
                Clear chat
              </button>
            )}
          </div>
        </header>

        {view === "dashboard" ? (
          <DashboardPanel
            dashboard={dashboardData}
            isLoading={dashboardLoading}
            error={dashboardError}
            paypalBalance={paypalBalance}
            paypalTransactions={paypalTransactions}
            paypalLoading={paypalLoading}
            paypalError={paypalError}
            onRefreshPayPalData={loadPaypalReporting}
          />
        ) : view === "chat" ? (
          <>
            <div className="chip-row">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  className="chip"
                  onClick={() => handleSubmit(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>

            <main className="message-panel" aria-live="polite">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`message-row ${message.sender === "user" ? "is-user" : "is-bot"}`}
                >
                  <div className="message-bubble">
                    <div>{message.text}</div>
                    {message.chart && <ChartPanel chart={message.chart} />}
                  </div>
                </div>
              ))}

              {isLoading && (
                <div className="message-row is-bot">
                  <div
                    className="message-bubble typing-bubble"
                    aria-label="Loading response"
                  >
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                </div>
              )}

              {error && <div className="error-banner">{error}</div>}
              <div ref={endOfMessagesRef} />
            </main>

            <form
              className="composer"
              onSubmit={(event) => {
                event.preventDefault();
                handleSubmit();
              }}
            >
              <input
                type="text"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Ask about account breakdowns, debit and credit percentages, fees, penalties, or account services..."
                aria-label="Ask a question"
              />
              <button type="submit" disabled={isLoading || !input.trim()}>
                {isLoading ? "Sending..." : "Send"}
              </button>
            </form>
          </>
        ) : (
          <PaymentPage />
        )}
      </div>
    </div>
  );
}

export default App;
