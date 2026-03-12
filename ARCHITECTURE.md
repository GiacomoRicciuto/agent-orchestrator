# Agent Orchestrator — Architecture Document

> Platform for automated provisioning and management of AI agent microservice instances.
> Each customer gets an isolated, self-improving instance deployed on Railway.

---

## 1. SYSTEM OVERVIEW

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AGENT ORCHESTRATOR (this project)                     │
│                    https://app.agentorchestrator.com                     │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │  Auth        │  │  Dashboard   │  │  Marketplace │  │  Billing   │  │
│  │  (email+pw)  │  │  (instances) │  │  (templates) │  │  (sprints) │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬─────┘  │
│         │                 │                  │                 │         │
│  ┌──────┴─────────────────┴──────────────────┴─────────────────┴──────┐  │
│  │                     ORCHESTRATOR API (FastAPI)                      │  │
│  │                                                                     │  │
│  │  POST /api/auth/register     POST /api/instances/create             │  │
│  │  POST /api/auth/login        GET  /api/instances                    │  │
│  │  POST /api/billing/topup     POST /api/instances/{id}/start-sprint  │  │
│  │  GET  /api/billing/balance   DELETE /api/instances/{id}             │  │
│  │  GET  /api/marketplace       GET  /api/instances/{id}/status        │  │
│  └─────────────────────────┬───────────────────────────────────────────┘  │
│                            │                                              │
│  ┌─────────────────────────┴───────────────────────────────────────────┐  │
│  │                     PROVISIONER ENGINE                               │  │
│  │                                                                      │  │
│  │  Uses Railway GraphQL API to:                                        │  │
│  │  1. projectCreate       → new Railway project                        │  │
│  │  2. serviceCreate       → new service in project                     │  │
│  │  3. serviceConnect      → connect to template GitHub repo            │  │
│  │  4. variableCollectionUpsert → set customer env vars                 │  │
│  │  5. volumeCreate        → persistent storage                         │  │
│  │  6. serviceDomainCreate → public URL                                 │  │
│  │  7. environmentTriggersDeploy → trigger deploy                       │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐    │
│  │  DATABASE (PostgreSQL on Railway)                                  │    │
│  │                                                                    │    │
│  │  users          │ instances        │ templates       │ sprints     │    │
│  │  ─────          │ ─────────        │ ─────────       │ ───────     │    │
│  │  id             │ id               │ id              │ id          │    │
│  │  email          │ user_id (FK)     │ name            │ user_id     │    │
│  │  password_hash  │ template_id (FK) │ description     │ instance_id │    │
│  │  credits        │ railway_project  │ github_repo     │ status      │    │
│  │  created_at     │ railway_service  │ required_vars   │ started_at  │    │
│  │                 │ railway_domain   │ cost_per_sprint │ ended_at    │    │
│  │  billing_txns   │ env_vars (enc)   │ llm_options     │ cost        │    │
│  │  ────────────   │ admin_api_key    │ icon            │ session_log │    │
│  │  id             │ status           │ category        │             │    │
│  │  user_id        │ created_at       │                 │             │    │
│  │  amount         │ last_sprint_at   │                 │             │    │
│  │  type           │ sprints_used     │                 │             │    │
│  │  stripe_id      │ sprints_total    │                 │             │    │
│  │  created_at     │                  │                 │             │    │
│  └───────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘

                                    │
                    Railway GraphQL API
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
        ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
        │  Customer      │ │  Customer      │ │  Customer      │
        │  Instance A    │ │  Instance B    │ │  Instance C    │
        │                │ │                │ │                │
        │  Railway Proj  │ │  Railway Proj  │ │  Railway Proj  │
        │  + Volume      │ │  + Volume      │ │  + Volume      │
        │  + Domain      │ │  + Domain      │ │  + Domain      │
        │                │ │                │ │                │
        │  ElevenLabs    │ │  ElevenLabs    │ │  Other         │
        │  Harness       │ │  Harness       │ │  Template      │
        │  (cloned repo) │ │  (cloned repo) │ │  (future)      │
        └───────────────┘ └───────────────┘ └───────────────┘
