# Fire Simulator documentation

| What | Where |
|---|---|
| **API reference** (generated from the docstrings with pdoc) | [`api/index.html`](api/index.html) |
| **Design diagrams** (PlantUML sources + PNG/SVG) | [`design/`](design/) |
| Interactive REST docs (Swagger / OpenAPI) | `/docs` on a running server, e.g. http://localhost:8000/docs |
| Test coverage report | `htmlcov/index.html` after `python build.py test`, or the `coverage-report` artifact of a CI run |

## API reference

`docs/api/` holds the HTML reference for every backend package and module: `engine` (simulation
core and city layer), `api` (FastAPI app and request models), `messaging` and `persistence`.
Every public class lists its attributes, and every public function and method lists its
arguments, return value and raised exceptions (Google-style docstrings rendered by
[pdoc](https://pdoc.dev)). Each page links to its source file on GitHub.

GitHub shows `.html` files as source. To read the pages:

- clone the repository and open `docs/api/index.html` in a browser, or
- download the `api-docs` artifact from the latest run of the CI workflow, or
- once GitHub Pages is enabled for `main` → `/docs` (repository owner: Settings → Pages), browse
  https://jaiswaladitneu.github.io/FireSimulator/api/

Regenerate after changing docstrings:

```bash
python build.py docs
```

## Design diagrams

| Diagram | Shows |
|---|---|
| [`architecture`](design/architecture.png) | Deployed components (browser, container, API, engine, persistence) and the Part B services that are planned but not built (dashed) |
| [`class-engine`](design/class-engine.png) | Simulation core: engine, grid, spread-model Strategy, tick Observer, state machine, session factory |
| [`class-city`](design/class-city.png) | City layer: town generator, assets, people model, priorities, fire crews |
| [`class-api`](design/class-api.png) | FastAPI facade, request models, `/api` middleware, repositories and records |
| [`class-messaging`](design/class-messaging.png) | MessageBus port and in-memory adapter, event publisher, suppression listener, versioned events |
| [`class-frontend`](design/class-frontend.png) | React views, `useSimulation` store, typed API client, Three.js scene controller |
| [`ci-pipeline`](design/ci-pipeline.png) | The GitHub Actions pipeline: backend, frontend and package jobs |

Stereotypes such as `<<Strategy>>`, `<<Observer>>`, `<<Repository>>` or `<<Facade>>` mark the
role each class plays; each diagram's legend explains them. To re-render after editing a
`.puml` file (needs Java and [PlantUML](https://plantuml.com)):

```bash
cd docs/design
java -jar plantuml.jar -tpng *.puml
java -jar plantuml.jar -tsvg *.puml
```
