"""Headless demo: run a scenario and print the fire as ASCII.

    python demo.py

Legend:  . unburned   + igniting   # burning   _ burned   X suppressed
"""
from engine import CellState, Scenario, SimulationEngine
from engine.scenario import IgnitionPoint

GLYPH = {
    CellState.UNBURNED: ".",
    CellState.IGNITING: "+",
    CellState.BURNING: "#",
    CellState.BURNED: "_",
    CellState.SUPPRESSED: "X",
}


def render(engine: SimulationEngine) -> None:
    c = engine.counts()
    print(
        f"\n-- tick {engine.tick:>3}  [{engine.state.value}]  "
        f"burning={c['burning']}  burned={c['burned']}  suppressed={c['suppressed']} --"
    )
    g = engine.grid
    for y in range(g.height):
        print("".join(GLYPH[g.get_state(x, y)] for x in range(g.width)))


def main() -> None:
    scenario = Scenario(
        name="Demo Burn", width=48, height=18, seed=4821,
        wind_direction=90, wind_speed=25,            # wind blowing east
        ignition_points=[IgnitionPoint(10, 9)],
    )
    engine = SimulationEngine.from_scenario(scenario)
    engine.start()
    render(engine)
    for _ in range(4):
        for _ in range(7):
            if engine.state.value == "running":
                engine.advance()
        render(engine)
    engine.run()  # let it finish
    render(engine)
    print(f"\nFire out after {engine.tick} ticks.")


if __name__ == "__main__":
    main()
