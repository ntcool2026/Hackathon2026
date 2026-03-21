# Design Document: LLM Agent Loop

## Overview

The LLM Agent Loop feature upgrades `backend/llm_agent.py` from a single-shot prompt-response pattern into a proper agentic loop. The cycle runs as follows:

1. **Pre-fetch phase** — all enabled adapters are called concurrently via `asyncio.gather`; results are injected directly into the user message as structured JSON blocks. No function calling is used.
2. **Initial analysis** — the LLM produces a first-pass `AI_RISK_SCORE`, `AI_RECOMMENDATION`, and `RATIONALE`.
3. **Reflection phase** — the LLM critiques its own output up to `LLM_MAX_REFLECTION_ROUNDS` times, stopping early when the score delta is below `LLM_REFLECTION_DELTA`.
4. **Memory injection** — the previous cycle's score and rationale are prepended to the system prompt so the LLM can reason about what changed.
5. **Portfolio analysis** — after all per-ticker loops finish, a single cross-ticker pass identifies concentration risk and broadcasts a `portfolio_analysis` WebSocket event.
6. **Chat endpoint** — `POST /api/chat` exposes a conversational interface backed by the same model fallback chain, with per-user 5-turn history in server-side memory.

> **Implementation note**: The original design called for OpenRouter function calling (tool-call phase). The shipped implementation replaced this with `_prefetch_tool_data` — all adapters are fetched concurrently in Python and the results are injected into the prompt. The `_run_tool_call_phase` function is retained in the codebase but is no longer called from `_generate_rationale`. This change was made because free-tier models on OpenRouter have inconsistent function-calling support.

All LLM calls use direct `httpx` calls to `https://openrouter.ai/api/v1/chat/completions`. LangChain is **not** used for execution; the `ToolRegistry` is read only to extract adapter metadata and build the `adapter_map` used by `_prefetch_tool_data`.

---

## Architecture

```mermaid
flowchart TD
    subgraph Scheduler["Refresh Cycle (APScheduler)"]
        DP[run_data_pipeline] --> LLC[run_llm_agent_cycle]
    end

    subgraph AgentLoop["run_llm_agent_cycle (per ticker)"]
        MEM[1. Load Memory\nfrom stock_scores] --> PREFETCH[2. Pre-fetch Tool Data\nasyncio.gather all adapters]
        PREFETCH --> INIT[3. Initial Analysis\nparse AI_RISK_SCORE etc.]
        INIT --> REF[4. Reflection Loop\nmax LLM_MAX_REFLECTION_ROUNDS]
        REF --> PERSIST[5. Persist & Broadcast\nrationale_update WS event]
    end

    LLC --> AgentLoop
    AgentLoop --> PA[run_portfolio_analysis\nper user]
    PA --> WS[portfolio_analysis WS event]

    subgraph ChatEndpoint["POST /api/chat"]
        CE[ChatRouter] --> HIST[Load 5-turn history\nfrom memory dict]
        HIST --> PCTX[Inject portfolio context]
        PCTX --> LLM[OpenRouter call\nfallback chain]
        LLM --> SAVE[Save turn to history]
    end
```

### Key Design Decisions

- **Pre-fetch instead of function calling**: `_prefetch_tool_data(ticker, adapter_map)` calls all adapters concurrently with `asyncio.gather` and injects results as `[tool_name] {json}` blocks in the user message. This is more reliable than function calling across free-tier models.
- **Model fallback chain**: 8 models across diverse providers — `mistral-7b`, `llama-3.1-8b`, `gemma-3-4b`, `qwen3-8b`, `nemotron`, `stepfun`, `phi-4`, `deepseek-r1`. Models that return HTTP 429 are skipped after a 1-second sleep.
- **Output guardrails**: `_extract_structured_block` strips `<think>...</think>` reasoning blocks and fast-forwards to the first `AI_RISK_SCORE:` line. `_sanitize_rationale` detects ~12 leaked-prompt patterns and replaces bad output with a score-derived fallback sentence. Sanitizer runs twice: before and after the reflection loop.
- **Chat history in memory**: `dict[user_id, list[dict]]` stored as a module-level variable in `routers/chat.py`. Not persisted to DB; lost on restart. Capped at 5 turns (10 messages).
- **Portfolio analysis timeout**: wrapped in `asyncio.wait_for(..., timeout=60)` per user.
- **Auth**: all protected routes use `get_or_create_user(user, db)` to extract `user_id`. Civic Auth JWT uses `"id"` not `"sub"`.

---

## Components and Interfaces

