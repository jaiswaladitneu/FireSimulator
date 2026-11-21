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
- **City layer (`engine/city_gen.py`, `city.py`, `population.py`, `response.py`)** —
  a seeded procedural town (homes, schools, hospital, shops, parks, roads, fuel
  stations, battery storage, fire station) in forested hills; an
  `UrbanSpreadModel` **Strategy** with wind-blown ember spotting; a people model
  (who is where by time of day, evacuation, people who need rescue, estimated
  casualties); life-safety priority scoring; and fire crews. It attaches to the
  engine as a tick **Observer**, so wildland scenarios are unchanged.
- **API (`api/`)** — a FastAPI app exposing scenario CRUD, playback control, the
  city map, crew dispatch and the incident history.
- **Frontend (`frontend/`)** — React + TypeScript + Three.js incident command
  center (live 3-D town, lives-at-risk HUD, priority queue, crews, incident log)
  and an admin dashboard with the history of past incidents.

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

## Run the command center (API + UI)

```bash
# terminal 1 — API on port 8000
pip install -r requirements.txt
uvicorn api.main:app --reload

# terminal 2 — UI on port 5173 (calls the API through the /api dev proxy)
cd frontend
npm install
npm run dev
# open http://127.0.0.1:5173
```

In the UI: **Incident setup → Generate town**, then **Start fire**. Lives at risk
are on top; the right column ranks what to protect first (lives, then fuel and
battery hazards) and dispatches crews; zoom in to see people counts on every
house, school and road. Finished incidents are recorded in `data/incidents.json`
(override with `FIRESIM_INCIDENTS_FILE`) and appear in the **Admin Dashboard**,
which can also run a batch of simulated incidents.

City scenario example:

```bash
curl -X POST localhost:8000/scenarios -H "content-type: application/json" \
  -d '{"name":"Ridgeview","map_type":"city","width":96,"height":96,"seed":4,"wind_direction":90,"wind_speed":25,"hour":14,"crews":4}'
curl localhost:8000/simulation/map      # town layout, buildings, people capacity
curl -X POST localhost:8000/simulation/play
curl -X POST localhost:8000/simulation/tick
```

| Endpoint | Purpose |
|---|---|
| `GET /simulation/map` | Static town map (land use, fuel, elevation, assets) |
| `POST /simulation/ignite` | Start a fire at a cell |
| `POST /simulation/suppress` | Queue suppression on cells |
| `POST /simulation/dispatch` | Send the nearest free crew to an asset |
| `POST /simulation/auto-dispatch` | Turn automatic dispatch on/off |
| `POST /simulation/end` | Close the incident and record it |
| `GET /incidents`, `GET /incidents/{id}` | Incident history / one incident with timeline |
| `DELETE /incidents/{id}`, `DELETE /incidents` | Delete one / clear history |
| `POST /incidents/simulate` | Run and record a batch of simulated incidents |

## Run the whole stack (API + NATS + PostgreSQL + Redis)

```bash
docker compose -f infra/docker-compose.yml up
```

## Repository layout

```
engine/        simulation core, map + town generation, city layer  (E1, E4)
messaging/     message bus port, events, publisher                 (E3)
persistence/   repositories, snapshot + incident models            (E6)
api/           FastAPI scenario, playback, dispatch, incidents      (E2)
frontend/      React + Three.js command center and admin dashboard  (E5)
infra/         docker-compose for the local stack     (E7)
tests/         pytest suite                           (E7)
```

## Process

This repo follows a Scrum workflow: epics and stories as issues, sprints as
milestones, a GitHub Project board, and peer-reviewed pull requests on
`issue-<number>` branches linked to their issues.
