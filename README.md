# Entropy Garden

A persistent multiplayer generation ship simulation. Oregon Trail meets Aurora meets RimWorld.
Players (or AI agents) manage a multi-generational starship where slow, compounding failure
and incomplete information drive emergent narrative.

- **Phases 0–2 complete**: sim engine, event system, REST/WebSocket API, LLM agent service, decision window system
- **Stack**: Python 3.12 / FastAPI / React 18 / Vite / Tailwind / nginx / Docker
- **200+ tests passing**

---

## Prerequisites

- Docker + Docker Compose v2 (`docker compose` not `docker-compose`)
- `jq` — for pretty-printing curl responses in the smoke test below
- Optional: Python 3.12+ if you want to run tests/lint outside Docker

---

## Quick Start

### Server only (fastest path — API + Swagger, no client)

```bash
cp .env.example .env
docker compose up --build
```

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- Server reloads automatically on code changes (bind mount)

### Full stack (server + React client + HTTPS proxy)

```bash
docker compose --profile client up --build
```

- App: `https://localhost:8443` — accept the self-signed cert warning
- HTTP `http://localhost:8080` redirects to HTTPS
- Override ports in `.env`: `HTTP_PORT=8080`, `HTTPS_PORT=8443`, `SSL_CN=localhost`

### Stop / clean up

```bash
docker compose down              # stop, keep data in ./local/
docker compose --profile client down

docker compose down -v           # stop + wipe volumes (db + certs reset)
```

---

## Running Tests (outside Docker)

```bash
cd server
pip install -e ".[dev]"          # first time only

python -m pytest tests/ -v       # full suite (~200 tests)
python -m pytest tests/ -q       # quiet pass/fail summary
python -m pytest tests/test_windows.py -v   # decision window tests only
python -m pytest tests/test_api.py -v       # API integration tests only
```

---

## Lint + Typecheck

```bash
cd server
ruff check .
mypy .
```

Both must pass clean before committing. Pre-commit hooks enforce this.

---

## Smoke Test — Manual Validation Walkthrough

Replace `GAME` with the `game_id` returned in step 1.

### 1. Create a game

```bash
curl -s -X POST http://localhost:8000/games \
  -H "Content-Type: application/json" \
  -d '{"seed": 42, "paused": true, "decision_window_interval": 10}' | jq .
```

Expected: `201` with `game_id`, `tick: 0`, `status: "paused"`.
Save the `game_id`: `GAME=<value>`

### 2. Check initial state (captain view)

```bash
curl -s "http://localhost:8000/games/$GAME/state?role=captain" | jq '{tick, ring_count: (.rings | length)}'
```

Expected: `tick: 0`, `ring_count: 3`.

### 3. Advance 10 ticks manually

```bash
curl -s -X POST "http://localhost:8000/games/$GAME/advance" \
  -H "Content-Type: application/json" \
  -d '{"ticks": 10}' | jq .tick
```

Expected: `10`.

### 4. Decision window should now be open

```bash
curl -s "http://localhost:8000/games/$GAME/window/current" | jq '{status, opened_tick, closes_tick}'
```

Expected: `status: "open"`, `opened_tick: 10`, `closes_tick: 20`.

### 5. Submit an action inside the window

```bash
curl -s -X POST "http://localhost:8000/games/$GAME/window/action" \
  -H "Content-Type: application/json" \
  -d '{"role": "engineer", "action_type": "emergency_repair", "ring_id": "ring_1", "parameters": {}}' | jq .
```

Expected: `status: "accepted"`, HTTP 200.

Action types: `emergency_repair`, `prioritize_maintenance`, `divert_power`, `ration_resource`, `boost_production`
Ring IDs: `ring_1`, `ring_2`, `ring_3`

### 6. Advance another 10 ticks to close the window

```bash
curl -s -X POST "http://localhost:8000/games/$GAME/advance" \
  -H "Content-Type: application/json" \
  -d '{"ticks": 10}' | jq .tick
```

Expected: `20`.

### 7. Confirm window closed and new one opened

