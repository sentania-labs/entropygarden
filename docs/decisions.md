# Design Decisions Log

Captured from architect interviews. These are binding decisions unless revisited.

---

## Time & Engagement Model

**Sim runs continuously.** Server ticks forward whether players are online or not.
Like an MMO server — the world doesn't pause.

**Default time scale:** 100 game-years = 1 real year.
Presets available:
- Sprint (50:1) — ~6 months for a 100-year trip
- Standard (100:1) — ~1 year
- Marathon (200:1) — ~2 years

**Decision windows:** 3-4 per real day at standard pace.
Each role has its own cadence — engineer may get maintenance checks more frequently
than captain gets strategic decisions. This naturally creates information lag between roles.

**Absent player handling (mix model):**
- Routine decisions: AI agent handles using player's policy settings
- Major decisions: go unresolved — neglect has consequences
- Crisis events: combination of AI handling + other active players can step in with limited authority

**Policy system (MVP):** Priority list — player ranks what matters most, AI interprets.
**Policy system (later):** Visual rule builder (IF oxygen < 80% THEN reduce activity).

**Design principle:** Neglect is a valid game state. An absent player's ship drifts.
Active players don't win by clicking more — they win by noticing problems earlier
and negotiating better.

---

## Game Setup & Difficulty

**Scenario configuration:** Presets with optional customization.
Presets combine destination + ship size + time scale with flavor names.

**Difficulty is shaped by two axes:**
- **Destination distance** — short trip (Proxima, 42yr) = intense survival. Long haul (TRAPPIST-1, 400yr) = political epic.
- **Ship size** — small = thin engineering margins, few roles. Large = more resources but political complexity, decentralization.

Ship size and destination don't just make it "harder" — they change what the game is *about*.

**Win/loss:** Arrive with viable population = win. Extinction/collapse = loss.
Shared outcome — all players win or lose together.

---

## Roles & Political System

**Roles are positions of power, not permanent assignments.**
The command council structure is the starting condition, not the final state.

**Captain authority:** Can unilaterally override any role's decision, but at a cost
to legitimacy and political capital. Legitimacy is effectively another resource.

**Role changes depend on context:**
- Routine transfer → Captain appoints
- Contested removal → Council mechanics
- Mutiny → Population-driven, requires influence threshold

**Removed players don't leave the game.** They become opposition figures / faction leaders.
They retain influence and can threaten strikes, organize resistance, or accumulate
enough support to force their way back into power.

**Emergent roles (VISION — not MVP):**
The formal role list at game start isn't the role list at game end.
Informal power structures emerge organically:
- A farmer who feeds ring 3 during a crisis accumulates influence
- A black market broker emerges during scarcity
- A religious/cultural leader arises over generations
- Random population members can evolve into agent-playable roles

**Architecture implication:** Roles aren't a fixed enum. The data model must support
influence tracking at the population level from day one. Who do the people in ring 3
actually listen to? That may not be whoever holds the title.

**Formal roles** = system-recognized authority, access to controls, decision windows.
**Informal roles** = no system authority, but influence over compliance, morale, factions.
The bridge between them is legitimacy/influence.

---

## Multiplayer

**Game creation:** Both private (invite code) and public lobby available.
**Player flow:** Drop in/out freely. AI backfills when a player leaves.
**AI handoff:** When AI takes a role, it gets its own personality — not a copy of the departing player.

---

## AI Agents

**Personality-driven.** Each AI has tendencies: risk-averse, ambitious, cautious, aggressive, etc.
**Feel like real crew members** with opinions, not transparent automation.
**Can participate in politics** — an AI ring delegate can resist the captain's orders
based on its personality. An AI engineer can disagree with resource allocation.
**This is what makes solo play interesting** — you're negotiating with characters, not optimizing widgets.

---

## Ship Design

**Start abstract, add physicality later if it serves gameplay.**
Rings are game zones with stats (population, resources, health, morale) — not geometric
objects with radius and RPM. If physics later adds interesting gameplay (gravity effects,
Coriolis, thrust vector tilt), it can be layered on. The data model shouldn't prevent this.

**Fixed structure, mutable state.** The ship layout is set at game creation (based on preset).
Rings cannot be added. But regions can be:
- Damaged (hull breach, contamination)
- Sealed off (quarantine, abandonment)
- Repurposed (agriculture ring becomes housing under pressure)

This creates interesting scarcity decisions without requiring a construction sim.

---

## Population Model

**Named individuals with traits (Cities: Skylines model).**
Every person on the ship has: name, age, traits, occupation, health, morale, ring assignment,
influence. But players never micromanage individuals — they manage systems and policies,
and the population responds through individual behavior aggregating into emergent outcomes.

Ring 3's unrest isn't just a number — it's 40 specific unhappy people, 12 of whom work in
life support, causing a productivity drop in that specific system. Emergent leaders arise
naturally: the individual whose traits and actions accumulate influence becomes someone.

