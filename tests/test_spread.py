import numpy as np

from engine import Grid, PhysicsSpreadModel, Wind


def test_probability_zero_without_fire():
    g = Grid(10, 10)
    prob = PhysicsSpreadModel().ignition_probability(g, Wind())
    assert np.all(prob == 0.0)


def test_neighbours_of_fire_have_positive_probability():
    g = Grid(10, 10)
    g.ignite(5, 5)
    prob = PhysicsSpreadModel().ignition_probability(g, Wind())
    assert prob[5, 4] > 0.0  # west neighbour of the burning cell
    assert prob[0, 0] == 0.0  # far away, no burning neighbour


def test_wind_biases_spread_downwind():
    # Strong wind blowing east (90 deg) should favour the east neighbour.
    g = Grid(11, 11)
    g.ignite(5, 5)
    prob = PhysicsSpreadModel().ignition_probability(g, Wind(direction_deg=90, speed=40))
    assert prob[5, 6] > prob[5, 4]  # east (downwind) > west (upwind)