```

---

## 2. TECH STACK

| Component | Technology | Why |
|-----------|-----------|-----|
| Backend API | **FastAPI** (Python 3.13) | Async, fast, auto-docs, consistent with harness |
| Database | **PostgreSQL** (Railway addon) | Reliable, Railway native, good ORM support |
| ORM | **SQLAlchemy 2.0** + Alembic | Async support, migrations |
| Auth | **bcrypt** + **JWT** (PyJWT) | Standard, stateless, no session management needed |
| Frontend | **Single HTML SPA** (like harness) | Simple, no build step, consistent with existing project |
| Payments | **Stripe** Checkout + Webhooks | Industry standard, supports one-time credit purchases |
| Provisioning | **Railway GraphQL API** | Programmatic project/service/variable/volume management |
| Secrets | **Fernet** encryption (cryptography lib) | Customer API keys encrypted at rest in DB |
| Hosting | **Railway** (same as instances) | Dogfooding, simple |

---

## 3. CORE FLOWS

### 3.1 Registration & Login

```
User → POST /api/auth/register { email, password }
     → bcrypt hash → INSERT users → return JWT

User → POST /api/auth/login { email, password }
     → verify bcrypt → return JWT (24h expiry)

All subsequent requests: Authorization: Bearer <jwt>
```

### 3.2 Instance Creation

```
User → GET /api/marketplace
     → Returns list of templates with required_vars and cost_per_sprint

User → POST /api/instances/create {
    template_id: "elevenlabs-harness",
    config: {
        ELEVENLABS_API_KEY: "xi-...",
        NOTION_API_KEY: "secret_...",
        NOTION_PARENT_PAGE_ID: "abc123",
        ADMIN_API_KEY: "user-chosen-password",
        LLM_PROVIDER: "anthropic",           // or "openai", "ollama", "huggingface"
        LLM_API_KEY: "sk-ant-...",           // if applicable
        LLM_MODEL: "claude-sonnet-4-6",   // user picks
        LLM_BASE_URL: ""                     // for self-hosted
    }
}

Orchestrator:
  1. Verify user has >= 4 credits (minimum for first agent)
  2. Encrypt all API keys with Fernet
  3. INSERT instance record
  4. Call Railway API:
     a. projectCreate(name: "ao-{user_id}-{instance_id}")
     b. serviceCreate(projectId, name: "harness")
     c. serviceConnect(serviceId, repo: template.github_repo, branch: "main")
     d. volumeCreate(projectId, mountPath: "/data/generations")
     e. variableCollectionUpsert(serviceId, environmentId, variables: {
          ELEVENLABS_API_KEY: decrypted,
          NOTION_API_KEY: decrypted,
          NOTION_PARENT_PAGE_ID: value,
          ADMIN_API_KEY: value,
          ANTHROPIC_API_KEY: decrypted (if anthropic),
          OPENAI_API_KEY: decrypted (if openai),
          LLM_BASE_URL: value (if self-hosted),
          GENERATIONS_DIR: "/data/generations",
          GITHUB_TOKEN: platform-github-token,
          GITHUB_REPO: template.github_repo
        })
     f. serviceDomainCreate → get railway domain
     g. environmentTriggersDeploy → trigger build
  5. UPDATE instance with railway_project_id, railway_domain
  6. Return { instance_id, domain, status: "deploying" }
```

### 3.3 Sprint System (Billing)

```
1 Sprint = 1 autonomous session (initializer, optimizer, or refiner)
Minimum purchase: 4 sprints (enough for 1 complete agent)
Price per sprint: calculated from LLM cost + Railway compute + margin

User → POST /api/billing/topup { amount_eur: 20, payment_method_id: "pm_..." }
     → Stripe charge → credits += amount / price_per_sprint
     → INSERT billing_txn

When instance starts a sprint:
  1. Check user.credits >= 1
  2. Deduct 1 credit
  3. INSERT sprint record (status: "running")
  4. Instance runs the session
  5. When session ends: UPDATE sprint (status: "completed")

Sprint cost calculation:
  Base cost = LLM tokens (avg ~100K input + 20K output per session)
  + Railway compute (~$0.000463/min for 8GB container)
  + Platform margin (30%)

  Example with Claude Sonnet:
    LLM: ~$0.40/session (100K input @ $3/M + 20K output @ $15/M)
    Railway: ~$0.10/session (15 min avg)
    Margin: $0.15
    Total: ~$0.65/session → round to €1/sprint for simplicity
    (Adjust based on actual measurements)