```bash
# Previous window should be in history
curl -s "http://localhost:8000/games/$GAME/window/history" | jq '.[0].status'
# → "closed"

# A new window should be open
curl -s "http://localhost:8000/games/$GAME/window/current" | jq .status
# → "open"
```

### 8. Try submitting after window closes (should reject)

```bash
# Advance past the close tick
curl -s -X POST "http://localhost:8000/games/$GAME/advance" \
  -H "Content-Type: application/json" \
  -d '{"ticks": 10}' | jq .tick   # → 30

# Now no window is open — action should 409
curl -s -o /dev/null -w "%{http_code}" -X POST "http://localhost:8000/games/$GAME/window/action" \
  -H "Content-Type: application/json" \
  -d '{"role": "engineer", "action_type": "emergency_repair", "ring_id": "ring_1", "parameters": {}}'
# → 409
```

### 9. Set a standing policy for a role

```bash
curl -s -X PUT "http://localhost:8000/games/$GAME/window/policy/engineer" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "engineer",
    "priorities": [
      {"action_type": "emergency_repair", "ring_id": "ring_1", "parameters": {}, "note": "keep ring 1 maintained"}
    ],
    "compliance": 1.0
  }' | jq .

curl -s "http://localhost:8000/games/$GAME/window/policy/engineer" | jq .
```

### 10. WebSocket live tick stream

```bash
# Install wscat once: npm install -g wscat
wscat -c "ws://localhost:8000/games/$GAME/ws"
```

Then in another terminal, resume the game and advance ticks — you should see JSON tick broadcast messages arriving on the WebSocket.

```bash
curl -s -X POST "http://localhost:8000/games/$GAME/resume" | jq .status
```

---

## LLM Agent (Optional)

The agent runner starts automatically when `AGENT_GAME_ID` is set in `.env`.

```bash
# 1. Create a game, copy its game_id
# 2. Edit .env:
AGENT_GAME_ID=<game_id>
AGENT_ROLE=engineer
LLM_PROVIDER=openrouter          # openrouter | openai | anthropic | ollama
OPENROUTER_API_KEY=sk-or-...

# 3. Restart the server
docker compose up --build
```

The agent subscribes to decision window events and submits actions for its role. Agent decisions are stored in the SQLite `agent_decisions` table.

---

## Project Layout

```
server/
  sim/           deterministic tick engine (state, tick, events, windows, policy)
  api/           FastAPI REST + WebSocket (routes: games, windows, ws)
  agents/        LLM agent service (agent, llm, runner, prompts)
  tests/         200+ tests
client/
  src/
    components/  Dashboard, GameLobby, RingView, EventFeed, SignalPanel, ...
    hooks/       useGameSocket, useEvents, useHistory
    api.ts       HTTP client + WebSocket
data/
  events.yaml    event definitions (random + threshold-triggered)
docker/
  server/        Python Dockerfile
  client/        Node/Vite Dockerfile
  nginx/         Dockerfile, entrypoint.sh, dev/prod nginx config templates
docs/
  roadmap.md     what's done and what's next
  architecture.md  service layout and k8s migration path
  design.md      game loop, roles, systems
  decisions.md   design decision log
local/           gitignored runtime data (db, ssl certs, node_modules)
CLAUDE.md        core design principles — do not violate
BOOTSTRAP.md     deep implementation guide for each phase
```

---

## Key API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/games` | Create a game |
| `GET` | `/games/{id}/state?role=captain` | Role-filtered state view |
| `POST` | `/games/{id}/advance` | Advance N ticks (paused games) |
| `POST` | `/games/{id}/pause` | Pause the tick loop |
| `POST` | `/games/{id}/resume` | Resume the tick loop |
| `GET` | `/games/{id}/events` | Recent event log |
| `GET` | `/games/{id}/history` | Resource history (sparkline data) |
| `GET` | `/games/{id}/window/current` | Current decision window |
| `POST` | `/games/{id}/window/action` | Submit action (409 if no open window) |
| `GET` | `/games/{id}/window/history` | Closed window history |
| `GET/PUT` | `/games/{id}/window/policy/{role}` | Get or set standing policy |
| `WS` | `/games/{id}/ws` | Live tick + event stream |

Full interactive docs at `http://localhost:8000/docs`.
