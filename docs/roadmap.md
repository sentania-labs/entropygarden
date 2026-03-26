# Roadmap — Entropy Garden

## What's complete

### Phase 0 — Sim Engine
- Deterministic tick engine (1 tick = 1 game-day)
- 3 rings, 1000 people, named individuals with traits
- 5 resources: Food, Water, Oxygen, Power, Morale
- 3 hidden pressures: Maintenance Debt, Ecological Drift, Social Tension
- Seeded PRNG for reproducible replay
- 12 starter events (threshold + random) in `data/events.yaml`
- CLI runner

### Phase 1 — API + Agent Service
- FastAPI REST + WebSocket API
- Role-filtered state views (Engineer, Captain)
- LLM agent service — multi-provider (openrouter, openai, anthropic, local/ollama)
- Role-specific system prompts, personality-driven decisions
- Agent decisions persisted to SQLite

### Phase 2 — Decision Windows
- Open/close lifecycle: windows open every N ticks, close when next window fires
- Conflict resolution by role hierarchy (captain overrides engineer, etc.)
- Policy system: standing orders per role, fallback for absent players
- REST endpoints: `/games/{id}/window/current|history|action|policy/{role}`
- 200 tests passing

---

## What's next

### Phase 3 — Playable Loop (immediate priority)

The goal: a human can sit down, open a browser, pick a role, watch the sim run, respond to events, and see consequences.

- [ ] **Client wired end-to-end** — connect React components to live WebSocket state; role selector gates what you see
- [ ] **Event response UI** — when an event fires with choices, present them; submit the player's response
- [ ] **Action UI** — forms for the 5 action types, queued for the next decision window
- [ ] **History endpoint consumed** — sparklines for resource trends using `GET /history`
- [ ] **Role views for Ecologist/Governor/Ring Delegate** — currently only Engineer and Captain views exist
- [ ] **`GET /games/{id}/history`** already exists in the API; client hook `useHistory` needs wiring

### Phase 4 — Multiplayer Foundation

- [ ] Game lobby: create public/private games, invite codes
- [ ] Drop-in/drop-out: player claims a role, AI releases it; player leaves, AI takes over
- [ ] Role change mechanics: Captain appoints, contested removal via council, mutiny path
- [ ] Removed players become opposition figures (retain influence, can threaten/organize)

### Phase 5 — Narrative Layer

- [ ] Ship's journal: LLM summarizes audit log into readable narrative each decision window
- [ ] News feed: role-specific "what's happening on the ship" updates
- [ ] Audit log: append-only record of every tick/decision/event (feeds journal + debugging)
- [ ] Communication system: player-to-agent messaging with friction (response time, agenda)

### Phase 6 — Political Systems

- [ ] Legitimacy/influence as a tracked resource (data model scaffolded, mechanics not tuned)
- [ ] Captain override at political cost
- [ ] Faction emergence from population influence accumulation
- [ ] Emergent role recognition: informal power structures that the system acknowledges

### Phase 7 — Admin Interface

An operator-facing dashboard separate from the player UI. Requires an auth layer first.

**Auth layer (prerequisite):**
- [ ] User accounts and sessions (currently no auth at all)
- [ ] Role-based access: player vs. admin vs. superadmin
- [ ] Session tokens / JWT — FastAPI dependency injection guards routes
- [ ] Admin routes under `/admin/` blocked at nginx unless authenticated

**Game management:**
- [ ] List all active and stale games with age, player count, tick rate
- [ ] Pause / resume / delete individual games
- [ ] Configurable stale-game TTL — auto-expire games with no activity for N days
- [ ] Game state inspector — browse rings, pressures, event log for any game
- [ ] Note: `GameStore` already tracks multiple games in memory; the API surface is mostly there

**Log viewer:**
- [ ] Tail and search the audit log (every tick, event, and decision — not yet implemented)
- [ ] Filter by game, role, tick range
- [ ] Agent decision history (already in `agent_decisions` SQLite table)

**SSL certificate management:**
- [ ] Upload cert.pem + key.pem via admin UI (writes to ssl_data volume, triggers proxy reload)
- [ ] Display cert expiry and CN
- [ ] Let's Encrypt integration: certbot sidecar container handles ACME challenge and renewal
  - Requires port 80 to be publicly reachable (HTTP challenge) or DNS API access (DNS challenge)
  - Certbot writes to the ssl_data volume; proxy reloads on cert renewal

**Infrastructure:**
- [ ] Metrics endpoint (`/metrics`, Prometheus-compatible) — tick rate, active games, population counts
- [ ] Health check endpoint (`/health`) — already implied by FastAPI but not explicit
- [ ] Structured logging (JSON) so log aggregators (Loki, CloudWatch) can parse fields

---

## Infrastructure roadmap

### Pre-k8s: Service separation (required before horizontal scaling)

The current architecture runs the sim tick loop inside the FastAPI process. This must change before multiple server instances are viable.

- [ ] **Extract sim engine to its own container** — tick loop moves to `sim-engine` service; writes state to Postgres; API becomes stateless
- [ ] **Migrate SQLite → PostgreSQL** — swap store backend; keep SQLite for local dev
- [ ] **Add Redis pub/sub for WebSocket fan-out** — multiple API pods can broadcast ticks to all clients
- [ ] **Production Dockerfile** — no `--reload`, no source mounts, node_modules baked in for client

### k8s deployment

- [ ] Helm chart or kustomize manifests
- [ ] `sim-engine`: StatefulSet, 1 replica (serial by design — scales vertically)
- [ ] `server` (API): Deployment, N replicas (stateless once on Postgres + Redis)
- [ ] `client`: Deployment, N replicas (pure static)
- [ ] PVCs for Postgres and Redis; managed services preferred for production
- [ ] Ingress with path routing (`/api`, `/ws`, `/`)
- [ ] k8s Secrets for LLM API keys; ConfigMaps for non-secret env vars

See `docs/architecture.md` for the full migration design.

---

## Open design questions

These are unresolved decisions that will affect implementation:

- Exact decision window cadence per role at each time preset (currently uniform)
- How AI delegation quality degrades when policy compliance decays
- Crisis interrupt notification (push notification? email? in-app only?)
- Generational handoff: knowledge transfer/loss when a character ages out
- Checkpoint frequency and max replay window
- What an opposition figure can actually *do* mechanically
- Mobile client strategy (responsive web first, PWA later, native never)
- Ship's journal consumption model — pull (player reads when they want) or push (broadcast at window close)
