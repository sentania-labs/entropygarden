# Bootstrapping Guide — Generation Ship Simulator

## Prerequisites
- Python 3.11+ and `uv` (or pip/venv)
- Node.js 20+ and npm/pnpm
- Claude Code CLI installed and configured
- Git repo initialized

## Step 0: Scaffold the Project

```bash
mkdir entropygarden && cd entropygarden
git init

# Create directory structure
mkdir -p docs server/{sim,api,agents,tests} client data

# Copy in your design docs
cp generation_ship_design.md docs/design.md
cp generation_ship_context.md docs/context.md
cp CLAUDE.md .
```

Create `docs/architecture.md` and `docs/roadmap.md` as empty stubs — Claude Code
will help flesh these out as decisions are made.

## Step 1: Sim Engine Core (Start Here)

This is the heart of everything. Get this right first, no UI needed.

**Ask Claude Code:**
> Read CLAUDE.md and docs/. Build the core simulation state model and tick engine.
> Start with: 3 rings, 5 resources (Food, Water, Oxygen, Power, Morale),
> 3 hidden pressures (Maintenance Debt, Ecological Drift, Social Tension).
> Make it deterministic and testable. Output state as JSON after each tick.
> Include a simple CLI runner that advances N ticks and prints state.
```
Read CLAUDE.md and all files in docs/. These contain binding design decisions — don't re-litigate them.

Goal: Build the core simulation state model and tick engine.
- 3 rings, 5 resources (Food, Water, Oxygen, Power, Morale)
- 3 hidden pressures (Maintenance Debt, Ecological Drift, Social Tension)
- Named individuals with traits (Cities: Skylines model, not micromanaged)
- Deterministic, testable, seeded PRNG
- CLI runner that advances N ticks and prints JSON state

Before writing any code, interview me on implementation details the docs don't cover — things like: initial population size, trait lists, resource consumption rates, tick granularity, drift curves. Don't ask about decisions already made in the docs.
```

**What you should get:**
- `server/sim/state.py` — data models (dataclasses or Pydantic)
- `server/sim/engine.py` — tick function: state_in → state_out
- `server/sim/resources.py` — resource consumption/production math
- `server/sim/drift.py` — drift/degradation logic
- `server/sim/cli.py` — run and print
- `server/tests/test_engine.py` — basic tick tests

**Validate:** Run `python -m server.sim.cli --ticks 100` and confirm resources
change, drift accumulates, nothing crashes.

## Step 2: Event System

**Ask Claude Code:**
> Add an event system to the sim engine. Events are defined in JSON/YAML in data/.
> Two types: random (probability per tick) and threshold (trigger when hidden
> pressure exceeds value). Each event modifies state and presents choices.
> For now, choices are auto-resolved (no player input yet).

**What you should get:**
- `data/events.yaml` — 10-15 starter events
- `server/sim/events.py` — event evaluation and resolution
- Events visible in CLI output

## Step 3: API Layer

**Ask Claude Code:**
> Wrap the sim engine in a FastAPI server. Endpoints needed:
> GET /state — current game state (filtered by role)
> POST /action — submit a player action
> GET /events — recent events and pending decisions
> WebSocket /ws — live state updates
> The server should tick on a timer (configurable speed for dev).

**Validate:** Hit endpoints with curl/httpie, confirm state advances over time.

## Step 4: Basic Web Client

**Ask Claude Code:**
> Build a minimal React client that connects to the game server.
> Show: resource bars, event feed, ring status diagram, action buttons.
> Role selector (Captain/Engineer/Ecologist) that filters what you see.
> No polish needed — functional dashboard only.

**Validate:** Open browser, see state updating, submit an action, see effect.

## Step 5: First AI Agent

**Ask Claude Code:**
> Add an AI agent service that can play a role. Use a single LLM with
> role-specific system prompts. The agent receives the role's state view,
> recent events, and available actions. It returns a decision with reasoning.
> Start with one agent playing Engineer. Use Ollama or API fallback.

**Validate:** Run a game where you play Captain, AI plays Engineer. Confirm
the AI makes contextual decisions based on state.

## Step 6: Decision Windows

**Ask Claude Code:**
> Implement the decision window system. The sim runs continuously.
> Every N ticks (configurable), a decision window opens. Players/agents
> are notified, given a time limit to submit actions, then actions resolve.
> Add a policy system so players can set standing orders that execute
> automatically when they're not actively playing.

## Tips for Working with Claude Code

1. **Point it at CLAUDE.md first** — always start sessions with "read CLAUDE.md"
2. **One step at a time** — don't ask for the whole game at once
3. **Ask it to interview you** — "what questions do you have before building X?"
4. **Review before accepting** — especially sim math and state transitions
5. **Keep docs updated** — after each milestone, ask Claude Code to update
   architecture.md and roadmap.md with what was actually built
6. **Test the sim math** — this is where subtle bugs create nonsensical gameplay

## What Good Looks Like After Bootstrap

- Sim engine ticks deterministically with tests passing
- Events fire and modify state
- API serves role-filtered state
- Basic web UI shows the game
- One AI agent plays a role competently
- You can play Captain while AI plays Engineer and things happen

That's your MVP. Everything after is iteration: more events, more roles,
multiplayer networking, better UI, tuning the feel.
