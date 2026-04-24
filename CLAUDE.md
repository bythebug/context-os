# ContextOS — AI Agent Instructions

Read `MEMORY.md` first. It has current project state, what's done, what's next, key decisions,
and known gotchas. It is the authoritative context for continuing work on this project.
Read `README.md` for user-facing product docs, API reference, and architecture.

---

## Project context

ContextOS is a model-agnostic memory infrastructure REST API for LLM apps.
Stack: Python + FastAPI, Postgres + pgvector, Redis, sentence-transformers (local) or OpenAI for embeddings.
Current stage: M2 production hardening (see README roadmap).

---

## Running the stack

```bash
docker-compose up -d          # start Postgres (port 5433), Redis, app (port 8000)
curl localhost:8000/health    # verify all three services ok

# Create an API key (needed for all endpoints)
python scripts/seed_api_key.py --app-name "test" \
  --database-url postgresql://contextos:contextos@localhost:5433/contextos

# Run smoke tests
CONTEXTOS_API_KEY=sk-... pytest tests/test_smoke.py -v
```

## Key files

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI app, middleware, lifespan (startup validation + model pre-warm) |
| `app/logging_config.py` | structlog JSON config, X-Request-ID context binding |
| `app/api/sessions.py` | POST /sessions — extraction pipeline with retry + dead-letter |
| `app/api/memory.py` | GET /memory, DELETE /memory/:id |
| `app/extraction/` | Extraction providers: anthropic, openai, mock |
| `app/extraction/embeddings.py` | Embedding providers: local (sentence-transformers), openai |
| `app/models/fragment.py` | ORM models: App, ApiKey, Fragment, DeadLetterSession |
| `migrations/` | Raw SQL migrations (001 = schema, 002 = dead-letter table) |
| `.env` | Local config — do not commit |

## Current local config

```
EXTRACTION_PROVIDER=mock      # no API key needed; switch to anthropic/openai when credits available
EMBEDDING_PROVIDER=local      # sentence-transformers all-MiniLM-L6-v2, 384 dims
```

## gstack

This project uses [gstack](https://github.com/garrytan/gstack) for AI-assisted workflows.

```bash
git clone --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
cd ~/.claude/skills/gstack && ./setup --team
```

Use `/browse` for all web browsing. Use `/qa`, `/review`, `/ship`, `/investigate` as needed.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. The
skill has multi-step workflows, checklists, and quality gates that produce better
results than an ad-hoc answer. When in doubt, invoke the skill. A false positive is
cheaper than a false negative.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke /office-hours
- Strategy, scope, "think bigger", "what should we build" → invoke /plan-ceo-review
- Architecture, "does this design make sense" → invoke /plan-eng-review
- Design system, brand, "how should this look" → invoke /design-consultation
- Design review of a plan → invoke /plan-design-review
- Developer experience of a plan → invoke /plan-devex-review
- "Review everything", full review pipeline → invoke /autoplan
- Bugs, errors, "why is this broken", "wtf", "this doesn't work" → invoke /investigate
- Test the site, find bugs, "does this work" → invoke /qa (or /qa-only for report only)
- Code review, check the diff, "look at my changes" → invoke /review
- Visual polish, design audit, "this looks off" → invoke /design-review
- Developer experience audit, try onboarding → invoke /devex-review
- Ship, deploy, create a PR, "send it" → invoke /ship
- Merge + deploy + verify → invoke /land-and-deploy
- Configure deployment → invoke /setup-deploy
- Post-deploy monitoring → invoke /canary
- Update docs after shipping → invoke /document-release
- Weekly retro, "how'd we do" → invoke /retro
- Second opinion, codex review → invoke /codex
- Safety mode, careful mode, lock it down → invoke /careful or /guard
- Restrict edits to a directory → invoke /freeze or /unfreeze
- Upgrade gstack → invoke /gstack-upgrade
- Save progress, "save my work" → invoke /context-save
- Resume, restore, "where was I" → invoke /context-restore
- Security audit, OWASP, "is this secure" → invoke /cso
- Make a PDF, document, publication → invoke /make-pdf
- Performance regression, page speed, benchmarks → invoke /benchmark
- Code quality dashboard → invoke /health
