# PharmaCore PMS

A pharmacy management system with point-of-sale, inventory, patients and prescriptions, and billing reports.

| Part | Stack | Location |
|---|---|---|
| Backend API | Python 3.13, FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic | [`backend/`](backend/) |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS | [`frontend/`](frontend/) |
| Database | PostgreSQL 16 | Docker container |

There are two ways to run it:

- **Docker** runs everything in containers. Use it for a quick start or a production-like setup.
- **Local development** runs PostgreSQL in Docker and the API and frontend natively, with auto-reload.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/), with Docker Compose v2
- For local development only: Python 3.13 and Node.js 20 or newer

## 1. Configure secrets

Every setup reads its settings from a `.env` file in the project root.

```bash
cp .env.example .env
```

Open `.env` and replace every `CHANGE_ME`:

- `POSTGRES_PASSWORD`: a long random value, for example `openssl rand -hex 24`.
- `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD`: the first administrator account.

Never commit `.env`. It is already listed in [`.gitignore`](.gitignore).

## 2a. Run with Docker

```bash
docker compose up -d --build
```

| URL | What |
|---|---|
| http://localhost:3000 | Web app (nginx serving the built frontend, proxying `/api`) |
| http://localhost:8000/docs | Interactive API docs (only if `ENABLE_DOCS=true`) |

PostgreSQL and the API are published on `127.0.0.1` only. Browsers reach the API through port 3000.

The API container runs `alembic upgrade head` before it starts, so the database schema is always at the latest migration.

| Task | Command |
|---|---|
| Follow API logs | `docker compose logs -f api` |
| Stop (keeps data) | `docker compose stop` |
| Start again | `docker compose start` |
| Rebuild after code changes | `docker compose up -d --build` |
| Remove containers and **delete the database** | `docker compose down -v` |

## 2b. Run for local development

Use three terminals, all starting from the project root. The commands below are for PowerShell on Windows; macOS and Linux equivalents are noted.

**Terminal 1: PostgreSQL**

```bash
docker compose up -d postgres
```