**Performance note:** 500-2000 individuals updated per tick must be efficient. Individuals
use simple trait-driven behavior rules, not LLMs. The LLM layer interprets what the
population is doing — it doesn't drive each person.

---

## Tech Stack

**Python + React.** Decided, not up for debate.
- Server: Python 3.11+, FastAPI, Pydantic for state models
- Client: React, TypeScript
- DB: SQLite for MVP, Postgres for multiplayer/production
- LLM: Ollama (local) with API fallback
- Containers: Docker Compose

**First playable target:** Sim engine with visual state output.
Sim engine first (prove the math), but surface state visually early — not a full UI,
but enough to see what's happening (could be a simple web view of JSON state, charts
of resource trends, or a minimal dashboard).

---

## Engineering & Infrastructure

**Test-driven development.** Non-negotiable. Tests come first, especially for:
- Sim engine math (resource consumption, drift accumulation, ecological balance)
- State transitions (tick produces expected output from known input)
- Event triggers (thresholds fire correctly)
- Action resolution (authority, compliance, conflict)
- Policy execution (standing orders produce expected actions)

**CI pipeline:** Linting + type checking + tests run on every commit.
- Python: pytest, ruff (linting), mypy (type checking)
- Frontend: vitest, eslint, TypeScript strict mode
- Pre-commit hooks to catch issues locally

**Containerized services.** Everything runs in containers from the start.
- `sim-engine` — deterministic simulation + game server (FastAPI)
- `agent-service` — LLM agent layer (can point at local Ollama or remote API)
- `client` — React web app (static build served by nginx or similar)
- `db` — PostgreSQL (SQLite for local dev is fine)
- Docker Compose for local dev, portable to any host

**Persistence & state recovery.** The sim runs continuously — server crashes are inevitable.
- Checkpoint state at regular intervals (every N ticks)
- On restart, resume from last checkpoint + replay any queued actions
- Checkpoints also enable: game history review, branching ("what if"), debugging

**Audit log.** Every tick, decision, AI action, and event logged immutably.
- Serves debugging (what happened at tick 4,217?)
- Serves narrative (LLM summarizes log into ship's journal / news feed)
- Serves accountability (who made that call?)
- Append-only — never mutated

**Deterministic replay.** Same initial seed + same action log = same game state.
- Enables: testing, debugging, spectating, "what if" branching
- Requires: sim engine has zero randomness except from a seeded PRNG
- Requires: LLMs never write state directly — they propose, engine validates and applies

**The LLM boundary (critical architectural constraint):**
- LLMs NEVER write to game state directly
- LLMs propose actions, generate narration, interpret state
- The sim engine validates and applies everything
- This keeps the game reproducible, testable, and cheat-resistant

**Multiplayer fairness.**
- Actions are capped per decision window, not per hour
- A player who logs in once per window has the same mechanical ceiling as someone refreshing constantly
- Advantage comes from better timing and better negotiation, not more clicks

**Frequent check-ins reward awareness, not power.**
Being present more often gets you:
- More time with the news feed / ship's journal (catch small signals before they become crises)
- More time to read role-specific status reports and spot trends
- More opportunities to message other players/agents and build relationships
- Earlier awareness of brewing problems — a head start, not exclusive access

Being present more often does NOT get you:
- More actions per window (still capped)
- Better raw information (same reports, same data)
- Cheaper overrides (still costs the same political capital)

**Communication as a game system.**
Messaging between roles is not instant-reliable infrastructure — it's a social layer
with friction. Players and AI agents alike have communication behavior:
- Response time (some agents are prompt, some aren't)
- Response quality (shallow vs. thoughtful, buried bad news vs. leading with problems)
- Selectivity (responds fast to technical questions, ghosts political ones)
- Agenda (only reaches out when they want something)

This means the player who checks in often has more *conversations*, not more *commands*.
The always-on advantage is relational, not mechanical.

---

## Open Questions (to resolve before or during build)

- [ ] Exact decision window cadence per role at each time preset
- [ ] How AI delegation quality degrades (or doesn't) compared to active play
- [ ] Crisis interrupt notification mechanism (push? email? in-app only?)
- [ ] How generational handoff works (knowledge transfer/loss, new leaders)
- [ ] Influence/legitimacy tracking model
- [ ] How emergent roles get recognized by the system
- [ ] What "opposition figure" can actually *do* mechanically
- [ ] Checkpoint frequency and max replay window
- [ ] Seeded PRNG strategy (one global seed? per-ring? per-system?)
- [ ] Container orchestration for production (Compose? K8s? keep it simple?)
- [ ] How the ship's journal / narrative layer consumes the audit log
- [ ] Mobile client strategy (responsive web? PWA? native later?)
