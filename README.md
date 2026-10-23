# British Auction in an RFQ System

[![CI](https://github.com/varun-sharma-2006/British-Auction-in-RFQ-System/actions/workflows/ci.yml/badge.svg)](https://github.com/varun-sharma-2006/British-Auction-in-RFQ-System/actions/workflows/ci.yml)

An RFQ (Request for Quotation) platform for freight with **British-auction** bidding: suppliers openly lower their
prices, the auction **extends automatically** when activity happens near the end, and it **never runs past the forced
close time**. Ranks, prices and the reason for every extension are visible live.

**Stack:** FastAPI · PostgreSQL · SQLAlchemy 2 · Alembic · Celery + Redis · React 18 + TypeScript · WebSockets ·
JWT auth · pytest · Vitest · Playwright · GitHub Actions · Docker

![Demo: a supplier takes L1 inside the trigger window, the auction extends with a logged reason, and the buyer's screen updates live](docs/demo.gif)

| Deliverable | Where |
|---|---|
| HLD with architecture diagram | [`docs/HLD.md`](docs/HLD.md): architecture, bid sequence, lifecycle, security, deployment modes, testing strategy |
| Schema design | [`docs/SCHEMA.md`](docs/SCHEMA.md) (ER diagram + constraints) and [`docs/schema.sql`](docs/schema.sql) (exact PostgreSQL DDL) |
| Backend code | [`backend/`](backend) |
| Frontend code | [`frontend/`](frontend) |

---

## Requirements coverage

| Assignment requirement | Implementation |
|---|---|
| **§5 RFQ creation** with British Auction option: name/reference ID, bid start, bid close, forced close, pickup/service date | `POST /api/rfqs` (buyers only) · *Create RFQ* page. Reference ID auto-generated (`RFQ-2026-00001`) if blank; British Auction can be toggled off for a standard RFQ. |
| **Quote fields:** carrier, freight / origin / destination charges, transit time, validity | `POST /api/rfqs/{id}/bids` (suppliers only) · bid form. Total = sum of charges. |
| **§5 Rule:** never extend beyond the forced close | Enforced 3×: engine caps `min(close + Y, forced)`, bids rejected at/after close, DB `CHECK (current_close_at <= forced_close_at)`. Proven under concurrency on PostgreSQL. |
| **§6.1 Trigger window X** | A bid counts if `current_close − X ≤ t < current_close`; the window slides with each extension. |
| **§6.2 Extension duration Y** | Added to the **current close time** (6:00 → 6:05, as in the brief). |
| **§6.3a / b / c triggers** | `BID_RECEIVED` · `ANY_RANK_CHANGE` · `L1_CHANGE`, each tested with the brief's own 5:55 / 5:58 / 5:59 PM examples |
| **§7 Validation** | Pydantic (clear messages) + client-side checks + DB `CHECK` constraints |
| **§8 Listing page:** name/ID, current lowest bid, current close, forced close, status (Active / Closed / Force Closed) | `/` (plus *Scheduled*, live countdowns, extension count, status filters) |
| **§8 Details page:** bids sorted by price, L1/L2/L3, quote details, X & Y, activity log with bids, extensions and the reason for each | `/rfqs/:id` (plus visual timeline, revision history, a "will this bid extend the auction?" hint) |
| **§4 Success metrics:** bids per RFQ; final prices for extended vs non-extended auctions | `GET /api/metrics`, shown on the listing page |

![Auction details: ranking, configuration and activity log with extension reasons](docs/screenshots/details.png)

## Engineering highlights

* **Proven concurrency safety.** Bids lock the RFQ row (`SELECT … FOR UPDATE`). A PostgreSQL test fires 8 simultaneous
  last-second bids and asserts exactly 5 chained extensions ending at the forced close. It fails if the lock is removed.
* **Pure rules engine**, unit-tested on its own, plus a TypeScript mirror that tells suppliers *before* they submit
  whether their bid will extend the auction. Both are tested against the same scenarios.
* **Real roles.** JWT auth: buyers create RFQs, suppliers bid, and a supplier can only bid as their own company.
* **Celery + Redis.** Celery beat/worker close auctions; Redis pub/sub fans live updates out to every API replica.
  Without Redis the same code runs as a single container.
* **Server-authoritative time.** Bids are timestamped by the server, and countdowns correct for client clock skew.
* **Audit trail.** Bids are append-only revisions; every extension logs `old → new` close time and a readable reason.
* **Tested at every layer.** 61 backend tests (95% coverage), 26 frontend tests, and a Playwright end-to-end run.
  CI covers all of it on PostgreSQL, plus lint and a migration up/down/drift check.

---

## Run it

Demo logins after seeding (password **`demo1234`**): `buyer@demo.com` · suppliers `bluedart@demo.com`,
`gati@demo.com`, `rivigo@demo.com`, `delhivery@demo.com`, `tci@demo.com`, `vrl@demo.com`.
The login page has one-click buttons for these.

### Option A: Docker, full topology (Postgres, Redis, API, Celery worker + beat, nginx)

```bash
docker compose up --build
docker compose exec api python -m scripts.seed
```
Open **http://localhost:8080** · API docs: http://localhost:8000/docs

### Option B: Single container (what the Render blueprint deploys)

```bash
docker build -t british-auction .
docker run -p 8000:8000 -e DATABASE_URL=postgresql://user:pass@host:5432/db -e SEED_DEMO=true british-auction
```
API and UI on **http://localhost:8000**.

**Hosting (free, no card):** [Neon](https://neon.tech) PostgreSQL + a [Hugging Face](https://huggingface.co/spaces)
Docker Space. `.github/workflows/deploy-hf.yml` redeploys the Space automatically after every green CI run on `main`
(setup steps are at the top of that file). `render.yaml` is also included for Render (**New → Blueprint**).

### Option C: Local development

Prerequisites: Python 3.11+, Node 18+, PostgreSQL 14+ (Redis optional).

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate                  # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env                  # macOS/Linux: cp; then set DATABASE_URL
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload           # http://localhost:8000/docs

# Frontend (second terminal)
cd frontend
npm install
npm run dev                             # http://localhost:5173 (proxies /api and /ws)
```

To watch extensions happen live, run `python -m scripts.simulate_bidding --every 8`. It logs in as the demo
suppliers and keeps undercutting L1. Optional Celery mode: set `REDIS_URL` and `RUN_CLOSER=false`, then run
`celery -A app.worker worker --pool=solo` and `celery -A app.worker beat`.

### Tests

```bash
cd backend && pytest                                        # SQLite by default
TEST_DATABASE_URL=postgresql+psycopg://... pytest           # PostgreSQL, adds the concurrency tests
ruff check .

cd frontend && npm run lint && npm run typecheck && npm test

pip install -r e2e/requirements.txt && playwright install chromium
E2E_BASE_URL=http://localhost:5173 pytest e2e               # app running with seeded data
```

---

## API

| Method | Path | Who | Description |
|---|---|---|---|
| `POST` | `/api/auth/register`, `/api/auth/login` | anyone | Returns a JWT and the user |
| `GET` | `/api/auth/me` | signed in | Current user |
| `GET` | `/api/rfqs?status=ACTIVE` | signed in | Listing |
| `POST` | `/api/rfqs` | buyer | Create an RFQ / British auction |
| `GET` | `/api/rfqs/{id}` | signed in | Details: config, ranking with full quotes, `server_time` |
| `GET` | `/api/rfqs/{id}/bids` | signed in | Every bid revision, newest first |
| `POST` | `/api/rfqs/{id}/bids` | supplier | Submit a quote → `{rank_label, extended, new_close_at, extension_reason}` |
| `GET` | `/api/rfqs/{id}/activity` | signed in | Activity log |
| `GET/POST` | `/api/suppliers` | signed in / buyer | Supplier companies |
| `GET` | `/api/metrics` | signed in | Success metrics |
| `WS` | `/ws` | anyone | `{"type":"rfq_updated","rfq_id":N,"reason":…}` (ids only, no data) |

Interactive docs at **`/docs`**.

## Rules and assumptions

These are the points where the brief leaves room for interpretation, and how this build resolves them:

* **Extension is added to the current close time**, not the bid time; the trigger window is measured from the
  *current* close, so it moves with each extension.
* **Window boundaries:** a bid exactly X minutes before close is inside; a bid at the close instant is rejected.
* **Capping:** if `close + Y` passes the forced close, the close becomes the forced close (logged as *capped*).
  Further triggers at the forced close are logged as *Extension blocked*.
* **Force Closed** = ended at the forced close (extensions reached the ceiling). **Closed** = ended earlier.
* **Re-bidding:** a supplier may only *lower* their own total; each re-bid is a new revision.
* **Ties:** equal totals rank by who reached that price first.
* **"Any rank change"** = an already-ranked supplier changed position. A newcomer entering last moves no one.
  **"L1 change"** includes the first-ever bid.
* **Open bidding:** suppliers see competitors' prices and names, per "suppliers submit bids openly".
* **Colleagues** who register with the same company name share one supplier entry, and so one place in the ranking.

## Project structure

```
backend/
  app/
    main.py               app, error handlers, background tasks, SPA serving
    api/                  auth.py (register/login/me) · deps.py (role guards) · routes.py (REST + WS)
    models.py             SQLAlchemy models + DB constraints
    schemas.py            Pydantic request/response models + validation
    security.py           password hashing, JWT
    services/
      auction_engine.py   pure rules: ranking, trigger window, extension, cap, status
      bidding.py          transactional bid submission (row lock)
      rfq_service.py      create / list / details / activity / metrics
      closer.py           start/close transitions (SKIP LOCKED)
    realtime.py           WebSocket fan-out (in-process or Redis pub/sub)
    worker.py             Celery app + beat schedule
  alembic/                migrations 0001 (schema), 0002 (users & roles)
  scripts/                seed.py (demo data through the real engine) · simulate_bidding.py
  tests/                  engine · API · auth · concurrency (PG) · worker/realtime · SPA
frontend/src/
  pages/                  AuctionList · AuctionDetail · CreateRfq · Login · Register · Suppliers
  components/             BidForm · AuctionTimeline · Layout · shared UI
  lib/                    api client · auth context · predict (extension hint) · hooks · formatting
e2e/                      Playwright end-to-end test · demo recorder (screenshots + GIF)
docs/                     HLD · schema · screenshots · demo.gif
Dockerfile · render.yaml  single-container build + Render blueprint
docker-compose.yml        full topology
.github/workflows/ci.yml  lint, migrations, tests (PostgreSQL), frontend, e2e
```
