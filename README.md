# Stock Portfolio Advisor

A full-stack stock portfolio advisor with personalized risk scoring, LLM-generated rationale, and live WebSocket updates.

## Architecture

```mermaid
graph TB
    subgraph Browser["Browser"]
        UI["React + Vite\nDashboard / PortfolioView\nPreferences / Criteria / Thresholds"]
        WS_CLIENT["useWebSocket\n(exponential backoff reconnect)"]
        AUTH_CTX["AuthContext\n(cookie-based)"]
    end

    subgraph FastAPI["FastAPI Backend (uvicorn)"]
        MIDDLEWARE["CORS + Rate Limit (slowapi)\n+ Private Network Access header"]

        subgraph Routers["Routers"]
            R_AUTH["/auth/*\nCivic OAuth"]
            R_PORT["/api/portfolios"]
            R_STOCKS["/api/portfolios/:id/stocks"]
            R_SCORES["/api/scores"]
            R_PREFS["/api/preferences"]
            R_CRIT["/api/criteria"]
            R_THRESH["/api/thresholds"]
            R_HEALTH["/health\n/admin/refresh"]
        end

        subgraph Scheduler["APScheduler"]
            SCHED["IntervalTrigger\nevery 30 min"]
            CLEANUP["CronTrigger\n3am daily cleanup"]
        end

        subgraph Layer1["Layer 1 — agent.py"]
            PIPELINE["run_data_pipeline()\nfetch → score → persist → broadcast"]
            SCORING["scoring.py\nvolatility + beta + D/E + sector\n± preference & criteria adjustments"]
        end

        subgraph Layer2["Layer 2 — llm_agent.py"]
            LLM_CYCLE["run_llm_agent_cycle()\ndelta filter → gather context → prompt → persist"]
            PROMPT["_build_prompt()\nnews + earnings + SEC + risk score"]
        end

        WS_SERVER["WebSocket Manager\n/ws/{user_id}?token=..."]
    end

    subgraph DataSources["External Data Sources"]
        YFINANCE["yfinance\nprice, beta, D/E, P/E, sector"]
        NEWSAPI["NewsAPI / Finnhub\nnews headlines + sentiment"]
        EDGAR["SEC EDGAR\n10-K, 10-Q, 8-K filings"]
        OPENROUTER["OpenRouter API\n(httpx direct)\nnvidia/nemotron or mistral"]
        CIVIC["Civic Auth\nOAuth2 + cookie session"]
    end

    subgraph DB["PostgreSQL"]
        T_USERS["users"]
        T_PORT["portfolios\nportfolio_stocks"]
        T_STOCK_DATA["stock_data"]
        T_SCORES["stock_scores\n(risk_score, rationale, breakdown)"]
        T_HIST["stock_score_history"]
        T_PREFS["user_preferences"]
        T_CRIT["custom_criteria"]
        T_THRESH["user_thresholds"]
        T_LOGS["refresh_logs"]
    end

    UI -->|"REST (credentials: include)"| MIDDLEWARE
    WS_CLIENT -->|"ws://"| WS_SERVER
    AUTH_CTX -->|"GET /auth/user"| R_AUTH
    R_AUTH <-->|"OAuth redirect"| CIVIC
    SCHED --> PIPELINE
    SCHED --> LLM_CYCLE
    CLEANUP -->|"DELETE old rows"| T_HIST
    R_HEALTH -->|"asyncio.create_task"| PIPELINE
    PIPELINE --> YFINANCE
    PIPELINE --> SCORING
    SCORING --> T_SCORES
    SCORING --> T_HIST
    SCORING --> T_STOCK_DATA
    PIPELINE --> WS_SERVER
    LLM_CYCLE --> PROMPT
    PROMPT --> NEWSAPI
    PROMPT --> YFINANCE
    PROMPT --> EDGAR
    PROMPT -->|"POST /chat/completions\nhttpx"| OPENROUTER
    OPENROUTER -->|"rationale text"| LLM_CYCLE
    LLM_CYCLE --> T_SCORES
    LLM_CYCLE --> WS_SERVER
    R_PORT <--> T_PORT
    R_STOCKS <--> T_PORT
    R_STOCKS <--> T_STOCK_DATA
    R_STOCKS <--> T_SCORES
    R_SCORES <--> T_SCORES
    R_SCORES <--> T_HIST
    R_PREFS <--> T_PREFS
    R_CRIT <--> T_CRIT
    R_THRESH <--> T_THRESH
    R_PREFS -->|"asyncio.create_task rescore"| SCORING
    R_CRIT -->|"asyncio.create_task rescore"| SCORING
    WS_SERVER -->|"score_update\nrationale_update\nthreshold_alert"| WS_CLIENT
```