### 1. `backend/settings.py` — Settings

```python
llm_reflection_delta: float = 3.0       # LLM_REFLECTION_DELTA
llm_max_reflection_rounds: int = 2      # LLM_MAX_REFLECTION_ROUNDS (capped at 3)
llm_max_tool_calls: int = 5             # LLM_MAX_TOOL_CALLS (retained, unused by main loop)
llm_model: str = "mistralai/mistral-7b-instruct:free"
```

A `@field_validator` on `llm_max_reflection_rounds` enforces the hard cap of 3.

### 2. `backend/llm_agent.py` — Agent Functions

#### `_prefetch_tool_data(ticker, adapter_map) -> dict[str, Any]`

Fetches all adapters concurrently. Returns `{tool_name: validated_result}`. Failures are logged at WARNING and excluded from the result (not propagated).

#### `_build_analysis_user_message(ticker, risk_score, tool_data=None) -> str`

Builds the user message. When `tool_data` is provided, injects each result as `[tool_name] {json}` (capped at 800 chars per tool). Falls back to quant-score-only message when no data is available.

#### `_build_system_prompt(ticker, memory) -> str`

Builds the system message. Instructs the model to output only the three structured lines. If `memory` is not `None` and the previous rationale passes the leaked-prompt check, prepends previous score/rec/rationale (truncated to 300 chars). Combined prompt capped at 16 000 chars.

#### `_extract_structured_block(raw) -> str`

Strips `<think>...</think>` blocks, then fast-forwards to the first `AI_RISK_SCORE:` line. Returns the original string if no structured lines are found.

#### `_sanitize_rationale(rationale, ticker, score, rec) -> str`

Returns a clean rationale. Replaces content that is empty, shorter than 15 chars, or matches any of 12 leaked-prompt regex patterns with a score-derived fallback sentence.

#### `_run_reflection_loop(messages, initial_score, initial_rec, initial_rationale) -> tuple[float, str, str]`

Runs up to `LLM_MAX_REFLECTION_ROUNDS` critique rounds. Stops early if `|new_score - prev_score| < LLM_REFLECTION_DELTA`. Returns `(score, recommendation, rationale)`.

#### `_call_openrouter_with_tools(messages, tool_schemas=None) -> dict`

Iterates the 8-model fallback chain. Skips on 429 (with 1s sleep) or HTTP errors. Returns the full response dict.

#### `_generate_rationale(ticker, risk_score, memory, tool_schemas, adapter_map) -> tuple[str, float|None, str|None]`

Main per-ticker entry point. Calls `_prefetch_tool_data`, builds messages, calls LLM for initial analysis, sanitizes, runs reflection loop, sanitizes again. Returns `(rationale, ai_score, ai_rec)`.

#### `run_portfolio_analysis(user_id, ticker_data) -> None`

Accepts `ticker_data: list[dict]` with `ticker`, `sector`, `ai_risk_score`, `ai_recommendation`. Computes concentration flags locally (no LLM needed for the math — sectors > 40% of portfolio). Calls LLM for a one-sentence summary. Broadcasts `portfolio_analysis` WS event.

### 3. `backend/routers/chat.py` — Chat Router

```
POST /api/chat
  Body:  {"message": str}
  Response: {"answer": str}
  Auth: require_auth (Civic Auth)
  Rate limit: 20/minute
```

Module-level `_chat_sessions: dict[str, list[dict]]` stores conversation history. Portfolio context (tickers, scores, recommendations, rationale) is loaded fresh from DB on each request.

### 4. WebSocket Events

`rationale_update` — broadcast per ticker after each agent loop completes:
```json
{
  "event": "rationale_update",
  "payload": {
    "ticker": "AAPL",
    "rationale": "...",
    "ai_risk_score": 42.0,
    "ai_recommendation": "HOLD",
    "rationale_at": "2026-03-21T10:00:00Z"
  }
}
```

`portfolio_analysis` — broadcast per user after all tickers complete:
```json
{
  "event": "portfolio_analysis",
  "payload": {
    "summary": "...",
    "concentration_flags": ["Technology"]
  }
}
```

---

## Data Models

```python
# backend/models.py
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    answer: str

class PortfolioAnalysisResult(BaseModel):
    summary: str = Field(..., max_length=500)
    concentration_flags: list[str] = Field(default_factory=list)
```

