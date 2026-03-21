# Stock Portfolio Advisor

A full-stack stock portfolio advisor with personalized risk scoring, LLM-generated rationale, and live WebSocket updates.

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL

### Backend

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in required values
alembic upgrade head
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Environment Variables

Copy `.env.example` to `.env` and fill in at minimum:
- `CIVIC_CLIENT_ID` — from [civic.com](https://civic.com)
- `DATABASE_URL` — PostgreSQL connection string
- `OPENROUTER_API_KEY` — from [openrouter.ai](https://openrouter.ai)

### Railway Deployment

Push to your Railway project. The `railway.toml` start command runs migrations then starts the server automatically.
