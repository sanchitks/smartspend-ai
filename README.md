# SmartSpend AI

An AI-powered personal finance and budgeting assistant: record income and expenses (or describe them in a
sentence), set monthly budgets, see where money goes, and ask plain-language questions about your own records.

Built from the *SmartSpend AI Product Requirements Document v1.0* (20 November 2026).

> SmartSpend AI provides general budgeting assistance, not regulated financial advice. It doesn't connect to
> banks or move money.

**Live:** <https://sanchitks.github.io/smartspend-ai/>. The website is on GitHub Pages, the API on Render
(<https://smartspend-api-x7e4.onrender.com/docs>) and the data in PostgreSQL on Neon. The free API server
sleeps when idle, so the first request after a quiet spell can take up to a minute.

## Quick start (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File start.ps1
```

This installs everything on first run and opens:

- Website: <http://localhost:5173>
- API and its interactive docs: <http://localhost:8000/docs>

Manual start:

```bash
# API
cd backend
uv venv --python 3.13 .venv && uv pip install --python .venv/Scripts/python.exe -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# Website (another terminal)
cd frontend
npm install
npm run dev
```

With no configuration it uses SQLite (`backend/smartspend.db`) and the **offline demo AI**, so everything works
without an API key.

### Turning on Claude

Copy `backend/.env.example` to `backend/.env` and set `ANTHROPIC_API_KEY`. With `AI_PROVIDER=auto` (the
default) the app switches to Claude (`ANTHROPIC_MODEL`, default `claude-opus-5-5`) when a key is present.

- **Structured outputs:** every model reply must match a JSON schema and is validated again before use.
- **Low effort:** parsing and intent detection run at low effort; general budgeting answers run at medium.
- **Server-side refusal fallback:** if Claude declines a request, the API retries it on a fallback model
  within the same call. It's switched on with `fallbacks: "default"` and the `server-side-fallback-2026-07-01`
  beta.

## What's built

| PRD area | Status |
|---|---|
| Auth & profile (AUTH-01..05) | Register, login, logout (revokes the session), token refresh, profile, currency and timezone, account deletion |
| Transactions (TXN-01..07) | Create, edit and delete; filters, search, sort and pagination; future dates flagged; CSV export; CSV import with a preview that reports every invalid row |
| Categories (§6.3) | PRD default categories, plus custom categories |
| Budgets (BUD-01..06) | Monthly total and category budgets, live progress, statuses, copy last month, drill-down to transactions |
| Dashboard & analytics (§6.5) | Summary cards; like-for-like month comparison; 6- or 12-month income vs expenses; category breakdown vs last month; spending pace against the budget |
| Alerts (§6.7) | In-app alerts at 75%, 90% and over 100%; deduplicated and re-evaluated on edit and delete |
| Savings goals | Target, date and progress, with the amount needed per month |
| AI parsing (§7, App. A.1) | Sentence → draft → user review → save. Nothing is saved without confirmation; vague input such as "paid 500" gets a clarifying question |
| SpendWise AI assistant (§6.8) | LangGraph workflow covering all PRD intents (see below) |
| Insights (§6.6, App. A.2) | Evidence-backed observations with the numbers shown; the AI may only re-word them |

**Assistant intents:** totals, top categories, budget status, period comparison, savings what-ifs (labelled
hypothetical), goals, general budgeting help, adding an expense, and polite refusals for investment, tax,
credit or insurance questions. Each answer shows the period it covers, the calculated figures, and links to
the supporting transactions.

## How the AI is kept honest

The core rule (PRD §1.2): **all amounts are calculated by code; the model only explains them.**

- **Workflow:** `parse_input → classify_intent → retrieve_financial_data → calculate_metrics → generate_insight →
  safety_check → format_response`.
    - Side branches handle education, clarification, refusals and drafting a transaction.
    - The workflow has no loops and the model never touches the database.
- **Grounding check:** every number in AI-written text must match a number the app calculated. If one doesn't,
  the text is thrown away and the calculated answer is shown instead (`app/ai/grounding.py`).
- **What Claude receives:**
    - It gets only what the task needs: the message, today's date, category names and the calculated figures.
    - It never gets names, emails, passwords, tokens or raw transaction history.
    - User text is fenced off as data, so instructions inside it aren't followed.
- **If Claude is down:** core features keep working. The assistant falls back to rule-based matching, and quick
  add tells the user to enter the transaction manually.

## Decisions on the PRD's open questions (§18.1)

| Question | Decision |
|---|---|
| Currency | Chosen at setup (INR default, 8 options), stored on every record, and locked once transactions exist, so currencies are never mixed |
| CSV import | Included, with a preview; invalid rows are listed with a reason and never silently dropped |
| Budget period | Calendar month |
| Refunds | Recorded as income in the **Refund** category; never netted against expenses |
| Email verification and password reset | Not in this version (needs an email provider) |
| Alert policy | One alert per budget, per month, per threshold. A single big jump creates only the highest alert crossed. Past alerts are kept even if spending later drops |

## Project layout

```text
backend/
  app/
    api/          # versioned routers: auth, records, planning, analytics, ai
    core/         # settings, money (Decimal), periods, errors, security
    services/     # business rules and all calculations
    ai/           # LangGraph graphs, handlers, prompts (versioned), grounding, providers (Claude + offline demo)
    models.py     # SQLAlchemy entities
    schemas.py    # Pydantic schemas
  alembic/        # migrations (PostgreSQL)
  tests/          # 81 tests
frontend/         # React + TypeScript + Tailwind + Recharts (Vite)
```

## Security

- **Passwords and sessions:**
    - Passwords are hashed with Argon2id.
    - Access tokens last 30 minutes and are tied to a server-side session, so logging out revokes them at once.
    - Sessions expire after 7 days at most.
- **Ownership:** every query is scoped to the signed-in user from the token, never from the request. Other
  users' records return 404.
- **Rate limits:** on login (per IP and per email), registration and the AI endpoints.
- **CORS:** only the configured origins are allowed.
- **API hardening:**
    - Security headers on every response, and a 1 MB request cap.
    - One error format for all errors, with no stack traces.
- **Money:** amounts are exact `NUMERIC(14,2)` decimals. SQLite stores whole paise instead, because it would
  otherwise add floats.
- **CSV export:** cells that start with `=`, `+`, `-` or `@` are neutralised so they can't run as spreadsheet
  formulas.
- **Production:** the API refuses to start with a placeholder `JWT_SECRET_KEY`.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest
```

81 tests cover:

- Money and threshold unit tests.
- Auth and security: cross-user access, expired and forged tokens, rate limits, CORS, body size.
- Every critical test case in PRD §15.3.
- AI contract tests with a faked Claude: malformed JSON, schema failures, refusals, truncation, timeouts, rate
  limits.
- Grounding rejection, outage fallback and LangGraph routing.

The frontend is type-checked with `npm run typecheck`.

To run the same tests on PostgreSQL, point `TEST_DATABASE_URL` at a disposable database; it's wiped on every
test.

## Database and deployment

Local runs use SQLite and create tables automatically. For PostgreSQL, set `DATABASE_URL` and run
`alembic upgrade head`.

How the live version is deployed:

- **Website:** every push to `main` builds the site and publishes it to GitHub Pages
  (`.github/workflows/pages.yml`). The API address comes from the repository variable `API_URL`.
- **API:** Render runs the `backend` folder (`render.yaml`) and applies migrations on every start. Secrets
  (`DATABASE_URL`, `JWT_SECRET_KEY`, `ANTHROPIC_API_KEY`) live only in Render's settings.
- **Turning on Claude in production:** add `ANTHROPIC_API_KEY` to the Render service's environment.

`docker compose up --build` runs the API with PostgreSQL. **The Docker files haven't been tested, because Docker
isn't installed on the development machine.**

## Note for Windows

The project folder name contains `&`, which breaks npm's `.cmd` shortcuts. That's why the npm scripts call
`node node_modules/...` directly. Use `npm run dev`, not `npx vite`.

## Not done yet

- Email verification and password reset.
- Recurring-transaction suggestions (P2) and email or push notifications (P2).
- Dark mode, and splitting the frontend bundle (charts load with the main bundle).
