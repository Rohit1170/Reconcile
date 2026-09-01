# Reconcile

A revenue reconciliation SaaS app: upload `orders.csv` (what the store believes it
sold) and `payments.csv` (what the payment processor actually charged/refunded),
and the backend deterministically compares them, classifies every discrepancy,
and computes how much money is at risk. Groq is used only to *explain* results
the deterministic engine already produced -- it never decides whether records
match.

## Overview

- Sign up / log in with a JWT-protected account.
- Upload your own `orders.csv` + `payments.csv`, or load a demo dataset.
- A deterministic Python engine (no LLM) matches orders to payments by
  `order_id` and classifies each into one of 9 categories.
- A dashboard shows totals, matched/disputed value, and money at risk.
- A discrepancies table supports search, filtering, and pagination, with a
  detail view per discrepancy.
- Groq (Llama 3, via the backend only) explains a discrepancy or a batch of
  selected discrepancies in plain English, given the deterministic result.

## Architecture

```
Next.js (TypeScript, Tailwind)
        |  REST + JWT bearer token
        v
FastAPI (Python)
   |                  |
   v                  v
MongoDB            Groq API
(users, datasets,  (explanation only,
 orders, payments,  never matching)
 reconciliations)
```

- **Frontend**: Next.js App Router, TypeScript, Tailwind (the v0-generated
  visual design was kept and extended, not rewritten), Recharts for the
  discrepancy chart.
- **Backend**: FastAPI with plain functions and routers -- no service/repository
  layers, no dependency-injection framework, no background job queue. Every
  route is readable top to bottom.
- **Database**: MongoDB via PyMongo. Every user-owned document carries
  `user_id`, and every query for that data is scoped to the JWT's user id
  (see `backend/auth.py::get_current_user`). This is the entire authorization
  model.
- **LLM**: Groq, called only from FastAPI (`backend/routes/ai.py`), never from
  the browser.

## Local setup

Requires: Node 18+, **Python 3.12** (3.14 is too new for some pinned wheels
as of this writing -- see Troubleshooting), and a local MongoDB.

### 1. MongoDB

```bash
mongod --dbpath <some-empty-directory> --port 27017
```

Any local MongoDB works; a free MongoDB Atlas cluster works too -- just point
`MONGODB_URI` at it.

### 2. Backend

```bash
cd backend
py -3.12 -m venv venv          # or: python3.12 -m venv venv
venv\Scripts\activate          # Windows; on macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # macOS/Linux: cp .env.example .env
# edit .env: set GROQ_API_KEY if you want live AI explanations (optional --
# the app degrades gracefully to a fallback response without it)
uvicorn main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`. Health check: `GET /health`.

### 3. Frontend

```bash
npm install
copy .env.example .env.local   # macOS/Linux: cp .env.example .env.local
npm run dev
```

Frontend `.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Frontend runs at `http://localhost:3000`.

### 4. Try it

Sign up, then on the Upload page either upload your own `orders.csv` /
`payments.csv` or click **Load demo data**. You're redirected to the
dashboard once reconciliation finishes.

### Backend tests

```bash
cd backend
venv\Scripts\activate
pytest -v
```

27 tests. The reconciliation-engine and CSV-parser tests are pure unit tests
(no DB). The API tests (`test_api_auth_isolation.py`) spin up the FastAPI app
against a real local MongoDB (database `reconcile_test`, auto-cleaned) -- a
`mongod` must be running for those to pass.

## Reconciliation logic

All of this lives in `backend/reconciliation.py`, with the same explanation
in code comments there.

### Matching strategy

`order_id` is the only reliable identifier shared between the two files
(every payment references the order it was collected for), so it's the sole
join key. For each `order_id`, records are classified using this priority --
**first applicable rule wins**:

1. **DUPLICATE_ORDER** -- the order_id appears more than once in `orders.csv`
2. **DUPLICATE_PAYMENT** -- the order_id has more than one payment row
3. **MISSING_PAYMENT** -- an order has zero matching payments
4. **UNKNOWN_PAYMENT** -- a payment's order_id matches no order
5. **REFUND_CHARGE_ISSUE** -- payment is refunded but the order isn't marked
   refunded/cancelled (the books disagree about whether the sale still stands)
6. **CURRENCY_MISMATCH** -- order and payment currencies differ
7. **AMOUNT_MISMATCH** -- `|order.amount - payment.amount| > 0.01`
8. **ROUNDING_DIFFERENCE** -- `0 < difference <= 0.01`
9. **MATCHED** -- everything lines up

**Why duplicates are checked first**: a duplicate is a data-integrity problem
independent of whether amounts happen to match -- classifying a duplicate
order as anything else (e.g. "matched" because one of the two rows happens to
line up with a payment) would hide the real issue. Everything else follows
from there in order of "can I even find a clean pair" before "does the pair's
data agree."

**Why refund status is checked before amount**: a refunded payment against a
still-open order is a status conflict regardless of whether the dollar
amounts happen to match -- the concerning fact is that the books disagree
about whether money is owed, not the size of any residual difference.

