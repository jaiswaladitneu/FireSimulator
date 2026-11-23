#!/usr/bin/env python3
"""Build script for the Fire Simulator: lint, compile, test, document, package, deploy.

Run it from the repository root with Python 3.11 or newer (Windows, macOS, Linux):

    python build.py <command> [<command> ...] [--scope all|backend|frontend]

Commands run in the order given and the build stops at the first failure (exit code 1).
The CI pipeline (.github/workflows/ci.yml) runs these same commands.

    setup     install the Python dev tools and the UI's npm packages
    lint      ruff on the backend, oxlint on the UI
    compile   byte-compile the backend; type-check and bundle the UI into frontend/dist
    test      pytest with branch coverage; fails below fail_under in pyproject.toml
    docs      generate the API reference HTML into docs/api with pdoc
    package   build the Docker image: API + built UI in one container
    smoke     start the image and check that the UI and the API answer
    deploy    start the app with docker compose on http://localhost:8000
    stop      stop the docker compose deployment
    clean     delete build outputs (frontend/dist, coverage reports, caches)
    ci        lint + compile + test + docs (what CI runs before packaging)
    all       ci + package + smoke
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
PACKAGES = ["engine", "api", "messaging", "persistence"]
COMPOSE_FILE = ROOT / "infra" / "docker-compose.yml"
REPO_URL = "https://github.com/jaiswaladitneu/FireSimulator"
DEFAULT_IMAGE = "firesim:local"
SMOKE_CONTAINER = "firesim-smoke"
ALIASES = {
    "ci": ["lint", "compile", "test", "docs"],
    "all": ["lint", "compile", "test", "docs", "package", "smoke"],
}


class BuildError(RuntimeError):
    """A build step failed; the message names the command or check that failed."""


def run(cmd: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    """Echo and run one command.

    Args:
        cmd: Program and arguments. The program is looked up on PATH, so ``npm`` also
            resolves to ``npm.cmd`` on Windows.
        cwd: Working directory for the command.
        env: Extra environment variables, added to the current environment.

    Raises:
        BuildError: If the program is missing or exits with a non-zero code.
    """
    exe = shutil.which(cmd[0]) or cmd[0]
    print(f"  $ {' '.join(cmd)}", flush=True)
    try:
        result = subprocess.run([exe, *cmd[1:]], cwd=cwd, env={**os.environ, **(env or {})})
    except FileNotFoundError as exc:
        raise BuildError(f"'{cmd[0]}' is not installed or not on PATH") from exc
    if result.returncode != 0:
        raise BuildError(f"'{' '.join(cmd)}' exited with code {result.returncode}")


def python(*args: str) -> list[str]:
    """Build a command that runs the current Python interpreter.

    Args:
        *args: Arguments for the interpreter, e.g. ``"-m", "pytest"``.

    Returns:
        The command as a list, starting with ``sys.executable``.
    """
    return [sys.executable, *args]


def wants(args: argparse.Namespace, part: str) -> bool:
    """Tell whether a part of the code base is in the selected scope.

    Args:
        args: Parsed command-line options (uses ``args.scope``).
        part: ``"backend"`` or ``"frontend"``.

    Returns:
        True if the scope is ``all`` or equals ``part``.
    """
    return args.scope in ("all", part)


def python_modules() -> list[str]:
    """List every backend package and its submodules, for the documentation generator.

    The packages define ``__all__`` for their re-exports, and pdoc would then skip the
    submodules they do not list (e.g. the city layer), so every module is named explicitly.

    Returns:
        Dotted module names, each package followed by its submodules.
    """
    modules = []
    for package in PACKAGES:
        modules.append(package)
        modules += [f"{package}.{f.stem}" for f in sorted((ROOT / package).glob("*.py"))
                    if f.stem != "__init__"]
    return modules


def npm_scripts() -> dict[str, str]:
    """Read the scripts defined in ``frontend/package.json``.

    Returns:
        Script names mapped to their commands.
    """
    return json.loads((FRONTEND / "package.json").read_text(encoding="utf-8")).get("scripts", {})


def http(url: str, body: dict | None = None) -> tuple[int, str]:
    """Send one GET (or POST with a JSON body) request.

    Args:
        url: Absolute URL.
        body: JSON body; when given the request is a POST.

    Returns:
        The HTTP status code and the response text.
    """
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def check_app(base: str, timeout_s: float = 90.0) -> None:
    """Wait for a running app, then check the UI, the API and one simulation step.

    Args:
        base: Base URL of the app, e.g. ``http://127.0.0.1:8080``.
        timeout_s: How long to wait for ``/health`` to answer.

    Raises:
        BuildError: If the app does not start in time or a check fails.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if http(f"{base}/health")[0] == 200:
                break
        except OSError:
            pass
        if time.monotonic() > deadline:
            raise BuildError(f"{base}/health did not answer within {timeout_s:.0f} s")
        time.sleep(1)

    status, page = http(f"{base}/")
    if status != 200 or "<title>" not in page:
        raise BuildError(f"GET / returned {status}; expected the UI's index.html")
    print("  ok  GET /                      -> UI index.html")
    checks = [
        ("GET /api/health", f"{base}/api/health", None, 200),
        ("POST /api/scenarios", f"{base}/api/scenarios",
         {"name": "Smoke test", "width": 30, "height": 30, "seed": 1,
          "ignition_points": [{"x": 15, "y": 15}]}, 201),
        ("POST /api/simulation/step", f"{base}/api/simulation/step", {}, 200),
    ]
    for label, url, body, expected in checks:
        status, text = http(url, body)
        if status != expected:
            raise BuildError(f"{label} returned {status} (expected {expected}): {text[:200]}")
        print(f"  ok  {label:<26} -> {status}")
    if json.loads(text).get("tick") != 1:
        raise BuildError("the simulation did not advance one tick")