## Data Flow

```mermaid
sequenceDiagram
    actor User
    participant Frontend
    participant Backend
    participant DB as PostgreSQL
    participant YF as yfinance
    participant News as NewsAPI/Finnhub
    participant SEC as SEC EDGAR
    participant OR as OpenRouter

    Note over Backend: Every 30 min (APScheduler)

    rect rgb(235, 245, 255)
        Note over Backend,YF: Layer 1 — Data Pipeline
        Backend->>YF: fetch price, beta, D/E, sector (concurrent)
        YF-->>Backend: StockData[]
        Backend->>DB: upsert stock_data
        Backend->>DB: read user_preferences + custom_criteria
        DB-->>Backend: prefs, criteria
        Backend->>Backend: scoring.py — compute risk score\n(volatility + beta + D/E + sector\n± preference & criteria adjustments)
        Backend->>DB: upsert stock_scores\nappend stock_score_history
        Backend->>Frontend: WS: score_update {ticker, risk_score, recommendation, breakdown}
    end

    rect rgb(240, 255, 240)
        Note over Backend,OR: Layer 2 — LLM Rationale
        Backend->>DB: read stock_scores (rationale_at IS NULL or score delta ≥ 5)
        DB-->>Backend: candidate tickers
        Backend->>News: fetch headlines + sentiment
        Backend->>YF: fetch EPS actual/estimate/surprise
        Backend->>SEC: fetch 10-K, 10-Q, 8-K filing dates
        News-->>Backend: headline_summary, sentiment score
        YF-->>Backend: EarningsData
        SEC-->>Backend: filings[]
        Backend->>Backend: _build_prompt()\nassemble risk score + signals
        Backend->>OR: POST /chat/completions (httpx)\nmodel: nvidia/nemotron or mistral
        OR-->>Backend: rationale text (2–4 sentences)
        Backend->>DB: UPDATE stock_scores SET rationale, rationale_at
        Backend->>Frontend: WS: rationale_update {ticker, rationale}
    end

    rect rgb(255, 248, 235)
        Note over User,DB: User Interaction — Add Stock
        User->>Frontend: enter ticker, click Add
        Frontend->>Backend: POST /api/portfolios/{id}/stocks {ticker}
        Backend->>YF: validate ticker (fetch price)
        YF-->>Backend: StockData
        Backend->>DB: insert portfolio_stocks\nupsert stock_data
        Backend->>DB: read prefs + criteria
        Backend->>Backend: compute_risk_score()
        Backend->>DB: upsert stock_scores
        Backend-->>Frontend: {ticker, risk_score, recommendation}
        Frontend->>Frontend: invalidate query cache → re-render StockCard
    end

    rect rgb(255, 240, 245)
        Note over User,DB: User Interaction — Update Preferences
        User->>Frontend: change risk tolerance / horizon / style
        Frontend->>Backend: PUT /api/preferences
        Backend->>DB: upsert user_preferences
        Backend-->>Frontend: {status: updated}
        Backend->>Backend: asyncio.create_task(_rescore_user)\n[fire and forget]
        Backend->>DB: read all user tickers + stock_data
        Backend->>Backend: recompute scores with new prefs
        Backend->>DB: upsert stock_scores
    end

    rect rgb(245, 240, 255)
        Note over User,Frontend: Auth Flow
        User->>Frontend: click Sign in with Civic
        Frontend->>Backend: GET /auth/login
        Backend-->>User: redirect → Civic OAuth
        User->>Backend: GET /auth/callback?code=...
        Backend->>Backend: resolve OAuth code → set session cookie
        Backend-->>Frontend: redirect → /dashboard
        Frontend->>Backend: GET /auth/user (cookie)
        Backend-->>Frontend: {id, email, ...}
    end
```