Memory structure (in-memory, `routers/chat.py`):
```python
_chat_sessions: dict[str, list[dict[str, str]]] = {}
_MAX_TURNS = 5  # 5 user + 5 assistant = 10 messages
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Adapter fetch fails in pre-fetch | Logged at WARNING, excluded from tool_data, loop continues |
| LLM returns 429 | 1s sleep, try next model in fallback chain |
| Initial parse fails (no AI_RISK_SCORE) | Falls back to quant score, rec=HOLD, empty rationale |
| Reflection parse fails | Retains previous round's values, stops reflection |
| Rationale matches leaked-prompt pattern | Replaced with score-derived fallback sentence |
| Empty portfolio on chat request | Returns static "no holdings" message without LLM call |
| Portfolio analysis < 2 tickers | Skipped entirely |
| Portfolio analysis timeout (60s) | Logged at WARNING, skipped for that user |
| All 8 models exhausted | `last_error` raised, caught by `_generate_rationale` try/except |

---

## Test Coverage

### What is tested (86 tests, all passing)

| Area | Test file | Coverage |
|---|---|---|
| Scoring engine — unit | `test_scoring.py` | Normalizers, `compute_recommendation`, `evaluate_criterion`, `compute_risk_score` — 14 classes, ~30 cases |
| Scoring engine — property | `test_scoring_property.py` | 4 properties × 100–200 examples: sensitivity, determinism, component ranges, threshold boundaries |
| LLM parser | `test_llm_parser.py` | 20 unit tests: structured format, fallback extraction, edge cases, clamping, case-insensitivity |
| Adapters — property | `test_adapters_property.py` | validate_output required-key rejection, truncation, ToolRegistry enabled/disabled filtering, error messages, fetch round-trips, news/SEC/earnings output shape |
| Models — property | `test_models_property.py` | StockData serialization round-trip (100 examples), malformed payload rejection (100 examples) |

### What is NOT tested

The following areas from the original design's testing strategy were not implemented:

- `_build_system_prompt` memory injection properties (P1–P3)
- `_run_tool_call_phase` message structure and call count cap (P5–P6) — function is retained but not called by main loop
- `_run_reflection_loop` — at-least-one-round, early stopping, max rounds cap (P7–P10)
- Chat history cap and portfolio context injection (P11–P12)
- Concentration flags threshold property (P13)
- Portfolio summary length cap (P14)
- WS broadcast event type (P15)
- `LLM_MAX_REFLECTION_ROUNDS` env cap (P16)
- INFO log fields (P17)
- `POST /api/chat` endpoint integration tests (auth, rate limit, empty portfolio)

These are all unit-testable without a live DB or LLM — they test pure functions and in-memory state. Adding them would bring the agent loop to the same coverage level as the scoring engine.

---

## Sequence Diagrams

### `_generate_rationale` — per-ticker agent loop

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant A as llm_agent.py
    participant DB as stock_scores (DB)
    participant ADP as Adapters (yfinance/news/SEC)
    participant OR as OpenRouter

    S->>A: _process_ticker_for_users(ticker, ...)
    A->>DB: _load_memory(user_id, ticker)
    DB-->>A: {ai_risk_score, ai_recommendation, rationale} or None

    A->>ADP: _prefetch_tool_data() — asyncio.gather all adapters
    ADP-->>A: {tool_name: validated_result, ...}

    A->>A: _build_system_prompt(ticker, memory)
    A->>A: _build_analysis_user_message(ticker, score, tool_data)

    A->>OR: _call_openrouter_with_tools(messages) — initial analysis
    OR-->>A: {choices[0].message.content}

    A->>A: _extract_structured_block(raw)
    A->>A: _parse_structured_output(raw) → (score, rec, rationale)
    A->>A: _sanitize_rationale(rationale, ...) — first pass

    loop Reflection (up to LLM_MAX_REFLECTION_ROUNDS)
        A->>OR: _call_openrouter_with_tools(messages + critique)
        OR-->>A: revised score/rec/rationale
        A->>A: check delta < LLM_REFLECTION_DELTA → break early
    end

    A->>A: _sanitize_rationale(rationale, ...) — second pass
    A->>DB: _persist_rationale(user_id, ticker, ...)
    A->>WS: broadcast rationale_update event
```

### `POST /api/chat` — conversational flow

```mermaid
sequenceDiagram
    participant U as User (browser)
    participant C as chat.py router
    participant DB as stock_scores (DB)
    participant OR as OpenRouter

    U->>C: POST /api/chat {message: "..."}
    C->>C: get_or_create_user(user, db) → user_id
    C->>DB: SELECT stock_scores WHERE user_id = ?
    DB-->>C: [{ticker, ai_risk_score, ai_recommendation, rationale}, ...]

    alt portfolio is empty
        C-->>U: {"answer": "You have no holdings yet..."}
    else portfolio has holdings
        C->>C: _build_chat_system_prompt(portfolio)
        C->>C: load _chat_sessions[user_id] history
        C->>OR: _call_openrouter_with_tools(system + history + user_msg)
        OR-->>C: {choices[0].message.content}
        C->>C: append turn, _trim_history (cap at 5 turns)
        C-->>U: {"answer": "..."}
    end
```