# ---- commands ---------------------------------------------------------------------
def cmd_setup(args: argparse.Namespace) -> None:
    """Install the Python dev tools and the UI's locked npm packages."""
    if wants(args, "backend"):
        run(python("-m", "pip", "install", "-r", "requirements-dev.txt"))
    if wants(args, "frontend"):
        run(["npm", "ci", "--no-audit", "--no-fund"], cwd=FRONTEND)


def cmd_lint(args: argparse.Namespace) -> None:
    """Run the linters: ruff (Python) and oxlint (TypeScript/React)."""
    if wants(args, "backend"):
        run(python("-m", "ruff", "check", "."))
    if wants(args, "frontend"):
        run(["npm", "run", "lint"], cwd=FRONTEND)


def cmd_compile(args: argparse.Namespace) -> None:
    """Byte-compile the backend; type-check (tsc) and bundle (Vite) the UI."""
    if wants(args, "backend"):
        run(python("-m", "compileall", "-q", *PACKAGES))
    if wants(args, "frontend"):
        run(["npm", "run", "build"], cwd=FRONTEND)


def cmd_test(args: argparse.Namespace) -> None:
    """Run the unit tests with coverage; reports go to the terminal, htmlcov/ and coverage.xml."""
    if wants(args, "backend"):
        run(python("-m", "pytest", "--cov", "--cov-report=term-missing:skip-covered",
                   "--cov-report=html", "--cov-report=xml"),
            env={"FIRESIM_INCIDENTS_FILE": ":memory:"})
    if wants(args, "frontend") and "test" in npm_scripts():
        run(["npm", "test"], cwd=FRONTEND)


def cmd_docs(args: argparse.Namespace) -> None:
    """Generate the API reference (HTML) from the docstrings into docs/api."""
    if not wants(args, "backend"):
        return
    out = ROOT / "docs" / "api"
    if out.exists():
        shutil.rmtree(out)
    edit_links = [f"--edit-url={p}={REPO_URL}/blob/main/{p}/" for p in PACKAGES]
    # Source listings are left out (each page links to its module on GitHub instead).
    run(python("-m", "pdoc", *python_modules(), "--docformat", "google", "--no-show-source",
               "--output-directory", str(out), "--footer-text", "Fire Simulator API reference",
               *edit_links),
        env={"FIRESIM_INCIDENTS_FILE": ":memory:", "FIRESIM_STATIC_DIR": ""})
    print(f"  API reference: {out / 'index.html'}")