## Stack

- backend: FastAPI + SQLAlchemy (async) + PostgreSQL
- auth: Civic Auth (cookie-based OAuth)
- data: yfinance, NewsAPI / Finnhub, SEC EDGAR (no API key)
- LLM: OpenRouter (direct httpx, no LangChain dependency)
- scheduler: APScheduler (refresh every 30 min by default)
- frontend: React + Vite + TanStack Query + React Router

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL (or a hosted instance — Railway works great)
- `uv` for Python package management (`pip install uv`)

## Local Setup

### 1. Environment variables

```bash
cp .env.example .env
```

Fill in at minimum:
- `CIVIC_CLIENT_ID` — from [civic.com](https://civic.com)
- `DATABASE_URL` — e.g. `postgresql+asyncpg://user:pass@localhost:5432/portfolio_advisor`
- `OPENROUTER_API_KEY` — from [openrouter.ai](https://openrouter.ai)

### 2. Backend

```bash
# Create venv with Python 3.11
uv venv --python 3.11 backend/.venv

# Install dependencies
uv pip install -r backend/requirements.txt --python backend/.venv/bin/python

# Run migrations (from project root)
PYTHONPATH=/path/to/project uv run --python backend/.venv/bin/python \
  -m alembic -c backend/alembic.ini upgrade head

# Start the server
PYTHONPATH=/path/to/project backend/.venv/bin/uvicorn backend.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev   # starts on http://localhost:5173
```

### 4. Auth flow

Navigate to `http://localhost:5173`. Click "Sign in with Civic" — you'll be redirected through Civic's OAuth and land back on `/dashboard`.

## API Reference

All endpoints require authentication (Civic session cookie) unless noted.

### Auth
| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/login` | Redirect to Civic OAuth |
| GET | `/auth/callback` | OAuth callback → redirects to `/dashboard` |
| GET | `/auth/user` | Returns current user info (no auth required) |
| POST | `/auth/logout` | Clear session cookie |

### Portfolios
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolios` | List user portfolios |
| POST | `/api/portfolios` | Create portfolio `{"name": "..."}` |
| DELETE | `/api/portfolios/{id}` | Delete portfolio |

### Stocks
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolios/{id}/stocks` | List stocks with scores |
| POST | `/api/portfolios/{id}/stocks` | Add stock `{"ticker": "AAPL"}` — validates via yfinance, scores immediately |
| DELETE | `/api/portfolios/{id}/stocks/{ticker}` | Remove stock |

### Scores
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/scores` | All scores for current user |
| GET | `/api/scores/{ticker}` | Score for a specific ticker |
| GET | `/api/scores/{ticker}/rationale` | LLM-generated rationale |
| GET | `/api/scores/{ticker}/history?limit=30` | Score history (max 500) |

### Preferences
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/preferences` | Get user preferences |
| PUT | `/api/preferences` | Update preferences (triggers background rescore) |
| GET | `/api/preferences/preview` | Preview scores with hypothetical preferences |

### Custom Criteria
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/criteria` | List criteria (max 20) |
| POST | `/api/criteria` | Create criterion |
| PUT | `/api/criteria/{id}` | Update criterion |
| DELETE | `/api/criteria/{id}` | Delete criterion |

Criterion body: `{"name", "description", "weight" (1–10), "metric", "operator" (gt/lt/gte/lte/eq), "threshold"}`

Available metrics: `price`, `volume`, `volatility`, `beta`, `pe_ratio`, `debt_to_equity`, `market_cap`

### Alert Thresholds
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/thresholds` | List thresholds |
| POST | `/api/thresholds` | Upsert threshold `{"ticker": "AAPL", "threshold": 70}` |
| DELETE | `/api/thresholds/{ticker}` | Delete threshold |

### Admin / Health
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness + DB check (no auth) |
| POST | `/admin/refresh` | Manually trigger data + LLM refresh cycle |

## WebSocket

Connect to `ws://localhost:8000/ws/{user_id}?token={civic_token}` for live updates.

Events pushed to the client:

| Event | Payload |
|-------|---------|
| `score_update` | `{ticker, risk_score, recommendation, breakdown}` |
| `rationale_update` | `{ticker, rationale, rationale_at}` |
| `threshold_alert` | `{ticker, risk_score, threshold}` |
| `data_stale` | `{ticker}` |

## Scoring Model

Risk score is 0–100 (0 = low risk / BUY, 100 = high risk / SELL).

Components (weights renormalized when data is missing):
- volatility (30%) — annualized, normalized to 0–100
- beta (25%) — normalized at 3.0 = 100
- debt/equity (25%) — normalized at 3.0 = 100
- sector risk (20%) — fixed lookup table

Adjustments applied on top:
- risk tolerance multiplier (±25%)
- time horizon multiplier (short +10%, long −10%)
- growth vs value multiplier (±5%)
- custom criteria add up to +20 points

Thresholds: score < 35 → BUY, score ≥ 65 → SELL, otherwise HOLD.

## LLM Rationale

Rationales are generated via OpenRouter (direct httpx, no LangChain). Each refresh cycle:
1. Gathers news sentiment (NewsAPI or Finnhub), earnings (yfinance), SEC filings (EDGAR)
2. Builds a prompt with the risk score and gathered signals
3. Calls the configured model (default: `mistralai/mistral-7b-instruct`)
4. Persists the rationale and broadcasts a `rationale_update` WebSocket event

Only tickers whose score has changed by more than `LLM_DELTA_THRESHOLD` (default 5.0) since the last rationale are processed. Capped at `LLM_MAX_TICKERS_PER_CYCLE` (default 50) per cycle.

## Railway Deployment

Push to your Railway project. The `railway.toml` start command runs migrations then starts the server automatically.

Set these environment variables in Railway:
- `CIVIC_CLIENT_ID`
- `DATABASE_URL` (Railway provides this automatically for Postgres add-ons)
- `OPENROUTER_API_KEY`
- `FRONTEND_ORIGIN` — your deployed frontend URL

## Project Structure

```
.
├── backend/
│   ├── adapters/          # Data source adapters (yfinance, NewsAPI, Finnhub, SEC EDGAR)
│   ├── migrations/        # Alembic migrations
│   ├── routers/           # FastAPI route handlers
│   ├── tests/             # Unit and integration tests
│   ├── agent.py           # Layer 1: data pipeline + scoring
│   ├── auth.py            # Civic Auth integration
│   ├── llm_agent.py       # Layer 2: LLM rationale generation
│   ├── main.py            # App entry point, scheduler, middleware
│   ├── models.py          # Pydantic models
│   ├── models_orm.py      # SQLAlchemy ORM models
│   ├── scoring.py         # Pure scoring functions
│   └── settings.py        # Pydantic-settings config
├── frontend/
│   └── src/
│       ├── components/    # StockCard
│       ├── context/       # AuthContext
│       ├── hooks/         # useApi, useWebSocket
│       └── pages/         # Dashboard, PortfolioView, Preferences, Criteria, Thresholds
├── .env.example
├── tools_config.yaml      # Enable/disable data adapters
└── railway.toml
```
