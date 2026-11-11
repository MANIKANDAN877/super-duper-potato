import express from "express";
import dotenv from "dotenv";
import path from "node:path";
import { fileURLToPath } from "node:url";

dotenv.config();

const app = express();
const PORT = Number(process.env.PORT ?? 3000);
const PAYPAL_ENV = process.env.PAYPAL_ENV === "live" ? "live" : "sandbox";
const PAYPAL_BASE_URL =
  PAYPAL_ENV === "live"
    ? "https://api-m.paypal.com"
    : "https://api-m.sandbox.paypal.com";
const PAYPAL_CLIENT_ID = process.env.PAYPAL_CLIENT_ID ?? "";
const PAYPAL_CLIENT_SECRET = process.env.PAYPAL_CLIENT_SECRET ?? "";
const HAS_PAYPAL_CREDENTIALS = Boolean(
  PAYPAL_CLIENT_ID && PAYPAL_CLIENT_SECRET,
);

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const publicDir = path.resolve(__dirname, "../public");

const catalog = {
  "demo-product": {
    id: "demo-product",
    name: "Demo Product",
    price: 9.99,
    currency: "USD",
  },
};

const orders = new Map<
  string,
  { itemId: string; amount: string; currency: string }
>();

function getPaypalAuthHeader(): string {
  return `Basic ${Buffer.from(`${PAYPAL_CLIENT_ID}:${PAYPAL_CLIENT_SECRET}`).toString("base64")}`;
}

app.use(express.json());
app.use(express.static(publicDir));

app.get("/api/config", (_req, res) => {
  if (!HAS_PAYPAL_CREDENTIALS) {
    return res.status(500).json({
      error:
        "PayPal credentials are missing. Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to .env.",
    });
  }

  return res.json({
    clientId: PAYPAL_CLIENT_ID,
    env: PAYPAL_ENV,
    sdkUrl: `https://www.paypal.com/sdk/js?client-id=${PAYPAL_CLIENT_ID}&currency=USD&components=buttons`,
  });
});

app.post("/api/orders", async (req, res) => {
  const { itemId } = req.body ?? {};
  const item = catalog[itemId as keyof typeof catalog];

  if (!item) {
    return res.status(400).json({ error: "Unknown itemId." });
  }

  try {
    const response = await fetch(`${PAYPAL_BASE_URL}/v2/checkout/orders`, {
      method: "POST",
      headers: {
        Authorization: getPaypalAuthHeader(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        intent: "CAPTURE",
        purchase_units: [
          {
            amount: {
              currency_code: item.currency,
              value: item.price.toFixed(2),
            },
            description: item.name,
          },
        ],
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      return res.status(response.status).json(data);
    }

    orders.set(data.id, {
      itemId: item.id,
      amount: item.price.toFixed(2),
      currency: item.currency,
    });

    return res.json({ id: data.id });
  } catch (error) {
    console.error("Create order error:", error);
    return res.status(500).json({ error: "Failed to create PayPal order." });
  }
});

app.post("/api/orders/:orderId/capture", async (req, res) => {
  const { orderId } = req.params;

  try {
    const response = await fetch(
      `${PAYPAL_BASE_URL}/v2/checkout/orders/${orderId}/capture`,
      {
        method: "POST",
        headers: {
          Authorization: getPaypalAuthHeader(),
          "Content-Type": "application/json",
        },
      },
    );

    const data = await response.json();

    if (!response.ok) {
      return res.status(response.status).json(data);
    }

    orders.delete(orderId);

    return res.json(data);
  } catch (error) {
    console.error("Capture order error:", error);
    return res.status(500).json({ error: "Failed to capture PayPal order." });
  }
});

app.get("*", (_req, res) => {
  res.sendFile(path.join(publicDir, "index.html"));
});

app.listen(PORT, () => {
  if (!HAS_PAYPAL_CREDENTIALS) {
    console.warn(
      "PayPal credentials are missing. Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to the .env file.",
    );
  }

  console.log(`Server listening on http://localhost:${PORT}`);
});
