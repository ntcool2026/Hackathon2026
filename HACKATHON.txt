# Stock Portfolio Advisor — Hackathon Summary

## What We Built

A full-stack AI-powered portfolio advisor that combines quantitative risk scoring with an agentic LLM loop. Users connect their portfolio, get per-ticker risk scores and AI-generated rationale, and can interrogate their holdings conversationally via a chat interface.

**Stack:** FastAPI + PostgreSQL + asyncpg (backend), React + TypeScript + Vite (frontend), OpenRouter (LLM gateway), Civic Auth (wallet-based authentication), Railway (deployment).

---

## What You Shipped

### Core pipeline
- Quant risk scoring engine — weighted composite of beta, P/E, short interest, PEG ratio, price momentum, and user-defined criteria
- LLM agentic loop — memory across cycles, concurrent tool pre-fetch (yfinance, news, SEC EDGAR), self-critique reflection, structured output parsing with guardrails
- Model fallback chain across 8 free-tier OpenRouter providers — rotates on 429s so rate limits on one provider don't stall the cycle
- WebSocket real-time push — `rationale_update` and `portfolio_analysis` events broadcast to connected clients as scores refresh

### API
- `POST /api/chat` — conversational portfolio advisor with 5-turn session history, portfolio context injected per request
- Full CRUD for portfolios, stocks, preferences, criteria, thresholds, and scores
- Civic Auth JWT validation on all protected routes
- Rate limiting via SlowAPI, async DB via SQLAlchemy + asyncpg

### Frontend
- Dashboard with portfolio list and summary chart (1w / 1y / 2y period selector)
- Stock cards with live AI risk score, recommendation badge, and rationale
- Slide-out chat drawer (360px) — Enter to send, typing indicator, portfolio-aware answers
- Portfolio analysis banner — dismissible, shows LLM summary + concentration flags, driven by WebSocket
- Dark theme throughout, Civic Auth login flow

### Quality
- 86 passing unit tests including property-based tests (Hypothesis) for scoring, adapters, models, and LLM parser
- 5 DB migrations tracked via Alembic
- Output guardrails: `<think>` block stripping, leaked-prompt detection, score-derived fallback rationale

---

## Speed and Ambition

Built in a single hackathon session. Scope covered what a small team would typically plan for a 2-week sprint:

- Spec-driven development (requirements → design → tasks) for both the base advisor and the LLM agent loop
- Full backend from scratch — models, migrations, routers, auth, scoring, agent, WebSocket manager
- Full frontend from scratch — auth context, routing, pages, components, hooks
- Property-based test suite alongside implementation

---

## AI-Assisted Process

Kiro was used for the entire development loop — spec writing, code generation, debugging, test writing, and git. Key moments where AI assistance made a real difference:

- Spec workflow gave the AI structured context (user stories + acceptance criteria) to generate correct implementations first time rather than iterating on vague prompts
- Bugs caught and fixed in the same turn they appeared: `KeyError: 'sub'` in Civic Auth (uses `"id"` not `"sub"`), duplicate function definition left by a mid-edit context cutoff, `tools_config.yaml` path resolution when running from a subdirectory
- Property-based tests generated from the spec acceptance criteria — not written by hand
- Output guardrails iterated rapidly: prompt tightening, `_extract_structured_block`, `_sanitize_rationale`, and leaked-prompt regex all developed in a few back-and-forth turns

Main friction: context window limits required a session summary and handoff. Mid-edit cutoffs occasionally left files in a broken state, caught by diagnostics on the next turn.

---

## Creativity

Most portfolio tools are either pure data dashboards or black-box robo-advisors. This sits in between:

- Shows the quant score *and* the AI's reasoning side by side — the user can see why a stock is flagged, not just that it is
- Conversational interface lets users interrogate their portfolio in plain English without navigating multiple screens
- Portfolio-level analysis flags concentration risk across holdings — something you miss looking at individual stocks
- Civic Auth (wallet-based identity) is a natural fit for a finance app — no email/password, no PII stored
- The agentic loop with self-critique is a genuine step beyond "call LLM once and display result" — the agent fetches real market data, reasons about it, then reviews its own output before committing a score

---

## Agent Evaluation

| Dimension | Rating | Notes |
|---|---|---|
| Autonomy | Moderate | Fully autonomous within a cycle; scheduler-triggered, not self-initiated |
| Usefulness | High | Real portfolio data, conversational interface, concentration risk flags |
| Technical depth | Good | Tool use, memory, error recovery, reflection loop — reasoning is present but shallow |

What would push this further: agent-initiated refresh when news volume spikes, persistent chat history, tool selection based on ticker sector rather than fetching everything.

---

## Tools and Technologies

### AI Tools
- **Kiro** — AI IDE used for the full development loop: spec writing, code generation, debugging, test generation, and git operations
- **Cerebras AI** — LLM API providing access to high-performance models (`https://api.cerebras.ai/v1/chat/completions`)
- **LLM model used**: `qwen-3-235b-a22b-instruct-2507`
  - `stepfun/step-3.5-flash:free`
  - `microsoft/phi-4-reasoning-plus:free`
  - `deepseek/deepseek-r1-0528-qwen3-8b:free`

### Backend
- **Python 3.11**
- **FastAPI** — async REST API framework
- **SQLAlchemy (asyncio) + asyncpg** — async ORM and PostgreSQL driver
- **Alembic** — database migrations
- **APScheduler** — background refresh scheduler
- **httpx** — async HTTP client for OpenRouter calls
- **civic-auth[fastapi]** — wallet-based JWT authentication via Civic
- **SlowAPI** — rate limiting middleware
- **pydantic-settings** — environment variable configuration
- **yfinance** — earnings and market data adapter
- **Finnhub** — news sentiment adapter
- **SEC EDGAR** — regulatory filings adapter
- **Hypothesis** — property-based testing framework
- **pytest + pytest-asyncio** — test runner

### Frontend
- **React 18 + TypeScript**
- **Vite** — build tool and dev server
- **React Router v6** — client-side routing
- **TanStack Query (React Query v5)** — server state management and data fetching
- **Recharts** — charting library (performance chart)
- **Native WebSocket API** — real-time score and analysis updates

### Infrastructure
- **PostgreSQL** — primary database
- **Railway** — deployment platform (backend + database)
- **Git / GitHub** — version control

---

## Known Gaps

- Free-tier LLM models are inconsistent — sanitizer catches most bad output but not all
- 12-second sleep between tickers (rate limit guard) means large portfolios refresh slowly
- Chat history is in-memory only — resets on server restart
- Portfolio analysis requires 2+ tickers to run
