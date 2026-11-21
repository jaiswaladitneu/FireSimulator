import numpy as np
import pytest

from engine import (
    CellState,
    CityMapGenerator,
    FuelType,
    Grid,
    LandUse,
    PhysicsSpreadModel,
    Scenario,
    SimulationEngine,
    UrbanSpreadModel,
    Wind,
    create_session,
)
from engine.city import BURNING, chebyshev_distance
from engine.population import KIND_INDEX


def city_session(**overrides):
    params = dict(name="t", width=64, height=64, seed=3, wind_direction=90, wind_speed=25,
                  map_type="city", hour=14, crews=4)
    params.update(overrides)
    return create_session(Scenario(**params))


# ---- town generation ------------------------------------------------------
def test_city_generation_is_deterministic():
    a = CityMapGenerator.generate(64, 64, seed=5)
    b = CityMapGenerator.generate(64, 64, seed=5)
    assert np.array_equal(a.landuse, b.landuse)
    assert np.array_equal(a.grid.fuel, b.grid.fuel)
    assert [x.to_dict() for x in a.assets] == [x.to_dict() for x in b.assets]


def test_city_has_every_kind_of_place():
    city = CityMapGenerator.generate(96, 96, seed=1)
    kinds = {a.kind for a in city.assets}
    assert {"house", "commercial", "school", "hospital", "park", "road",
            "fuel_station", "battery_storage", "fire_station"} <= kinds


def test_roads_water_and_paving_cannot_burn():
    city = CityMapGenerator.generate(80, 80, seed=2)
    for lu in (LandUse.ROAD, LandUse.WATER, LandUse.PAVED):
        assert (city.grid.fuel[city.landuse == lu] == FuelType.NONE).all()


def test_asset_cells_are_consistent():
    city = CityMapGenerator.generate(80, 80, seed=4)
    for a in city.assets:
        assert 0 <= a.x and a.x + a.w <= 80 and 0 <= a.y and a.y + a.h <= 80
        for p in a.parts:
            assert (city.asset_id[p.y:p.y + p.h, p.x:p.x + p.w] == a.id).all()
    assert set(np.unique(city.asset_id[city.asset_id >= 0])) <= set(range(len(city.assets)))


def test_city_map_rejects_tiny_grids():
    with pytest.raises(ValueError):
        CityMapGenerator.generate(30, 30)


# ---- urban spread (Strategy) ------------------------------------------------
def _crosses_road(model, wind_speed: float) -> bool:
    g = Grid(40, 20)                              # all grass
    g.fuel[:, 20:22] = FuelType.NONE              # a 2-cell-wide road
    g.fuel_remaining = (g.fuel != FuelType.NONE).astype(np.float32)
    eng = SimulationEngine(g, Wind(90, wind_speed), seed=1, spread_model=model)
    for y in range(20):
        eng.ignite(2, y)
    eng.run(200)
    return bool((g.state[:, 22:] != CellState.UNBURNED).any())


def test_embers_carry_fire_across_a_road_in_wind():
    assert not _crosses_road(PhysicsSpreadModel(), 35)   # adjacent-only spread stops at the road
    assert _crosses_road(UrbanSpreadModel(), 35)          # wind-blown embers jump it


def test_no_ember_spotting_in_calm_air():
    assert not _crosses_road(UrbanSpreadModel(), 0)


def test_wildland_scenarios_keep_the_default_model():
    s = create_session(Scenario(name="w", width=30, height=30, seed=1))
    assert s.city is None
    assert type(s.engine.spread_model) is PhysicsSpreadModel


# ---- people, risk and priorities ----------------------------------------------
def test_people_are_conserved_through_a_whole_incident():
    s = city_session(wind_speed=30)
    s.engine.run(600)
    c = s.city
    assert ((c.occ + c.evac + c.cas) == c.occ0).all()
    assert c.population()["total"] == int(c.occ0.sum())


def test_burning_school_puts_lives_at_risk_and_is_critical():
    s = city_session(hour=10, wind_speed=10)        # school in session
    city = s.city
    school = next(a for a in city.assets if a.kind == "school")
    part = school.parts[0]
    s.engine.spot_fire(part.x, part.y)
    city.refresh()
    assert city.status[school.id] == BURNING
    assert city.at_risk[school.id] > 0
    entry = next(p for p in city.priorities if p["id"] == school.id)
    assert entry["level"] == "critical"


def test_priorities_list_critical_first_at_every_tick():
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    s = city_session(wind_speed=30)
    s.engine.start()
    seen_critical = False
    for _ in range(160):
        s.engine.advance()
        levels = [rank[p["level"]] for p in s.city.priorities]
        assert levels == sorted(levels)          # never a lower level above a higher one
        seen_critical |= 0 in levels
    assert seen_critical


def test_night_time_homes_react_slower():
    day = city_session(hour=14).city
    night = city_session(hour=2).city
    houses = day.kind == KIND_INDEX["house"]
    assert (night.delay[houses] == 2 * day.delay[houses]).all()


def test_fuel_station_explodes_when_it_burns():
    s = city_session()
    city, eng = s.city, s.engine
    station = next(a for a in city.assets if a.kind == "fuel_station")
    canopy = next(p for p in station.parts if p.style == "canopy")
    eng.spot_fire(canopy.x, canopy.y)
    eng.start()
    eng.advance()
    assert city.exploded[station.id]
    assert any(e["type"] == "explosion" for e in city.events)


# ---- fire crews ----------------------------------------------------------------
def test_dispatched_crew_travels_then_suppresses():
    s = city_session(wind_speed=10)
    city, eng = s.city, s.engine
    house = next(a for a in city.assets if a.kind == "house")
    eng.spot_fire(house.x, house.y)
    city.refresh()
    crew = city.dispatch(house.id)
    assert crew is not None and crew.status == "en_route"
    eng.start()
    for _ in range(crew.travel_total + 3):
        eng.advance()
    assert crew.cells_suppressed > 0
    assert (eng.grid.state == CellState.SUPPRESSED).any()


def test_dispatch_fails_when_every_crew_is_busy():
    city = city_session(crews=1).city
    a, b = [x.id for x in city.assets if x.kind == "house"][:2]
    assert city.dispatch(a) is not None
    assert city.dispatch(b) is None


def test_auto_dispatch_sends_crews():
    s = city_session(wind_speed=30, auto_dispatch=True)
    s.engine.run(150)
    assert s.city.response.dispatch_count > 0


def test_reset_restores_people_and_crews():
    s = city_session(wind_speed=30, auto_dispatch=True)
    s.engine.run(80)
    s.engine.reset()
    c = s.city
    assert (c.occ == c.occ0).all() and c.cas.sum() == 0 and c.evac.sum() == 0
    assert all(crew.status == "available" for crew in c.response.crews)
    assert c.events == [] and len(c.timeline) == 1


def test_chebyshev_distance():
    m = np.zeros((5, 5), dtype=bool)
    m[2, 2] = True
    d = chebyshev_distance(m, 3)
    assert d[2, 2] == 0 and d[1, 3] == 1 and d[0, 0] == 2 and d[2, 4] == 2