```

### 3.4 Multi-LLM Support

```
Template defines which LLM providers are supported.
User selects provider + model at instance creation.

┌──────────────┬─────────────────┬──────────────────────────────┐
│ Provider     │ Env Vars        │ How it connects              │
├──────────────┼─────────────────┼──────────────────────────────┤
│ Anthropic    │ ANTHROPIC_API_KEY│ Direct API (current default) │
│ OpenAI       │ OPENAI_API_KEY  │ Via pi --model gpt-4o        │
│ Google       │ GOOGLE_API_KEY  │ Via pi --model gemini-2.0    │
│ Ollama       │ LLM_BASE_URL    │ OpenAI-compatible endpoint   │
│ HuggingFace  │ HF_API_KEY +   │ Inference API or TGI endpoint│
│              │ LLM_BASE_URL    │                              │
│ Any OpenAI-  │ LLM_API_KEY +  │ Custom base URL              │
│  compatible  │ LLM_BASE_URL    │                              │
└──────────────┴─────────────────┴──────────────────────────────┘

The harness client.py already supports ANTHROPIC_API_KEY.
For other providers: the orchestrator sets the appropriate env vars
and the harness's client.py routes to the correct pi model flag.
```

---

## 4. SECURITY MODEL

| Layer | Protection |
|-------|-----------|
| Auth | bcrypt password hashing, JWT with 24h expiry, httponly cookies |
| API Keys | Fernet-encrypted at rest in PostgreSQL, decrypted only during provisioning |
| Instances | Each customer = separate Railway project (full isolation) |
| Network | HTTPS everywhere (Railway provides SSL), CORS restricted |
| Admin | Platform admin endpoints require separate admin JWT |
| Billing | Stripe handles all payment data (PCI compliant), we never see card numbers |
| Rate Limiting | Per-user rate limits on instance creation (max 5/hour) |
| Secrets in Transit | Railway API calls use workspace token over HTTPS |
| Instance Access | Each instance has its own ADMIN_API_KEY set by the customer |

---

## 5. DATABASE SCHEMA

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    credits DECIMAL(10,2) DEFAULT 0.00,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Templates (marketplace items)
CREATE TABLE templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    icon VARCHAR(10),  -- emoji
    category VARCHAR(50),
    github_repo VARCHAR(200) NOT NULL,
    github_branch VARCHAR(50) DEFAULT 'main',
    required_vars JSONB NOT NULL,  -- [{name, label, type, placeholder, required}]
    llm_options JSONB,  -- [{provider, models[], default_model}]
    cost_per_sprint DECIMAL(6,2) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Customer instances
CREATE TABLE instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    template_id UUID REFERENCES templates(id),
    name VARCHAR(200),
    -- Railway resources
    railway_project_id VARCHAR(100),
    railway_service_id VARCHAR(100),
    railway_environment_id VARCHAR(100),
    railway_domain VARCHAR(300),
    -- Config (encrypted)
    encrypted_vars BYTEA,  -- Fernet-encrypted JSON of all API keys
    admin_api_key_hash VARCHAR(255),  -- bcrypt hash for verification
    -- LLM config
    llm_provider VARCHAR(50),
    llm_model VARCHAR(100),
    -- Status
    status VARCHAR(20) DEFAULT 'provisioning',  -- provisioning, active, stopped, error, deleted
    error_message TEXT,
    -- Usage
    sprints_used INTEGER DEFAULT 0,
    last_sprint_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Sprint history
CREATE TABLE sprints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    instance_id UUID REFERENCES instances(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'running',  -- running, completed, failed, cancelled
    phase VARCHAR(20),  -- brief, initializer, optimizer, refiner
    cost DECIMAL(6,2),
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    metadata JSONB  -- session stats, pass_rate, etc.
);

-- Billing transactions
CREATE TABLE billing_txns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    type VARCHAR(20) NOT NULL,  -- topup, sprint_deduct, refund, bonus
    amount DECIMAL(10,2) NOT NULL,  -- positive for topup, negative for deduct
    credits_delta DECIMAL(10,2) NOT NULL,
    description TEXT,
    stripe_payment_id VARCHAR(200),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_instances_user ON instances(user_id);
CREATE INDEX idx_instances_status ON instances(status);
CREATE INDEX idx_sprints_instance ON sprints(instance_id);
CREATE INDEX idx_sprints_user ON sprints(user_id);
CREATE INDEX idx_billing_user ON billing_txns(user_id);
```