**Terminal 2: Backend API (http://127.0.0.1:8000)**

```powershell
python -m venv venv                      # first time only (the venv lives in the project root)
.\venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# Load .env into this shell. Without DATABASE_URL, the API connects to 127.0.0.1:5432
# with the POSTGRES_* credentials.
Get-Content .env | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object { $k,$v = $_ -split '=',2; Set-Item "env:$k" $v }

cd backend
..\venv\Scripts\python.exe -m alembic upgrade head   # create or update the schema
..\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

<details>
<summary>macOS / Linux</summary>

```bash
python3 -m venv venv && ./venv/bin/pip install -r backend/requirements.txt
set -a && . ./.env && set +a
cd backend
../venv/bin/alembic upgrade head
../venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
</details>

**Terminal 3: Frontend (http://localhost:3000)**

```bash
cd frontend
npm install          # first time only
npx vite
```

The Vite dev server runs on port 3000 and forwards `/api` to `localhost:8000`, as configured in [`frontend/vite.config.js`](frontend/vite.config.js).

> **Windows PowerShell:** use `npx vite`, not `npm run dev -- --host ...`. The PowerShell npm wrapper drops the flags, and Vite then starts on port 5173 without the API proxy.

Don't run the Docker `web` container at the same time, because both use port 3000.

## First sign-in

1. Open http://localhost:3000 and sign in with `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD`.
2. You'll be asked to choose a new password straight away. From then on, the `.env` password no longer works.
3. Open the **Users** tab to create staff accounts or approve registrations.

The bootstrap account is created only when the `users` table is empty. Changing `.env` later has no effect on existing accounts.

Forgotten password: another administrator can reset it from the **Users** tab. The user must then choose a new password at next sign-in.

## Authentication and roles

- **Sessions:** server-side, in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie scoped to `/api`.
  - The database stores only a SHA-256 hash of each session ID.
  - Sessions expire after 30 minutes idle or 12 hours total.
  - Signing out, changing your password, or an admin changing your role or disabling you ends sessions immediately.
- **CSRF:** every `POST`, `PUT`, `PATCH` or `DELETE` must send an `X-CSRF-Token` header. The frontend gets this token from `/api/auth/me` and keeps it in memory only.
- **Passwords:**
  - Hashed with Argon2id.
  - At least 12 characters, and must not contain the user's email name or full name.
  - Admin-set passwords are temporary and must be changed at first sign-in.
- **Brute-force protection:**
  - An account locks for 15 minutes after 5 failed attempts.
  - nginx limits each IP to 10 logins and 3 registrations per minute. This applies in Docker only; the Vite dev server has no rate limits.
- **Self-registration:**
  - The **Register** tab on the login page creates a *pending* cashier account.
  - The person can't sign in until an administrator approves it on the **Users** tab and chooses the role.
  - The response is the same whether or not the email already exists.
  - Turn it off with `ALLOW_SELF_REGISTRATION=false`.
- **Audit log:** logins, failures, registrations, approvals and user changes are written to the `auth_events` table.

| Role | Can do |
|---|---|
| Cashier | View all data, POS checkout, add patients, generate documents |
| Pharmacist | Everything a cashier can, plus manage medicines, batches and categories; create prescriptions; cancel, refund and delete invoices |
| Admin | Everything, plus user management and database reset |

The server enforces roles. The UI also hides actions a role can't use.

## Billing rules

- **Every POS checkout creates an invoice.** Its number (`INV-…`) comes from a database sequence and is unique. Prices are always taken from the batch MRP, never from the browser. The receipt is that invoice's PDF (`GET /api/billing/invoices/{id}/pdf`; add `?inline=true` to view it in the browser for printing).
- **GST:** POS prices are MRP, which already includes GST (12%), so the tax is extracted and shown as included. Invoices created through `POST /api/billing/invoices` add GST on top.
- **Checkout is one database transaction:** the cart's batches are locked, then stock deduction, the invoice, the stock audit log and prescription progress all commit together or not at all.
- **Stock:**
  - Can never go below zero, even with simultaneous sales. The database also enforces it with a `CHECK` constraint.
  - Expired batches can't be sold.
  - A prescription can't be dispensed beyond its remaining quantity (also a database constraint).
- **Refunds:**
  - Can be partial. Status becomes `Partially Refunded` and then `Refunded`.
  - The total refunded can't exceed the amount paid. Refunds and cancellations lock the invoice row, so simultaneous requests can't both succeed.
  - `amount_paid` stays as what was collected, and refunds are tracked in `refunded_amount`.
  - Refunds don't return stock.
- **Cancel:**
  - Allowed only for `Paid`, `Pending` or `Partially Paid` invoices that have no refunds.
  - Cancelling a POS sale returns its stock and reverses any prescription progress, in the same transaction.
- **Duplicate:** creates an unpaid `Pending` copy, so it adds no revenue until paid.
- **How the reports calculate figures:**
  - KPIs, sparklines and charts are calculated in SQL, so they cost a fixed number of queries however many invoices match.
  - Cancelled invoices are listed but excluded from every total.
  - *Total revenue* is collected minus refunded. *Net revenue* is billed (paid or not) minus refunded.
  - The dashboard's revenue uses the same invoices.
  - KPI "% change" compares against the previous period of the same length. It shows `n/a` when no start date is selected.
- **Dates** are stored as UTC timestamps. The Reports screen sends the viewer's local day boundaries, and charts group by the viewer's local day.

## Demo data

- **Demo data loads at startup only when all of these hold:**
  - `SEED_DEMO_DATA` is on. It defaults to on in development and off in production.
  - No earlier demo seed has completed.
  - The database contains no business data, so demo records are never mixed into real ones.
- **What it contains:**
  - 6 medicines, 7 stock batches and 8 patients.
  - Two open prescriptions (John Doe and Jane Smith).
  - About 30 days of sales: roughly 240 invoices, with a few refunds and cancellations.
- **How it's built:** it uses the same pricing, invoice, refund and cancel code as the live app. So:
  - Stock, audit logs, invoices and prescriptions agree with each other.
  - Prescription sales link to the prescriptions they dispensed.
  - Today's stock matches the figures in `seed.py`. For example, Augmentin has a batch close to expiry and Metformin is below its minimum level.
  - The data uses a fixed random seed, so it's the same every time.
- **Atomic:** seeding (and a reset: wipe, reload and marker) runs in one transaction. If it fails or is interrupted, nothing is changed. The completion marker is kept in the `app_meta` table.
- **Resetting:** the admin action **Settings → Reset to Demo Data** deletes all business data (patients, prescriptions, medicines, stock, invoices, audit logs) and reloads demo data. User accounts are kept.
  - It requires typing `RESET DEMO DATA`.
  - It's recorded in `auth_events`.
  - It's unavailable unless `ALLOW_DEMO_RESET=true`.

## Configuration

All settings are environment variables, set in `.env`. They're read in [`backend/app/core/config.py`](backend/app/core/config.py).

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `pharmacore` / (required) / `pharmacore` | PostgreSQL credentials and database, used by Docker Compose |
| `DATABASE_URL` | built from `POSTGRES_*` at `127.0.0.1:5432` | SQLAlchemy URL, `postgresql+asyncpg://user:password@host:5432/db`. Compose sets it for the API container |
| `DB_POOL_SIZE` | `10` | Connections kept in the pool |
| `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` / `BOOTSTRAP_ADMIN_NAME` | (empty) | First admin account, created only while no users exist |
| `ENVIRONMENT` | `development` | `production` disables API docs unless `ENABLE_DOCS` overrides it |
| `ENABLE_DOCS` | `true` outside production | Serve `/docs`, `/redoc` and `/openapi.json` |
| `SEED_DEMO_DATA` | `true` outside production | Load demo data into an **empty** database at startup (see [Demo data](#demo-data)) |
| `ALLOW_DEMO_RESET` | `true` outside production | Enable the admin "Reset to Demo Data" action, which **deletes all business data** |
| `DB_CONNECT_TIMEOUT_SECONDS` | `30` | How long startup keeps retrying PostgreSQL before failing |
| `ALLOW_SELF_REGISTRATION` | `true` | Show the Register tab and accept registration requests |
| `COOKIE_SECURE` | `true` | Keep `true`. Browsers accept Secure cookies on `http://localhost`; anywhere else, serve over HTTPS |
| `SESSION_IDLE_TIMEOUT_MINUTES` | `30` | Sign out after this much inactivity |
| `SESSION_ABSOLUTE_TIMEOUT_HOURS` | `12` | Maximum session length |
| `LOGIN_MAX_FAILED_ATTEMPTS` / `LOGIN_LOCKOUT_MINUTES` | `5` / `15` | Account lockout |
| `PASSWORD_MIN_LENGTH` | `12` | Minimum password length |
| `STORE_NAME` | `PharmaCore Central` | Store name recorded on invoices created at the POS |
| `CORS_ORIGINS` | (empty) | Comma-separated origins allowed to call the API cross-origin. Not needed for the bundled frontend |

## Project structure

The backend and frontend are separate apps side by side. Each backend feature keeps its endpoints, models, rules and queries together in one folder.

```
.
├── docker-compose.yml              postgres + api + web services
├── .env.example                    configuration template (.env lives here too)
├── backend/                        FastAPI API
│   ├── Dockerfile                  API image (migrates, then serves; non-root user)
│   ├── requirements.in             direct Python dependencies (edit this)
│   ├── requirements.txt            pinned versions, generated by pip-compile
│   ├── requirements-dev.txt        test and tooling dependencies
│   ├── alembic.ini, alembic/       database migrations
│   ├── tests/                      pytest suite (throwaway database per run)
│   └── app/
│       ├── main.py                 FastAPI app, router wiring, startup, error handlers
│       ├── core/
│       │   ├── config.py           environment settings
│       │   ├── common.py           shared helpers (dates, ids, stock/expiry rules)
│       │   └── pagination.py       skip/limit parameters and X-Total-Count
│       ├── db/
│       │   ├── tables.py           schema: tables, constraints, indexes (source for migrations)
│       │   ├── engine.py           connection pool and transactions
│       │   ├── utils.py            small query helpers
│       │   ├── meta.py             app state (demo marker) and the demo-reset wipe
│       │   └── seed.py             optional demo data
│       └── modules/                one folder per feature, each with
│           │                       router.py · schemas.py · service.py · repository.py
│           ├── auth/               login, sessions, CSRF, roles, users (+ security.py, dependencies.py)
│           ├── medicines/          categories, medicines, stock batches
│           ├── patients/           patients and prescriptions
│           ├── pos/                checkout and the stock movement log
│           ├── billing/            invoices, refunds, KPIs, charts, CSV/PDF (+ invoice_template.py)
│           └── dashboard/          dashboard metrics
└── frontend/                       React app
    ├── Dockerfile                  builds the app and serves it with nginx
    ├── nginx/                      nginx.conf (/api proxy, rate limits) and security headers
    ├── package.json, vite.config.js, tailwind.config.js, tsconfig.json
    └── src/
        ├── main.tsx, App.tsx       entry point, layout and navigation (screens load on demand)
        ├── api.ts                  fetch wrapper (CSRF header, session expiry)
        ├── queries.ts              cached server data (TanStack Query) and refresh rules
        ├── auth.tsx                auth context and roles
        ├── pages/                  one file per screen: Dashboard, POSBilling, InventoryList, ...
        ├── components/             parts used by the pages: inventory/, patients/, reports/, ui/
        └── lib/                    formatting helpers and notifications
```

## Database migrations

The schema is defined once, in [`backend/app/db/tables.py`](backend/app/db/tables.py), and versioned with Alembic in [`backend/alembic/versions/`](backend/alembic/versions/). The API refuses to start if the database isn't at the latest revision, and tells you to run `alembic upgrade head`.

To change the schema:

1. Edit `tables.py`.
2. Generate a migration, then read and fix it. Autogenerate doesn't detect everything, for example extensions, sequences or renamed columns.
   ```powershell
   cd backend
   ..\venv\Scripts\python.exe -m alembic revision --autogenerate -m "add supplier table"
   ```
3. Apply it locally with `alembic upgrade head`. Docker applies it on the next `docker compose up -d --build`.

`alembic check` reports whether `tables.py` and the migrations disagree; the test suite runs it.

## API

All endpoints are under `/api`. Everything except the `/api/auth/*` sign-in endpoints requires a session. The full, interactive list is at http://localhost:8000/docs when docs are enabled.

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/login` | Sign in, which sets the session cookie |
| `POST /api/auth/logout` | Sign out |
| `GET /api/auth/me` | Current user and CSRF token |
| `POST /api/auth/register` | Request an account (pending approval) |
| `POST /api/auth/change-password` | Change your own password |
| `GET/POST /api/users`, `PATCH/DELETE /api/users/{id}` | User management (admin) |
| `GET /api/medicines`, `/api/batches`, `/api/patients`, `/api/prescriptions` | Lists. Optional `skip` and `limit` (max 1000) page the results; `X-Total-Count` has the total. Without `limit` everything is returned |
| `GET /api/pos/audit-logs?limit=50` | Latest stock movements (max 200) |
| `POST /api/settings/seed` | Delete all business data and reload demo data (admin; needs `ALLOW_DEMO_RESET` and body `{"confirm": "RESET DEMO DATA"}`) |

## Tests

Backend tests are a pytest suite in `backend/tests/`. They drive the real app in-process through its HTTP API, so no server needs to be running. Each run creates its own throwaway database, `pharmacore_test_<random>`, and drops it at the end. The fixture refuses to run against any database whose name doesn't start with `pharmacore_test_`, so your real data is never touched.

```powershell
cd backend
..\venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # first time
..\venv\Scripts\python.exe -m pytest                                 # ~4 min
```

- PostgreSQL must be reachable (`docker compose up -d postgres`). The tests use `TEST_DATABASE_URL` if set, otherwise the `POSTGRES_*` credentials from `.env` at `127.0.0.1:5432`. The user needs permission to create databases.
- The test database is built with `alembic upgrade head`, so every run also tests the migrations.
- Coverage:
  - authentication, sessions, CSRF, roles and registration
  - POS checkout, including concurrent sales, stock rules and rollback of a failed checkout
  - database constraints, concurrent refunds, and migrations (upgrade, downgrade, `alembic check`)
  - invoices, refunds, cancellations, KPIs, charts and exports; the SQL KPIs are checked against a Python reference
  - demo-data consistency and reset safety
  - pure-function unit tests
  - **query budgets**: each list endpoint must use a fixed number of database queries, which catches N+1 regressions
  - **responsiveness**: other requests are still answered while a PDF renders
- Frontend: `npm run build` (in `frontend/`) type-checks (`tsc --noEmit`) before bundling, with unused-code checks enabled.
- Backend static check, in `backend/`: `..\venv\Scripts\python.exe -m pyflakes app tests alembic`

## Production checklist

- [ ] Serve over HTTPS (for example, a TLS-terminating load balancer or reverse proxy in front of the `web` container). Then uncomment the `Strict-Transport-Security` header in [`frontend/nginx/nginx.conf`](frontend/nginx/nginx.conf).
- [ ] Set `ENABLE_DOCS=false`.
- [ ] Use strong, unique values for `POSTGRES_PASSWORD` and `BOOTSTRAP_ADMIN_PASSWORD`, and keep `.env` out of version control.
- [ ] Decide whether self-registration should stay on (`ALLOW_SELF_REGISTRATION`).
- [ ] Back up the database, for example `docker compose exec postgres pg_dump -U pharmacore pharmacore > backup.sql` on a schedule, or back up the `pg-data` volume.
- [ ] Don't publish ports 8000 or 5432 beyond `127.0.0.1`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `failed to connect to the docker API` | Docker Desktop isn't running. Start it and retry. |
| API exits with `DatabaseUnavailable: Could not connect to PostgreSQL` | PostgreSQL isn't reachable, or the `POSTGRES_*` / `DATABASE_URL` settings are wrong. Startup retries for `DB_CONNECT_TIMEOUT_SECONDS` (30 s) before giving up. On Windows, use `127.0.0.1` rather than `localhost`, which may try IPv6 first. |
| API exits with `The database schema is at revision … Run alembic upgrade head` | The schema is older than the code. Run `alembic upgrade head` in `backend/` (Docker does this automatically). |
| `password authentication failed` after changing `POSTGRES_PASSWORD` | PostgreSQL sets the password only when the `pg-data` volume is first created. Change it inside the database (`ALTER USER`), or delete the volume to start empty. |
| Old `mongo-data` volume | Left over from the MongoDB version and no longer used. Delete it with `docker volume rm pharma_mongo-data` once you no longer need it. |
| No demo data after startup | Demo data only loads into an empty database, and only when `SEED_DEMO_DATA` is on (off when `ENVIRONMENT=production`). The log says which case applied. |
| No "Reset to Demo Data" card in Settings | It's shown only to admins and only when `ALLOW_DEMO_RESET=true`. |
| Frontend opens on port 5173 and every API call fails | You started Vite with `npm run dev -- …` in PowerShell. Use `npx vite` instead. |
| Login works but you're signed out immediately | You're on plain HTTP at an address other than `localhost`, so the browser drops the Secure cookie. Use `localhost` or HTTPS. |
| "Your account is awaiting administrator approval." | The account was self-registered. An admin must approve it on the **Users** tab. |
| `Too many attempts` / HTTP 429 | nginx rate limit. Wait a minute. |
| Port 3000 or 8000 already in use | Stop the other copy: `docker compose stop web api`, or close the local dev servers. |