### Normalization (`backend/csv_parser.py`)

Column names are matched case-insensitively and whitespace-tolerant. Values
are cleaned but never reinterpreted: amounts strip `$`/commas/accounting
parens and parse as `Decimal` (never `float`, to avoid binary rounding
artifacts); currency is upper-cased; IDs are kept as strings (never coerced
to numbers); status is lower-cased; blank rows are skipped; a row with a bad
amount or missing required field is skipped and logged, not silently guessed
at or dropped without a trace. The original CSV row is kept under `raw` on
every parsed record for audit.

### Tolerance

`ROUNDING_TOLERANCE = 0.01` (one cent). Card processors and currency
conversion routinely introduce sub-cent noise; a 1-cent tolerance absorbs
that without hiding a genuine mismatch. All money math uses `Decimal`.

### Duplicate handling

A duplicate order/payment group is classified **once**, not once per
duplicate row, with financial impact = the amount of the *extra* rows beyond
the first. This is what keeps a duplicate from being double-counted against
money-at-risk.

### Refund handling

A refunded payment is only a discrepancy if the order doesn't already
reflect it (see priority #5 above). If the order is also marked
`refunded`/`cancelled`, that's `MATCHED` -- both sides agree.

### Priority

Priority is derived from financial impact, uniformly across categories
(rounding differences are always forced to `LOW` since they're immaterial by
definition):

| Impact | Priority |
|---|---|
| >= 500 | CRITICAL |
| >= 100 | HIGH |
| >= 10 | MEDIUM |
| < 10 | LOW |

### Money-at-risk calculation

Because every `order_id` is classified into exactly one category, every
dollar is counted at most once -- there's no separate "double counting" rule
needed; it falls out of the one-row-per-order_id design.

- **matched_value** -- payment amount for rows classified `MATCHED` or
  `ROUNDING_DIFFERENCE` (money that genuinely settled)
- **disputed_value** -- order/payment amount involved in every other
  category (how much revenue is "in question")
- **money_at_risk** -- sum of `financial_impact` across those same rows (the
  actual dollar exposure; always <= disputed_value, since e.g. an
  `AMOUNT_MISMATCH` disputes the *full* order amount but only the
  *difference* is actually at risk)

## What was found in the supplied data

**No `orders.csv` / `payments.csv` were supplied with this assignment.**
`backend/sample_data/orders.csv` and `payments.csv` are synthetic data
generated for this project (`backend/sample_data/generate_sample_data.py`,
deterministic, no randomness) so the demo button and tests have something
real to run against end to end. Real supplied files can be dropped into
`backend/sample_data/` at any time and `POST /datasets/demo` will pick them
up automatically -- see `backend/sample_data/README.md`.

Actual output of running the reconciliation engine against that synthetic
dataset (`POST /datasets/demo` -> `POST /reconciliation/run/{id}` ->
`GET /reconciliation/{id}/summary`, values below are real, not invented):

- **22 orders**, **20 payments** imported
- **Total order value**: $3,718.58 -- **Total payment value**: $3,460.59
- **Matched value**: $2,879.59 (14 of 23 rows: 13 exact matches + 1 rounding
  difference)
- **Disputed value**: $883.00 -- **Money at risk**: $675.00
- Discrepancies by category (9 total):
  - `AMOUNT_MISMATCH`: 2 ($27.00 impact)
  - `CURRENCY_MISMATCH`: 1 ($65.00 impact -- an order in EUR paid in USD)
  - `DUPLICATE_ORDER`: 1 ($40.00 impact)
  - `DUPLICATE_PAYMENT`: 1 ($30.00 impact -- a customer was charged twice)
  - `MISSING_PAYMENT`: 2 ($249.00 impact -- orders with no processor record)
  - `REFUND_CHARGE_ISSUE`: 1 ($220.00 impact -- refunded on the processor
    side, order never updated)
  - `UNKNOWN_PAYMENT`: 1 ($44.00 impact -- a payment referencing an order
    that doesn't exist)
  - `ROUNDING_DIFFERENCE`: 1 ($0.00 impact, immaterial by definition)

**What this means for the business** (reading the synthetic data as if it
were real, for illustration): out of $3,719 in recorded orders, $675 (about
18%) is in categories that represent real financial exposure -- two orders
with no payment at all ($249, the largest single risk), a $220 refund the
order records never caught up to, and a $30 duplicate charge that likely
needs a customer refund. The $65 currency mismatch and $27 in amount
mismatches are smaller but still worth a manual look. None of this required
guessing -- every number above came directly from the deterministic engine.

## LLM approach

Groq is used *only* to narrate a result the deterministic engine already
produced -- see `backend/routes/ai.py`. It is never in the matching path
(`backend/reconciliation.py` has no network calls, no LLM imports, and is
fully covered by pure unit tests that don't need Groq to run).

**Prompt structure**: the system prompt tells the model the category,
amounts, and match/no-match status are already final facts it must not
contradict; the user prompt hands it the discrepancy's category, priority,
deterministic reason, order/payment records, difference, and financial
impact (single-discrepancy `/ai/explain`) or a list of the same for every
selected discrepancy plus their total impact (`/ai/analyze`). The model is
asked to return **only** a JSON object with `what_happened`, `likely_cause`,
`recommended_action` -- a Groq `response_format: json_object` request keeps
this a structured call rather than free text to parse with regex.

**Temperature = 0.2** (`GROQ_MODEL`/temperature configurable via `.env`):
low temperature is used because this is an explanation/summarization task
where consistent phrasing is preferable to creative variation. This does
**not** make the model deterministic in the way the reconciliation engine
is -- low temperature only reduces output variance, it doesn't guarantee
identical output for identical input the way a pure function does.

**Malformed response handling**: the JSON response is validated against a
Pydantic model (`AIExplanation` / `AIAnalysisResponse`). If Groq is
unreachable, returns invalid JSON, or the JSON doesn't match the expected
shape, the backend catches it, logs the failure server-side
(`logger.exception(...)`), and returns a clearly-labeled fallback response
(`is_fallback: true`) built from the deterministic reason that's already on
hand -- the request never 500s and the user is never shown a blank screen or
a hallucinated-looking answer.

## AI tool usage

This implementation was built with AI coding assistance (Claude). Every file
was reviewed, the reconciliation logic was hand-verified against unit tests
and the actual synthetic dataset's output (see "What was found" above,
computed by actually running the code, not estimated), and the full flow
(signup -> login -> upload/demo -> reconcile -> dashboard -> discrepancies ->
detail -> AI explanation) was exercised end-to-end in a real browser before
being called done.

## Deploying to Vercel

This repo deploys as a single Vercel project using [Vercel Services](https://vercel.com/docs/services), which run the Next.js frontend and the FastAPI backend together behind one domain (`vercel.json` at the repo root):

```json
{
  "services": {
    "frontend": { "root": ".", "framework": "nextjs" },
    "backend": { "root": "backend", "entrypoint": "main:app" }
  },
  "rewrites": [
    { "source": "/api/backend(/.*)?", "destination": { "type": "service", "service": "backend" } },
    { "source": "/(.*)", "destination": { "type": "service", "service": "frontend" } }
  ]
}
```

**Why the backend routes are mounted twice**: a Vercel service receives the
request's *full original path* -- a request to `/api/backend/auth/login`
reaches the FastAPI app as `/api/backend/auth/login`, not `/auth/login`.
Rather than force local development to always use that prefix,
`backend/main.py` mounts every route both unprefixed (what you use locally,
and what the tests/README curl examples above use) and again under
`/api/backend` (what Vercel's rewrite requires) -- same app, same code, two
mount points.

**Before deploying**, you need:

1. **A cloud-reachable MongoDB.** Vercel Functions cannot reach a `mongod`
   running on your laptop. Use [MongoDB Atlas](https://www.mongodb.com/atlas)
   (a free tier is enough) and put its connection string in `MONGODB_URI`.
2. **Environment variables**, set in the Vercel project's Settings ->
   Environment Variables (these apply project-wide, covering both services):
   - `MONGODB_URI`, `DATABASE_NAME`, `JWT_SECRET`, `GROQ_API_KEY`, `GROQ_MODEL`
   - `FRONTEND_URL` -- set to your deployed domain (e.g. `https://your-app.vercel.app`)
   - `NEXT_PUBLIC_API_URL` -- set to `/api/backend` (a **relative** path, not
     a full URL -- frontend and backend share one domain under Services, so
     this becomes a same-origin call through the rewrite above, and no CORS
     round-trip is needed in production)
3. **Python version**: pinned via `backend/.python-version` (3.12), the same
   version this was developed and tested against -- newer Python versions
   have had prebuilt-wheel gaps for some pinned dependencies (see
   Troubleshooting).

Then push to the branch connected to your Vercel project (or run `vercel
deploy` locally) -- both services build and deploy together as one unit.
`vercel dev` also runs both services together locally if you want to test
the exact Vercel routing before deploying.

## Troubleshooting

- **`pydantic-core` fails to build / `pyo3` version error during
  `pip install`**: you're on a Python version newer than the pinned
  dependencies support (this was hit with Python 3.14 during development).
  Use Python 3.12 or 3.11 for the backend venv.
- **`email-validator is not installed`**: covered by `requirements.txt`
  already; if you see this, re-run `pip install -r requirements.txt`.
- **Backend tests fail with a connection error**: `mongod` isn't running.
  Start it first (see step 1 above); the API isolation tests need a real
  MongoDB.
- **AI explanations always show the fallback**: `GROQ_API_KEY` isn't set in
  `backend/.env`, or the key is invalid. The rest of the app works fine
  without it -- the fallback is intentional, not a bug.

## Future improvements

- Support multiple historical reconciliations per user in the UI (currently
  one "active" reconciliation per browser, tracked in `localStorage`)
- Server-side rate limiting on `/ai/*` routes
- Streaming the AI response instead of waiting for the full completion
- CSV upload progress percentage for very large files
- Deployment to Vercel (frontend) + a managed host (backend) + MongoDB Atlas
