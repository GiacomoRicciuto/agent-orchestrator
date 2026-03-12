# Agent Orchestrator

Platform for automated provisioning and management of AI agent microservice instances.

Each customer gets an **isolated, self-improving instance** deployed on Railway with their own API keys, data, and agents.

## What It Does

1. **User signs up** → creates account with email/password
2. **Browses marketplace** → picks a template (e.g., "ElevenLabs Voice Agent Optimizer")
3. **Enters their API keys** → ElevenLabs, Notion, LLM provider of choice
4. **Sets instance password** → becomes the admin key for their private instance
5. **System provisions** → creates Railway project, service, volume, env vars, deploys
6. **User gets a link** → their own private instance, fully isolated, self-improving

## Tech Stack

- **Backend**: FastAPI (Python 3.13)
- **Database**: PostgreSQL (async via SQLAlchemy 2.0)
- **Auth**: bcrypt + JWT
- **Encryption**: Fernet (customer API keys encrypted at rest)
- **Provisioning**: Railway GraphQL API
- **Payments**: Stripe (credits/sprints system)
- **Frontend**: Single HTML SPA (dark theme, n8n-inspired)

## Quick Start (Local Dev)

```bash
# 1. Clone and install
cd agent-orchestrator
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Start PostgreSQL (Docker)
docker run -d --name ao-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=orchestrator -p 5432:5432 postgres:16

# 3. Configure
cp .env.example .env
# Edit .env with your values

# 4. Run
python -m app.main
# → http://localhost:8000
```

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the complete system design.

## Sprint Pricing

| LLM | Model | ~Cost/Sprint |
|-----|-------|-------------|
| Anthropic | Claude Sonnet 4 | €0.65 |
| OpenAI | GPT-4o | €0.60 |
| Google | Gemini 2.0 Flash | €0.20 |
| Self-hosted | Ollama/HF | €0.15 |

*1 sprint = 1 autonomous session (initializer, optimizer, or refiner)*
*Minimum 4 sprints to create one complete agent*