---

## 6. FILE STRUCTURE

```
agent-orchestrator/
├── ARCHITECTURE.md          ← This file
├── README.md
├── requirements.txt
├── Dockerfile
├── docker-compose.yml       ← Local dev (postgres + app)
├── railway.json
├── alembic.ini
├── alembic/
│   └── versions/            ← DB migrations
├── app/
│   ├── __init__.py
│   ├── main.py              ← FastAPI app entry point
│   ├── config.py            ← Settings from env vars
│   ├── database.py          ← SQLAlchemy async engine + session
│   ├── models.py            ← SQLAlchemy ORM models
│   ├── security.py          ← JWT, bcrypt, Fernet encryption
│   ├── dependencies.py      ← Auth dependency (get_current_user)
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py          ← Register, login, profile
│   │   ├── marketplace.py   ← List templates
│   │   ├── instances.py     ← CRUD instances, start sprint
│   │   ├── billing.py       ← Topup, balance, transactions
│   │   └── admin.py         ← Admin: manage templates, users
│   ├── services/
│   │   ├── __init__.py
│   │   ├── railway.py       ← Railway GraphQL API client
│   │   ├── provisioner.py   ← Instance creation/deletion orchestration
│   │   ├── stripe_svc.py    ← Stripe integration
│   │   └── sprint_tracker.py← Sprint lifecycle management
│   └── utils/
│       ├── __init__.py
│       └── crypto.py        ← Fernet encrypt/decrypt helpers
├── frontend/
│   └── index.html           ← Single-page app (n8n-inspired UI)
├── seed/
│   └── templates.json       ← Initial marketplace templates
└── tests/
    ├── test_auth.py
    ├── test_instances.py
    └── test_billing.py
```

---

## 7. RAILWAY PROVISIONING SEQUENCE (DETAILED)

The provisioner uses Railway's GraphQL API (https://backboard.railway.com/graphql/v2)
with an Account Token that has access to the orchestrator's workspace.

```python
# Simplified provisioning flow

async def provision_instance(user, template, config):
    # 1. Create project
    project = await railway.mutation("projectCreate", {
        "input": {
            "name": f"ao-{user.id[:8]}-{instance.id[:8]}",
            "description": f"Agent instance for {user.email}",
            "teamId": RAILWAY_WORKSPACE_ID
        }
    })

    # 2. Get default environment
    envs = await railway.query("environments", {"projectId": project.id})
    env_id = envs[0].id  # "production" environment

    # 3. Create service from GitHub repo
    service = await railway.mutation("serviceCreate", {
        "input": {
            "projectId": project.id,
            "name": "harness"
        }
    })

    # 4. Connect to template repo
    await railway.mutation("serviceConnect", {
        "id": service.id,
        "input": {
            "repo": template.github_repo,
            "branch": template.github_branch
        }
    })

    # 5. Create volume
    await railway.mutation("volumeCreate", {
        "input": {
            "projectId": project.id,
            "environmentId": env_id,
            "mountPath": "/data/generations",
            "name": "generations"
        }
    })

    # 6. Set environment variables
    variables = build_env_vars(config, template)
    await railway.mutation("variableCollectionUpsert", {
        "input": {
            "projectId": project.id,
            "environmentId": env_id,
            "serviceId": service.id,
            "variables": variables
        }
    })

    # 7. Create public domain
    domain = await railway.mutation("serviceDomainCreate", {
        "input": {
            "serviceId": service.id,
            "environmentId": env_id
        }
    })

    # 8. Deploy
    await railway.mutation("serviceInstanceDeploy", {
        "serviceId": service.id,
        "environmentId": env_id
    })

    return {
        "project_id": project.id,
        "service_id": service.id,
        "environment_id": env_id,
        "domain": domain.domain
    }
```