### Full refresh cycle — data flow

```mermaid
sequenceDiagram
    participant APSched as APScheduler
    participant DP as run_data_pipeline
    participant LLC as run_llm_agent_cycle
    participant DB as PostgreSQL
    participant ADP as Adapters
    participant OR as OpenRouter
    participant WS as WebSocket clients

    APSched->>DP: trigger (every 30 min)
    DP->>ADP: fetch market data for all tickers
    ADP-->>DP: StockData
    DP->>DB: upsert stock_data, compute & upsert stock_scores

    DP->>LLC: run_llm_agent_cycle()
    LLC->>DB: _get_candidates() — scores with delta >= threshold
    DB-->>LLC: [(user_id, ticker, score, prev_score), ...]

    loop per unique ticker (semaphore: LLM_CONCURRENCY)
        LLC->>DB: _load_memory()
        LLC->>ADP: _prefetch_tool_data() concurrently
        LLC->>OR: initial analysis + reflection
        LLC->>DB: _persist_rationale()
        LLC->>WS: broadcast rationale_update
        LLC->>LLC: asyncio.sleep(12s) — rate limit guard
    end

    loop per user with >= 2 tickers
        LLC->>DB: load sector data
        LLC->>OR: portfolio summary (1 LLM call)
        LLC->>WS: broadcast portfolio_analysis
    end
```

---

## Prompt Templates

### System prompt (no memory)

```
You are a financial risk scoring API. Respond with ONLY the three lines below —
no preamble, no explanation, no chain-of-thought, no tool commentary.
Any text outside these three lines will be discarded.

AI_RISK_SCORE: <integer 0-100>
AI_RECOMMENDATION: <BUY or HOLD or SELL>
RATIONALE: <one factual sentence about the stock's primary risk driver>
```

### System prompt (with memory from previous cycle)

```
You are a financial risk scoring API. Respond with ONLY the three lines below —
no preamble, no explanation, no chain-of-thought, no tool commentary.
Any text outside these three lines will be discarded.

AI_RISK_SCORE: <integer 0-100>
AI_RECOMMENDATION: <BUY or HOLD or SELL>
RATIONALE: <one factual sentence about the stock's primary risk driver>

Previous cycle for {ticker}: score={prev_score}, rec={prev_rec}, rationale={prev_rationale[:300]}
```

Combined system + user message is capped at 16 000 characters.

### User message (no tool data)

```
{ticker} quant_risk_score={risk_score:.1f}/100.
AI_RISK_SCORE:
AI_RECOMMENDATION:
RATIONALE:
```

### User message (with pre-fetched tool data)

```
{ticker} quant_risk_score={risk_score:.1f}/100.

Market data:
[fetch_earnings] {"ticker": "AAPL", "price": 189.3, ...}  ← capped at 800 chars
[fetch_news_sentiment] {"sentiment": 0.4, "article_count": 3, ...}
[fetch_sec_filings] {"filings": [...]}

AI_RISK_SCORE:
AI_RECOMMENDATION:
RATIONALE:
```

### Reflection / critique prompt

```
Previous: score={score:.1f}, rec={rec}, rationale={rationale}
Revise if needed. Output only:
AI_RISK_SCORE:
AI_RECOMMENDATION:
RATIONALE:
```

### Guardrail — leaked-prompt patterns detected by `_sanitize_rationale`

If the rationale matches any of these patterns it is replaced with a score-derived fallback:

```
[one sentence]
<one sentence
<2-3 sentences
[0-100]
[BUY|HOLD|SELL]
<integer
output (only|exactly) (these|three)
from the previous analysis.*it says
in the output format
should be one sentence
quant_score=
quant risk score is \d
```

---

## Failure Mode Decision Tree

