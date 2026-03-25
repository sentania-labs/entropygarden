# Generation Ship Simulator

## What This Is
A persistent multiplayer generation ship simulation. Oregon Trail meets Aurora meets RimWorld.
Players (or AI agents) manage a multi-generational starship where slow, compounding failure
and incomplete information drive emergent narrative. This is a vibecoding learning project.

## Key Design Docs
- `docs/design.md` — game loop, roles, systems, MVP scope
- `docs/context.md` — inspiration, themes, tone, design intent
- `docs/architecture.md` — technical architecture and stack decisions
- `docs/roadmap.md` — current priorities and future ideas

## Core Principles (never violate these)
1. **Drift** — systems degrade over time, partially irreversibly
2. **Incomplete information** — no role sees full truth
3. **Slow compounding failure** — no instant death spirals
4. **Negotiation > optimization** — social tension IS the gameplay
5. **Server is authoritative** — client is a view + input layer

## Architecture
- **Sim Engine**: Deterministic tick-based simulation (Python/FastAPI)
- **Game Server**: Turn/window management, action resolution, state persistence
- **Agent Service**: LLM-powered role agents (single model, multi-role prompting)
- **Client**: Web dashboard (React), role-specific views, chat/negotiation

## Time Model
- 100 game-years = 1 real year
- Sim ticks continuously on server
- Decision windows open every 6-12 hours real time
- Players set policies (persistent) and take actions (per-window)

## MVP Scope
- 3 rings, 3-5 roles (Captain, Engineer, Ecologist minimum)
- 5 resources: Food, Water, Oxygen, Power, Morale
- 3 hidden pressures: Maintenance Debt, Ecological Drift, Social Tension
- Event system with random + threshold-triggered events
- Single-player first (AI fills other roles), multiplayer second

## Roles & Information Asymmetry
Each role sees different slices of truth:
- **Captain**: summaries, risk flags, policy levers
- **Engineer**: power grid, maintenance backlog, rotation stability
- **Ecologist**: crop yield, atmosphere composition, contamination
- **Governor**: unrest levels, enforcement capacity, faction tensions
- **Ring Delegate**: local sentiment, informal economy, compliance

## Code Standards
- **Test-driven.** Write tests first, especially for sim math and state transitions.
- Keep simulation logic deterministic and testable (no LLM in the sim loop)
- LLMs NEVER write state directly — they propose, engine validates and applies
- **LLM calls are expensive.** Treat them as a scarce resource, not a default.
  Compute everything possible with deterministic code. LLM is reserved for:
  agent decisions (absent/emergent roles), narration/flavor, negotiation dialogue.
  Always ask: "can this be done without an LLM call?" If yes, do that.
- State is JSON-serializable; persist to DB (SQLite for MVP, Postgres later)
- All randomness via seeded PRNG (enables deterministic replay)
- Python: pytest, ruff, mypy strict. Frontend: vitest, eslint, TypeScript strict.
- Pre-commit hooks. CI runs lint + typecheck + tests on every commit.
- Prefer simple models tuned by playtesting over complex models tuned by math

## Project Structure
```
ark-drift/
├── CLAUDE.md
├── docs/              # design, context, architecture, decisions, roadmap
├── server/            # sim engine + game server (Python/FastAPI)
│   ├── sim/           # deterministic simulation core
│   ├── api/           # REST + WebSocket endpoints
│   ├── agents/        # LLM agent service
│   └── tests/
├── client/            # React web dashboard (TypeScript)
├── data/              # seed data, event definitions, role configs
├── docker/            # Dockerfiles per service
└── docker-compose.yml # local dev orchestration
```

## Current Phase
**Phase 0: Bootstrap** — Get sim engine ticking, basic state model, CLI output.
Next: event system, then basic web client, then first AI agent.

## When In Doubt
- Simpler is better. Tune later.
- The sim engine owns truth. LLMs interpret it.
- Every decision should have a delayed consequence.
- If it doesn't create tension between roles, it's not a feature.
