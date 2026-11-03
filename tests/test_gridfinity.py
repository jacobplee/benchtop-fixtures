"""Gridfinity bin against the community spec.

Expected numbers are written out here from the spec (kennetek/gridfinity-rebuilt-openscad,
src/core/standard.scad, which follows https://gridfinity.xyz/specification/), not imported from
the implementation:
  grid pitch 42, height unit 7 (base included, lip excluded), base top 41.5 x 41.5 r 3.75,
  base profile from the bottom: 45 deg 0.8, vertical 1.8, 45 deg 2.15 (bottom 35.6 r 0.8),
  stacking lip from the inner tip: 45 deg 0.7, vertical 1.8, 45 deg 1.9 (depth 2.6, height 4.4),
  lip top rounded r 0.6.
"""
import itertools
import math

import pytest
from build123d import Plane, Pos, section

from benchtop_fixtures import make
from conftest import cylinder_faces, is_multiple

PITCH, UNIT = 42.0, 7.0
TOP, TOP_R = 41.5, 3.75
BOTTOM, BOTTOM_R = 35.6, 0.8


def rr_area(w, h, r):
    return w * h - (4 - math.pi) * r * r


def cut(shape, z):
    return section(shape, Plane.XY.offset(z)).faces()


@pytest.fixture(scope="module")
def bin1():
    return make("gridfinity_bin", cells_x=1, cells_y=1, units=3)


@pytest.mark.parametrize("z,width,radius", [
    (1e-6, BOTTOM, BOTTOM_R),                 # foot bottom
    (0.4, BOTTOM + 0.8, BOTTOM_R + 0.4),      # halfway up the first 45 deg band
    (0.8, 37.2, 1.6),                         # top of the first band
    (1.7, 37.2, 1.6),                         # vertical band 0.8 .. 2.6
    (2.6, 37.2, 1.6),
    (3.675, 37.2 + 2 * 1.075, 1.6 + 1.075),   # halfway up the 2.15 band
    (4.75 - 1e-6, TOP, TOP_R),                # top of the profile
    (6.0, TOP, TOP_R),                        # bridge band up to 7
])
def test_base_profile(bin1, z, width, radius):
    fs = cut(bin1.shape, z)
    assert len(fs) == 1
    bb = fs[0].bounding_box()
    assert bb.size.X == pytest.approx(width, abs=1e-5)
    assert bb.size.Y == pytest.approx(width, abs=1e-5)
    assert fs[0].area == pytest.approx(rr_area(width, width, radius), abs=1e-3)


def test_profile_heights_add_up():
    assert 0.8 + 1.8 + 2.15 == pytest.approx(4.75)
    assert BOTTOM + 2 * (0.8 + 2.15) == pytest.approx(TOP)


@pytest.mark.parametrize("nx,ny", [(2, 1), (3, 2), (1, 4)])
def test_feet_on_42mm_pitch_and_outer_size(nx, ny):
    fx = make("gridfinity_bin", cells_x=nx, cells_y=ny, units=2)
    feet = cut(fx.shape, 1.7)
    assert len(feet) == nx * ny
    cs = [f.center() for f in feet]
    for a, b in itertools.combinations(cs, 2):
        assert is_multiple(a.X - b.X, PITCH, 1e-6) and is_multiple(a.Y - b.Y, PITCH, 1e-6)
    xs = sorted({round(c.X, 6) for c in cs})
    assert len(xs) == nx and (nx == 1 or xs[1] - xs[0] == pytest.approx(42.0, abs=1e-6))
    bb = cut(fx.shape, 6.0)[0].bounding_box()
    assert bb.size.X == pytest.approx(PITCH * nx - 0.5, abs=1e-6)
    assert bb.size.Y == pytest.approx(PITCH * ny - 0.5, abs=1e-6)


@pytest.mark.parametrize("units", [2, 3, 6])
def test_height_units_and_lip(units):
    fx = make("gridfinity_bin", cells_x=1, cells_y=1, units=units)
    H = UNIT * units
    # lip: inner tip at the body top, 2.6 in from the outer wall; 1.9 in over the vertical band
    tip = cut(fx.shape, H + 1e-6)[0]
    assert tip.inner_wires()[0].bounding_box().size.X == pytest.approx(TOP - 2 * 2.6, abs=1e-5)
    band = cut(fx.shape, H + 0.7 + 0.9)[0]
    assert band.inner_wires()[0].bounding_box().size.X == pytest.approx(TOP - 2 * 1.9, abs=1e-5)
    # 45 deg lower lip band: halfway up 0.7 the inset is 2.6 - 0.35
    mid = cut(fx.shape, H + 0.35)[0]
    assert mid.inner_wires()[0].bounding_box().size.X == pytest.approx(TOP - 2 * 2.25, abs=1e-5)
    # top of the lip: the 4.4 mm spec line with its knife edge rounded r 0.6
    r = 0.6
    top = H + 4.4 - r * math.sqrt(2)
    assert fx.shape.bounding_box().max.Z == pytest.approx(top, abs=1e-6)


def test_bins_stack():
    """A second bin seats in the lip with zero interference where the profiles predict."""
    a = make("gridfinity_bin", cells_x=1, cells_y=1, units=3)
    H = 3 * UNIT
    # foot bottom (35.6) meets the lip inner tip (41.5 - 2 x 2.6 = 36.3) on parallel 45 deg faces
    seat = H - ((TOP - 2 * 2.6) - BOTTOM) / 2          # 21 - 0.35
    above = (Pos(0, 0, seat + 0.01) * a.shape) & a.shape
    below = (Pos(0, 0, seat - 0.05) * a.shape) & a.shape
    assert above.volume < 1e-6
    assert below.volume > 0.05


def test_cylinder_pocket():
    fx = make("gridfinity_bin", cells_x=1, cells_y=1, units=6, pocket="cylinder", pocket_d=30.0, pocket_depth=30.0)
    faces = cylinder_faces(fx.shape, 30.0)
    assert len(faces) == 1
    bb = faces[0].bounding_box()
    fill_top = 6 * UNIT - 1.2                            # STACKING_LIP_SUPPORT_HEIGHT under the lip
    assert bb.min.Z == pytest.approx(fill_top - 30.0, abs=1e-6)


def test_box_pocket():
    fx = make("gridfinity_bin", pocket="box", pocket_size=(70.0, 28.0), pocket_r=3.0, pocket_depth=10.0)
    fill_top = 3 * UNIT - 1.2
    fs = cut(fx.shape, fill_top - 5.0)
    hole = fs[0].inner_wires()[0].bounding_box()
    assert (hole.size.X, hole.size.Y) == (pytest.approx(70.0, abs=1e-6), pytest.approx(28.0, abs=1e-6))


@pytest.mark.parametrize("kw", [dict(units=1), dict(cells_x=0), dict(pocket="cylinder", pocket_d=40.0),
                                dict(pocket="box", pocket_depth=50.0), dict(pocket="hexagon")])
def test_bad_bin_parameters_are_refused(kw):
    with pytest.raises(ValueError):
        make("gridfinity_bin", **kw)
