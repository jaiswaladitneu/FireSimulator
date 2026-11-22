# Fire Simulator

[![CI](https://github.com/jaiswaladitneu/FireSimulator/actions/workflows/ci.yml/badge.svg)](https://github.com/jaiswaladitneu/FireSimulator/actions/workflows/ci.yml)

The fire-modeling component of the **Fireforce6** wildfire-response system. It models the fire on
a grid of cells and advances it in discrete ticks from fuel, slope, moisture and wind. City
scenarios add an incident command center: a procedural town with people, life-safety priorities,
fire crews and an incident history. Fire events go out, and suppression commands come in, through
a message-bus port (an in-memory bus today; the NATS adapter is planned).

> CSYE 7230 · Team A (Aditi Jaiswal, Mohammad Adnaan Mansuri)

## Architecture at a glance

- **Engine (`engine/`)** — the simulation core: `Grid`/`Cell` (NumPy arrays), a `SpreadModel`
  **Strategy** (`PhysicsSpreadModel`), a procedural `MapGenerator`, and `SimulationEngine` (seeded
  RNG, fixed-step tick loop, play/pause/step/reset, suppression).
- **City layer (`engine/city_gen.py`, `city.py`, `population.py`, `response.py`)** — a seeded
  procedural town (homes, schools, hospital, shops, parks, roads, fuel stations, battery storage,
  fire station) in forested hills; an `UrbanSpreadModel` **Strategy** with wind-blown ember
  spotting; a people model (who is where by time of day, evacuation, people who need rescue,
  estimated casualties); life-safety priority scoring; and fire crews. It attaches to the engine as
  a tick **Observer**, so wildland scenarios are unchanged.
- **Messaging (`messaging/`)** — a `MessageBus` **port** with an in-memory adapter, versioned event
  topics, an event publisher and a suppression-command listener.
- **Persistence (`persistence/`)** — **Repository** interfaces with in-memory and JSON-file
  implementations, and a `Snapshot` record of the engine state.
- **API (`api/`)** — a FastAPI app exposing scenario CRUD, playback control, the city map, crew
  dispatch and the incident history. It also serves the built UI in the Docker image.
- **Frontend (`frontend/`)** — React + TypeScript + Three.js incident command center (live 3-D
  town, lives-at-risk HUD, priority queue, crews, incident log) and an admin dashboard with the
  history of past incidents.

Class diagrams with the design patterns, the deployed architecture and the CI pipeline are in
[`docs/design/`](docs/design/); the generated API reference is in [`docs/api/`](docs/api/)
(see [`docs/README.md`](docs/README.md)).

## Quick start

**With Docker** (one container serves the UI and the API):

```bash
python build.py deploy        # builds the image and starts it with docker compose
# UI: http://localhost:8000      Swagger: http://localhost:8000/docs
python build.py stop          # stops it; the incident history volume is kept
```

**From source** (two terminals; Python 3.11+ and Node 22):

```bash
# terminal 1 - API on port 8000
pip install -r requirements.txt
uvicorn api.main:app --reload

# terminal 2 - UI on port 5173 (calls the API through the /api dev proxy)
cd frontend
npm install
npm run dev                   # open http://127.0.0.1:5173
```

In the UI: **Incident setup → Generate town**, then **Start fire**. Lives at risk are on top; the
right column ranks what to protect first (lives, then fuel and battery hazards) and dispatches
crews; zoom in to see people counts on every house, school and road. Finished incidents are
recorded in `data/incidents.json` (override with `FIRESIM_INCIDENTS_FILE`) and appear in the
**Admin Dashboard**, which can also run a batch of simulated incidents.

## Build, test and deploy

One cross-platform build script, [`build.py`](build.py), compiles, tests, documents, packages and
deploys the project. The CI pipeline runs the same commands. Run it from the repository root:

```bash
python build.py <command> [<command> ...] [--scope all|backend|frontend]
```

| Command | What it does |
|---|---|
| `setup` | Installs the Python dev tools (`requirements-dev.txt`) and the UI packages (`npm ci`) |
| `lint` | `ruff check .` on the backend, `oxlint` on the UI |
| `compile` | Byte-compiles every backend module; type-checks (`tsc`) and bundles (Vite) the UI into `frontend/dist` |
| `test` | `pytest` with branch coverage; fails if coverage drops below `fail_under` (90 %) in `pyproject.toml`. Reports: terminal, `htmlcov/index.html`, `coverage.xml` |
| `docs` | Regenerates the API reference into `docs/api` with pdoc |
| `package` | Builds the Docker image `firesim:local` (multi-stage: Node builds the UI, Python serves API + UI) |
| `smoke` | Starts the image and checks the UI, `/api/health`, scenario creation and one simulation step |
| `deploy` / `stop` | Starts / stops the app with docker compose on http://localhost:8000 |
| `clean` | Deletes build outputs and caches |
| `ci` | `lint compile test docs` — what CI runs before packaging |
| `all` | `ci` plus `package` and `smoke` |

Typical use:

```bash
python build.py setup                 # once
python build.py ci                    # before pushing
python build.py test --scope backend  # just the Python tests with coverage
python build.py all                   # everything, including the Docker image (Docker required)
```

Requirements: Python 3.11+ (CI and the image use 3.12), Node 22 (Vite 8 needs 20.19+ or 22.12+),
and Docker for `package`, `smoke` and `deploy`. Coverage is opt-in, so a single test file can still
be run on its own: `pytest tests/test_grid.py`.

## Continuous integration and delivery

The pipeline is [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
(diagram: [`docs/design/ci-pipeline.png`](docs/design/ci-pipeline.png)).

- **Triggers:** every push to any branch, every pull request to `main`, and manual runs. A newer
  push to the same branch cancels the run still in progress.
- **Jobs** (each calls `build.py`):

  | Job | Runs on | Steps | Outputs |
  |---|---|---|---|
  | `backend` | ubuntu-latest, Python 3.12 | setup → lint → compile → test (coverage ≥ 90 %) → docs | artifacts `coverage-report`, `api-docs`; coverage table in the run summary |
  | `frontend` | ubuntu-latest, Node 22 | setup (`npm ci`) → lint → compile (type-check + bundle) → test | artifact `ui-dist` |
  | `package` | ubuntu-latest, after both jobs pass | build the Docker image → smoke-test the container → on `main` only: push to GitHub Container Registry | image `ghcr.io/jaiswaladitneu/firesimulator:latest` and `:<short sha>` |

- **How to trigger a build:** push a commit to any branch, or open a pull request to `main`. To run
  it by hand: GitHub → **Actions** → **CI** → **Run workflow**, or with the GitHub CLI:

  ```bash
  gh workflow run CI --ref <branch>
  gh run watch                         # follow the run
  ```

- **Run the published image** (after a push to `main`):
  `docker run -p 8000:8000 ghcr.io/jaiswaladitneu/firesimulator:latest`

## Documentation

- **API reference:** [`docs/api/index.html`](docs/api/index.html), generated from the docstrings
  with `python build.py docs` — every public class, its attributes, and every method's arguments,
  return value and raised exceptions. How to view it: [`docs/README.md`](docs/README.md).
- **Design:** architecture, class diagrams (with the design patterns) and the CI pipeline in
  [`docs/design/`](docs/design/).
- **REST endpoints:** interactive Swagger UI at `/docs` on a running server.

## Use the API directly

```bash
curl -X POST localhost:8000/scenarios -H "content-type: application/json" \
  -d '{"name":"Ridgeline Burn","width":60,"height":60,"seed":4821,"wind_speed":18,"ignition_points":[{"x":30,"y":30}]}'
curl -X POST localhost:8000/simulation/play
curl localhost:8000/simulation/state
```

City scenario:

```bash
curl -X POST localhost:8000/scenarios -H "content-type: application/json" \
  -d '{"name":"Ridgeview","map_type":"city","width":96,"height":96,"seed":4,"wind_direction":90,"wind_speed":25,"hour":14,"crews":4}'
curl localhost:8000/simulation/map      # town layout, buildings, people capacity
curl -X POST localhost:8000/simulation/play
curl -X POST localhost:8000/simulation/tick
```

Every route is also served under `/api` (for example `/api/simulation/state`), which is how the UI
calls it.

| Endpoint | Purpose |
|---|---|
| `POST /scenarios`, `GET /scenarios`, `GET`/`DELETE /scenarios/{id}` | Scenario CRUD |
| `GET /scenarios/{id}/replay` | Deterministic replay of a saved scenario |
| `POST /simulation/play`, `pause`, `step`, `tick`, `reset`, `speed` | Playback control |
| `GET /simulation/state`, `GET /simulation/map` | Live state; static map (land use, fuel, elevation, assets) |
| `POST /simulation/ignite` | Start a fire at a cell |
| `POST /simulation/suppress` | Queue suppression on cells |
| `POST /simulation/dispatch` | Send the nearest free crew to an asset |
| `POST /simulation/auto-dispatch` | Turn automatic dispatch on/off |
| `POST /simulation/end` | Close the incident and record it |
| `GET /incidents`, `GET /incidents/{id}` | Incident history / one incident with timeline |
| `DELETE /incidents/{id}`, `DELETE /incidents` | Delete one / clear history |
| `POST /incidents/simulate` | Run and record a batch of simulated incidents |
| `GET /health` | Liveness check |

## Repository layout

```
engine/            simulation core, map + town generation, city layer       (E1, E4)
messaging/         message bus port, events, publisher, listener            (E3)
persistence/       repositories, snapshot + incident records                (E6)
api/               FastAPI scenario, playback, dispatch, incidents, UI      (E2)
frontend/          React + Three.js command center and admin dashboard      (E5)
tests/             pytest suite (unit + API tests)                          (E7)
docs/api/          generated API reference (pdoc)
docs/design/       architecture, class and pipeline diagrams (PlantUML)
infra/             docker compose deployment                                (E7)
build.py           build script: lint, compile, test, docs, package, deploy (E7)
Dockerfile         multi-stage image: UI build + Python runtime             (E7)
.github/workflows  CI/CD pipeline                                           (E7)
```

## Process

This repo follows a Scrum workflow: epics and stories as issues, sprints as milestones, a GitHub
Project board, and peer-reviewed pull requests on `issue-<number>` branches linked to their issues.
