"""Breadboard adapter: slots land on the breadboard grid exactly. Measured from B-rep cylinders."""
import itertools

import numpy as np
import pytest

from benchtop_fixtures import make
from benchtop_fixtures.standards import BREADBOARD, INCH, SCREWS
from conftest import holes_by_diameter, is_multiple

CASES = [("imperial", (5, 4)), ("metric", (5, 4)), ("imperial", (4, 3)), ("metric", (6, 2))]


def slot_ends(fx, system):
    sc = SCREWS[BREADBOARD[system]["screw"]]
    d = sc.clearance(fx.params["slot_fit"])
    ends = holes_by_diameter(fx.shape, d)
    assert ends, "no slot-end arcs of the clearance width found"
    for _, a in ends:
        assert abs(abs(a[2]) - 1) < 1e-9          # vertical
    return np.array([o[:2] for o, _ in ends])


@pytest.mark.parametrize("system,units", CASES)
def test_slot_ends_sit_on_the_grid(system, units):
    fx = make("breadboard_adapter", system=system, units=units, device_pattern=(30.0, 0.0))
    p = BREADBOARD[system]["pitch"]
    xy = slot_ends(fx, system)
    # every pairwise offset is a whole number of pitches
    for a, b in itertools.combinations(xy, 2):
        assert is_multiple(a[0] - b[0], p) and is_multiple(a[1] - b[1], p), (a, b)
    # and the grid is the breadboard's: holes are half a pitch in from the plate edge
    W, H = units[0] * p, units[1] * p
    for x, y in xy:
        assert is_multiple(x + W / 2 - p / 2, p) and is_multiple(y + H / 2 - p / 2, p)


@pytest.mark.parametrize("system,units", CASES)
def test_slot_travel_is_one_pitch(system, units):
    fx = make("breadboard_adapter", system=system, units=units, device_pattern=(30.0, 0.0))
    p = BREADBOARD[system]["pitch"]
    xy = slot_ends(fx, system)
    rows = {}
    for x, y in xy:
        rows.setdefault(round(y, 6), []).append(x)
    assert len(rows) == 2
    for xs in rows.values():
        xs = sorted(set(np.round(xs, 9)))
        assert len(xs) % 2 == 0
        for left, right in zip(xs[::2], xs[1::2]):
            assert right - left == pytest.approx(p, abs=1e-6)


def test_pitch_values():
    assert BREADBOARD["imperial"]["pitch"] == 25.4 == 1.0 * INCH
    assert BREADBOARD["metric"]["pitch"] == 25.0


@pytest.mark.parametrize("system", ["imperial", "metric"])
def test_counterbore_is_coaxial_with_every_slot_end(system):
    fx = make("breadboard_adapter", system=system)
    sc = SCREWS[BREADBOARD[system]["screw"]]
    ends = slot_ends(fx, system)
    cb = np.array([o[:2] for o, _ in holes_by_diameter(fx.shape, sc.cbore_d)])
    for e in ends:
        assert np.min(np.linalg.norm(cb - e, axis=1)) < 1e-6


def test_device_pattern_is_where_asked():
    fx = make("breadboard_adapter", device_pattern=(50.0, 30.0), device_screw="M3", device_fit="normal")
    xy = sorted(map(tuple, np.round([o[:2] for o, _ in holes_by_diameter(fx.shape, 3.4)], 6)))
    assert xy == [(-25.0, -15.0), (-25.0, 15.0), (25.0, -15.0), (25.0, 15.0)]


def test_device_pattern_colliding_with_slots_is_refused():
    with pytest.raises(ValueError):
        make("breadboard_adapter", units=(3, 2), device_pattern=(60.0, 40.0))