def cmd_package(args: argparse.Namespace) -> None:
    """Build the Docker image (multi-stage: Node builds the UI, Python serves it with the API)."""
    run(["docker", "build", "--tag", args.image, "."])


def cmd_smoke(args: argparse.Namespace) -> None:
    """Start the image in a throw-away container and check that it serves the UI and the API."""
    run(["docker", "run", "--detach", "--rm", "--name", SMOKE_CONTAINER,
         "--publish", f"{args.port}:8000", args.image])
    try:
        check_app(f"http://127.0.0.1:{args.port}")
    except BuildError:
        subprocess.run([shutil.which("docker") or "docker", "logs", SMOKE_CONTAINER])
        raise
    finally:
        subprocess.run([shutil.which("docker") or "docker", "stop", SMOKE_CONTAINER],
                       capture_output=True)


def cmd_deploy(args: argparse.Namespace) -> None:
    """Build and start the app with docker compose, then check it on port 8000."""
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "up", "--detach", "--build"])
    check_app("http://127.0.0.1:8000")
    print("  Fire Simulator is running: http://localhost:8000  (API docs: /docs)")


def cmd_stop(args: argparse.Namespace) -> None:
    """Stop and remove the docker compose deployment (the incident history volume is kept)."""
    run(["docker", "compose", "-f", str(COMPOSE_FILE), "down"])


def cmd_clean(args: argparse.Namespace) -> None:
    """Delete build outputs and caches."""
    for path in (FRONTEND / "dist", ROOT / "htmlcov", ROOT / "coverage.xml", ROOT / ".coverage",
                 ROOT / ".pytest_cache", ROOT / ".ruff_cache"):
        if path.is_dir():
            shutil.rmtree(path)
            print(f"  removed {path.relative_to(ROOT)}/")
        elif path.exists():
            path.unlink()
            print(f"  removed {path.relative_to(ROOT)}")


COMMANDS = {
    "setup": cmd_setup, "lint": cmd_lint, "compile": cmd_compile, "test": cmd_test,
    "docs": cmd_docs, "package": cmd_package, "smoke": cmd_smoke, "deploy": cmd_deploy,
    "stop": cmd_stop, "clean": cmd_clean,
}


def main(argv: list[str] | None = None) -> int:
    """Parse the command line and run the requested build steps in order.

    Args:
        argv: Command-line arguments without the program name; defaults to ``sys.argv[1:]``.

    Returns:
        The process exit code: 0 if every step passed, 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        prog="python build.py", description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n\n".join(__doc__.split("\n\n")[3:]))
    parser.add_argument("commands", nargs="+", metavar="command",
                        choices=[*COMMANDS, *ALIASES], help="one or more commands (see below)")
    parser.add_argument("--scope", choices=["all", "backend", "frontend"], default="all",
                        help="limit setup/lint/compile/test to one part (default: all)")
    parser.add_argument("--image", default=DEFAULT_IMAGE,
                        help=f"Docker image name for package/smoke (default: {DEFAULT_IMAGE})")
    parser.add_argument("--port", type=int, default=8080,
                        help="host port for the smoke-test container (default: 8080)")
    args = parser.parse_args(argv)

    steps = [step for command in args.commands for step in ALIASES.get(command, [command])]
    started = time.perf_counter()
    for step in steps:
        print(f"\n== {step} ==", flush=True)
        t0 = time.perf_counter()
        try:
            COMMANDS[step](args)
        except BuildError as exc:
            print(f"\nBUILD FAILED at '{step}': {exc}", file=sys.stderr, flush=True)
            return 1
        print(f"   {step}: ok ({time.perf_counter() - t0:.1f} s)", flush=True)
    print(f"\nBUILD OK: {' '.join(steps)} ({time.perf_counter() - started:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