```
_generate_rationale(ticker, ...)
│
├─ _prefetch_tool_data fails for one adapter
│   └─ Log WARNING, exclude that tool from tool_data, continue with remaining data
│
├─ _prefetch_tool_data fails for ALL adapters
│   └─ tool_data = {}, proceed with quant-score-only prompt
│
├─ _call_openrouter_with_tools returns 429
│   └─ Sleep 1s → try next model → ... → if all 8 exhausted: raise last_error
│       └─ Caught by _generate_rationale try/except → return fallback rationale
│
├─ _parse_structured_output finds no AI_RISK_SCORE
│   └─ initial_score = risk_score (quant fallback), rec = "HOLD", rationale = ""
│
├─ _sanitize_rationale detects leaked prompt
│   └─ Replace with: "{ticker} carries moderate risk (score X/100); ..."
│
├─ _run_reflection_loop — parse fails on a round
│   └─ Log WARNING, retain previous round's values, stop reflection
│
├─ _run_reflection_loop — delta < LLM_REFLECTION_DELTA
│   └─ Stop early, return current values
│
└─ Any unhandled exception in _generate_rationale
    └─ Log WARNING with ticker, return static fallback:
       "Automated analysis for {ticker} is temporarily unavailable."

run_portfolio_analysis(user_id, ...)
│
├─ len(ticker_data) < 2
│   └─ Return immediately, no LLM call
│
├─ LLM call fails
│   └─ summary = "Portfolio contains N holdings across M sectors." (no LLM)
│
└─ asyncio.wait_for timeout (60s)
    └─ Log WARNING with user_id, skip broadcast for this user
```

---

## Configuration Reference

| Environment variable | Default | Valid range | Controls |
|---|---|---|---|
| `LLM_MODEL` | `mistralai/mistral-7b-instruct:free` | Any OpenRouter model ID | Primary model; fallback chain starts here |
| `LLM_TEMPERATURE` | `0.2` | `0.0 – 1.0` | Sampling temperature for all LLM calls |
| `LLM_REFLECTION_DELTA` | `3.0` | `0.0 – 100.0` | Minimum score change to continue reflection |
| `LLM_MAX_REFLECTION_ROUNDS` | `2` | `1 – 3` (hard cap 3) | Max critique rounds per ticker |
| `LLM_MAX_TOOL_CALLS` | `5` | `1 – 20` | Retained for `_run_tool_call_phase`; unused by main loop |
| `LLM_CONCURRENCY` | `1` | `1 – 10` | Max tickers processed in parallel |
| `LLM_DELTA_THRESHOLD` | `5.0` | `0.0 – 100.0` | Min score change vs previous cycle to trigger LLM re-analysis |
| `LLM_MAX_TICKERS_PER_CYCLE` | `50` | `1 – 500` | Cap on tickers processed per refresh cycle |
| `REFRESH_INTERVAL_MINUTES` | `30` | `5 – 1440` | How often the full data + LLM pipeline runs |
| `REFRESH_CYCLE_TIMEOUT_MINUTES` | `25` | `1 – 60` | Hard timeout for a single refresh cycle |
| `OPENROUTER_API_KEY` | _(required)_ | — | API key for OpenRouter |

---

## Deliberate Trade-offs and Out-of-Scope Decisions

These are gaps that were consciously left out, not oversights.

**Persistent chat history**
Chat sessions are stored in a module-level dict and lost on server restart. Persisting to DB would require a new table, migration, and session expiry logic. For a hackathon the in-memory approach is sufficient; the 5-turn cap limits the blast radius of a restart.

**Agent-initiated refresh**
The agent runs on a fixed 30-minute scheduler, not in response to market events. Triggering a refresh when news volume spikes or a price moves significantly would require a separate event-detection layer (e.g. polling a news feed, watching price WebSocket). This was out of scope.

**Sector-aware tool selection**
All enabled adapters are pre-fetched for every ticker regardless of sector. A more sophisticated approach would skip SEC filings for ETFs, skip earnings data for REITs with no EPS, etc. This would require sector metadata at fetch time and adds complexity for marginal token savings.

**Function calling (OpenRouter)**
The original design used OpenRouter's `tools` API so the LLM could decide which adapters to call. This was replaced with pre-fetching because free-tier models have inconsistent function-calling support — some return plain text, some hallucinate tool names, and the fallback logic to detect this added more complexity than the feature was worth at this stage. The `_run_tool_call_phase` function is retained for future use.

**Per-user rationale**
Rationale is computed once per ticker using the average score across all users holding that ticker, then broadcast to all of them. A per-user rationale would account for each user's risk tolerance and preferences but would multiply LLM calls by the number of users per ticker.

**Frontend test coverage**
No frontend unit or integration tests were written. The React components were iterated on directly against the running backend. Adding Vitest + React Testing Library tests for the ChatPanel, PortfolioSummary, and WebSocket hook would be the highest-value frontend testing investment.