---

## 8. ENV VARS FOR ORCHESTRATOR ITSELF

```
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/orchestrator

# Auth
JWT_SECRET=<random-64-char>
FERNET_KEY=<fernet-key-for-encrypting-customer-secrets>

# Railway API (for provisioning)
RAILWAY_API_TOKEN=<account-or-workspace-token>
RAILWAY_WORKSPACE_ID=<workspace-id>

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_... (for credit packages)

# Platform
PLATFORM_DOMAIN=https://app.agentorchestrator.com
ADMIN_EMAIL=admin@agentorchestrator.com
```

---

## 9. SPRINT COST MATRIX (PER LLM)

| LLM Provider | Model | Avg Input Tokens | Avg Output Tokens | LLM Cost | Railway Cost | Total/Sprint |
|-------------|-------|-----------------|------------------|----------|-------------|-------------|
| Anthropic | claude-sonnet-4-6 | 100K | 20K | ~€0.40 | ~€0.10 | ~€0.65 |
| Anthropic | claude-opus-4 | 100K | 20K | ~€2.10 | ~€0.10 | ~€2.85 |
| OpenAI | gpt-4o | 100K | 20K | ~€0.35 | ~€0.10 | ~€0.60 |
| OpenAI | gpt-4o-mini | 100K | 20K | ~€0.05 | ~€0.10 | ~€0.25 |
| Google | gemini-2.0-flash | 100K | 20K | ~€0.03 | ~€0.10 | ~€0.20 |
| Self-hosted | ollama/hf | 100K | 20K | €0.00 | ~€0.10 | ~€0.15 |

*Sprint price = LLM cost + Railway cost + 30% margin, rounded up*
*Self-hosted: customer runs their own inference, we only charge Railway compute*

---

## 10. WHAT CHANGES IN THE HARNESS (MINIMAL)

The ElevenLabs harness project remains UNTOUCHED except for one addition:

### Sprint Webhook (optional)
The orchestrator needs to know when a sprint starts/ends.
Options:
a. **Poll**: Orchestrator polls instance `/api/jobs/<id>/status` periodically
b. **Webhook**: Harness calls orchestrator webhook at session start/end
c. **Log parsing**: Orchestrator reads session.log via Railway API logs

**Recommended: Option (a) — Polling.** Zero changes to harness.
The orchestrator checks instance status every 60 seconds for active instances.

### LLM Provider Routing
The harness's `client.py` needs to support `--model` flag for non-Anthropic LLMs.
This is already partially supported by pi-coding-agent:
- `--model claude-sonnet-4-6` (Anthropic)
- `--model gpt-4o` (OpenAI)
- `--model gemini-2.0-flash` (Google)
- Custom models via ANTHROPIC_API_KEY / OPENAI_API_KEY env vars

For self-hosted (Ollama/HuggingFace): requires OPENAI_API_KEY + OPENAI_BASE_URL
pointing to the self-hosted endpoint (OpenAI-compatible API).

---

## 11. DEVELOPMENT PHASES

### Phase 1: Core Platform (MVP)
- [ ] FastAPI app with auth (register/login)
- [ ] PostgreSQL schema + migrations
- [ ] Template marketplace (read-only, seeded)
- [ ] Instance provisioning via Railway API
- [ ] Basic frontend (login, dashboard, create instance)
- [ ] Manual credit assignment (admin adds credits)

### Phase 2: Billing
- [ ] Stripe integration for credit purchases
- [ ] Sprint tracking and deduction
- [ ] Usage dashboard
- [ ] Invoice/receipt generation

### Phase 3: Multi-LLM
- [ ] LLM provider selection in instance creation
- [ ] Cost calculation per provider
- [ ] Harness client.py modifications for provider routing

### Phase 4: Polish
- [ ] n8n-inspired UI (dark theme, smooth animations)
- [ ] Instance health monitoring
- [ ] Email notifications (instance ready, sprint completed, low credits)
- [ ] Admin panel (manage users, templates, billing)

### Phase 5: Scale
- [ ] Template SDK (allow third-party templates)
- [ ] Affiliate/referral system
- [ ] Multi-region support
- [ ] Usage analytics dashboard
