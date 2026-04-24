# ContextOS — AI Agent Instructions

**Read `MEMORY.md` first.** It is the single source of truth for this project:
product goal, current stage, todo list, architecture decisions, known gotchas, and progress log.
Do not start work without reading it. Update it after completing any meaningful work.

`README.md` is the public-facing product doc — API reference, quickstart, architecture.

---

## Project context (summary — full detail in MEMORY.md)

**What we're building:** Cross-app personal memory OS.
"Your AI tools have different brains. ContextOS gives them one."

**Current stage:** M5 complete · M6 in progress (PyPI publish, `contextos start` CLI, screencast demo)

**Stack:** Python + FastAPI · Postgres + pgvector · Redis · sentence-transformers (local) or OpenAI

---

## Running the stack

```bash
# Start (note: non-default Docker socket on this machine)
DOCKER_HOST=unix:///Users/sverma/.docker/run/docker.sock docker compose up -d
curl localhost:8000/health    # verify Postgres + Redis + app ok

# Create an API key
python scripts/seed_api_key.py --app-name "test" \
  --database-url postgresql://contextos:contextos@localhost:5433/contextos

# Smoke tests
CONTEXTOS_API_KEY=sk-... pytest tests/test_smoke.py -v
```

## Local config

```
EXTRACTION_PROVIDER=mock      # no API key needed for local dev
EMBEDDING_PROVIDER=local      # sentence-transformers all-MiniLM-L6-v2, 384 dims
```

---

## gstack

```bash
git clone --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
cd ~/.claude/skills/gstack && ./setup --team
```

Use `/browse` for all web browsing. Use `/qa`, `/review`, `/ship`, `/investigate` as needed.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool.

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
