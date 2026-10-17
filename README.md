# Fire Simulator

[![CI](https://github.com/jaiswaladitneu/FireSimulator/actions/workflows/ci.yml/badge.svg)](https://github.com/jaiswaladitneu/FireSimulator/actions/workflows/ci.yml)

The fire-modeling component of the **Fireforce6** wildfire-response system. It
models the fire itself on a grid of cells, advances it in discrete ticks based on
fuel, slope, moisture and wind, broadcasts what happens onto a shared NATS
message bus, and reacts to suppression actions sent by other components.

> CSYE 7230 · Project Part B — Team A (Aditi Jaiswal, Mohammad Adnaan Mansuri)

## Architecture at a glance

- **Engine (`engine/`)** — the simulation core: `Grid`/`Cell` (NumPy arrays),
  a `SpreadModel` **Strategy** (`PhysicsSpreadModel`), a procedural
  `MapGenerator`, and `SimulationEngine` (seeded RNG, fixed-step tick loop,
  play/pause/step/reset, suppression).
- **Messaging (`messaging/`)** — a `MessageBus` **port** (Adapter) with an
  in-memory bus and versioned event topics (publish/subscribe).
- **Persistence (`persistence/`)** — **Repository** interfaces + in-memory
  implementations and a `Snapshot` (**Memento**) for save / replay / resync.
- **API (`api/`)** — a FastAPI app exposing scenario CRUD and playback control.
- **Frontend (`frontend/`)** — React + Babylon.js control panel and 3D view
  (planned; see the Part B report mock-ups).

See the Part B report for the full UML, architecture and design write-up.

## Run the tests

```bash
pip install -r requirements.txt
pip install pytest httpx ruff
ruff check .
pytest -q
```

## Run the API locally

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload
# interactive docs at http://127.0.0.1:8000/docs
```

Example:

```bash
curl -X POST localhost:8000/scenarios -H "content-type: application/json" \
  -d '{"name":"Ridgeline Burn","width":60,"height":60,"seed":4821,"wind_speed":18,"ignition_points":[{"x":30,"y":30}]}'
curl -X POST localhost:8000/simulation/play
curl localhost:8000/simulation/state
```

## Run the whole stack (API + NATS + PostgreSQL + Redis)

```bash
docker compose -f infra/docker-compose.yml up
```

## Repository layout

```
engine/        simulation core + map generation      (E1, E4)
messaging/     message bus port, events, publisher   (E3)
persistence/   repositories + snapshot model         (E6)
api/           FastAPI scenario + playback API        (E2)
frontend/      React + Babylon.js UI (planned)        (E5)
infra/         docker-compose for the local stack     (E7)
tests/         pytest suite                           (E7)
```

## Process

This repo follows a Scrum workflow: epics and stories as issues, sprints as
milestones, a GitHub Project board, and peer-reviewed pull requests on
`issue-<number>` branches linked to their issues.
