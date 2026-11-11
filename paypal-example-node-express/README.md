# PayPal Checkout Demo

A minimal Express + TypeScript app for a PayPal Checkout flow using the browser SDK and a server-side order creation/capture flow.

## Setup

1. Copy `.env.example` to `.env`.
2. Fill in your PayPal sandbox credentials.
3. Install dependencies:

```bash
npm install
```

4. Run the app:

```bash
npm run dev
```

Then open http://localhost:3000.

## Endpoints

- `GET /api/config` returns the public PayPal client id and environment config
- `POST /api/orders` creates a PayPal order server-side
- `POST /api/orders/:orderId/capture` captures the order

## Notes

This is a demo app intended to show the expected pattern:

- browser calls the backend to create an order
- PayPal UI completes the checkout
- browser calls the backend to capture the order

Do not hardcode prices in the browser. Keep prices on the server.
