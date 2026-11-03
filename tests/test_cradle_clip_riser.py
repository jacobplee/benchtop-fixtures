"""Cradle, clip and riser: dimensions read back from the B-rep."""
import math

import pytest
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

from benchtop_fixtures import make
from benchtop_fixtures.check import check
from conftest import cylinder_faces, holes_by_diameter


# ------------------------------------------------------------------ cradle
@pytest.mark.parametrize("barrels", [((14.0, 80.0), (17.0, 120.0), (29.5, 115.0)),
                                     ((20.0, 150.0),),
                                     ((8.0, 60.0), (10.0, 60.0), (12.0, 75.0), (15.0, 90.0), (21.0, 100.0))])
def test_cradle_saddles_follow_the_list(barrels):
    fx = make("tube_cradle", barrels=barrels)
    clr = fx.params["clearance"]
    for d, length in barrels:
        faces = cylinder_faces(fx.shape, d + clr)
        assert len(faces) >= 2, f"saddle bores for OD {d} not found"
        ys = sorted(f.center().Y for f in faces)
        # minimum-sag supports: 0.2232 L in from each end of a barrel centred on y = 0
        want = (0.5 - 0.2232) * length
        assert ys[0] == pytest.approx(-want, abs=1e-6) and ys[-1] == pytest.approx(want, abs=1e-6)
        for f in faces:                                   # bore axis runs along Y
            n = f.normal_at(f.center())
            assert abs(n.Y) < 1e-6
    assert check(fx).verdict == "PASS"


def test_cradle_bad_wrap_is_refused():
    with pytest.raises(ValueError):
        make("tube_cradle", wrap_deg=300)


# ------------------------------------------------------------------ clip
def ray_gap(shape, z, y=0.0):
    """Clear width across the clip opening at height z, measured by a ray along X from the centre."""
    it = IntCurvesFace_ShapeIntersector()
    it.Load(shape.wrapped, 1e-7)
    out = []
    for s in (1, -1):
        it.Perform(gp_Lin(gp_Pnt(0, y, z), gp_Dir(s, 0, 0)), 0.0, 1e3)
        out.append(min(it.WParameter(i) for i in range(1, it.NbPnt() + 1)))
    return sum(out)


@pytest.mark.parametrize("od,opening", [(6.0, 0.8), (10.0, 0.75), (4.0, 0.85)])
def test_clip_bore_and_opening(od, opening):
    fx = make("cable_clip", od=od, opening=opening)
    bore = od + fx.params["clearance"]
    assert holes_by_diameter(fx.shape, bore), "bore not found"
    # the tightest point of the opening is between the two round lip tips, at their centre height
    ri = bore / 2
    rm = ri + fx.params["wall"] / 2
    s = (opening * od + fx.params["wall"]) / (2 * rm)
    z_tips = fx.params["base"] + ri + rm * math.sqrt(1 - s * s)
    assert ray_gap(fx.shape, z_tips) == pytest.approx(opening * od, abs=1e-6)
    assert check(fx).verdict == "PASS"


@pytest.mark.parametrize("screw,fit,want", [("M3", "normal", 3.4), ("M4", "close", 4.3), ("#8", "normal", 0.196 * 25.4)])
def test_clip_screw_tab(screw, fit, want):
    fx = make("cable_clip", style="screw", od=8.0, screw=screw, fit=fit, width=12.0)
    hs = holes_by_diameter(fx.shape, want)
    assert len(hs) == 1 and abs(abs(hs[0][1][2]) - 1) < 1e-9
    assert check(fx).verdict == "PASS"


# ------------------------------------------------------------------ riser
@pytest.mark.parametrize("shape,pads", [("round", 4), ("square", 4), ("round", 3)])
def test_riser_pads(shape, pads):
    fx = make("instrument_riser", shape=shape, pads=pads, size=60.0)
    recess = fx.params["pad_d"] + fx.params["pad_clearance"]
    depth = fx.params["pad_thickness"] - fx.params["pad_protrusion"]
    faces = cylinder_faces(fx.shape, recess)
    assert len(faces) == pads
    for f in faces:
        bb = f.bounding_box()
        assert bb.min.Z == pytest.approx(0.0, abs=1e-6)
        assert bb.max.Z == pytest.approx(depth, abs=1e-6)


def test_riser_size_and_height():
    fx = make("instrument_riser")
    bb = fx.shape.bounding_box()
    assert bb.size.Z == pytest.approx(fx.params["height"], abs=1e-6)
    assert bb.size.X == pytest.approx(fx.params["size"], abs=1e-3)


def test_riser_overlapping_pads_are_refused():
    with pytest.raises(ValueError):
        make("instrument_riser", pad_d=25.0)
