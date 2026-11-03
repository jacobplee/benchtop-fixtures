"""The checker against known shapes built here, and against deliberately bad part parameters."""
import pytest
from build123d import Box, Cylinder, Polygon, Pos, Plane, extrude

from benchtop_fixtures import make
from benchtop_fixtures.check import check, main
from benchtop_fixtures.core import Fixture, HoleSpec, as_part
from benchtop_fixtures.standards import PRINTERS, SCREWS, INCH


def fx_of(shape, holes=()):
    shape = as_part(shape)
    bb = shape.bounding_box()
    shape = as_part(Pos(0, 0, -bb.min.Z) * shape)            # bed at z = 0
    return Fixture("probe", shape, {}, list(holes))


def status(fx, key, **kw):
    return check(fx, **kw).results[key].status


# ------------------------------------------------------------------ build volume
@pytest.mark.parametrize("size,fits_all", [((100, 100, 100), True), ((260, 10, 10), False), ((10, 10, 230), False)])
def test_build_volume_primitives(size, fits_all):
    fx = fx_of(Box(*size))
    assert status(fx, "build_volume") == ("pass" if fits_all else "fail")


def test_build_volume_per_printer():
    fx = fx_of(Box(200, 240, 10))                             # Prusa MK4 only after a 90 deg turn
    rep = check(fx, printers=("prusa_mk4",))
    per = rep.results["build_volume"].details["printers"]
    assert per["prusa_mk4"]["fits"] and per["bambu_x1c"]["fits"] and not per["form3"]["fits"]
    assert rep.results["build_volume"].status == "pass"
    assert check(fx).results["build_volume"].status == "fail"     # all three required by default


def test_printer_table():
    assert (PRINTERS["prusa_mk4"].x, PRINTERS["prusa_mk4"].y, PRINTERS["prusa_mk4"].z) == (250, 210, 220)
    assert (PRINTERS["bambu_x1c"].x, PRINTERS["bambu_x1c"].y, PRINTERS["bambu_x1c"].z) == (256, 256, 256)
    assert (PRINTERS["form3"].x, PRINTERS["form3"].y, PRINTERS["form3"].z) == (145, 145, 185)


# ------------------------------------------------------------------ minimum wall
@pytest.mark.parametrize("wall,ok", [(0.8, False), (1.1, False), (1.3, True), (2.0, True)])
def test_min_wall_open_box(wall, ok):
    outer = Box(30, 20, 15)
    inner = Pos(0, 0, wall) * Box(30 - 2 * wall, 20 - 2 * wall, 15)
    fx = fx_of(outer - inner)
    assert status(fx, "min_wall") == ("pass" if ok else "fail")


def test_min_wall_thin_rib_on_thick_block():
    fx = fx_of(Box(30, 30, 5) + Pos(0, 0, 7.5) * Box(0.8, 20, 10))
    assert status(fx, "min_wall") == "fail"


def test_min_wall_knife_edge_fails_but_square_corner_passes():
    wedge = extrude(Polygon((0, 0), (20, 0), (0, 8), align=None), 10)        # 22 deg knife edge
    assert status(fx_of(wedge), "min_wall") == "fail"
    assert status(fx_of(Box(20, 20, 20)), "min_wall") == "pass"


# ------------------------------------------------------------------ holes
def block_with_hole(d):
    return Box(20, 20, 10) - Cylinder(d / 2, 12)


@pytest.mark.parametrize("d,screw,fit,ok", [
    (3.4, "M3", "normal", True), (3.2, "M3", "close", True), (3.0, "M3", "normal", False),
    (3.4, "M3", "close", False), (4.5, "M4", "normal", True), (6.6, "M6", "normal", True),
    (0.180 * INCH, "#8", "close", True), (0.196 * INCH, "#8", "normal", True),
    ((17 / 64) * INCH, "1/4-20", "close", True), ((9 / 32) * INCH, "1/4-20", "normal", True),
    (6.6, "1/4-20", "normal", False),
])
def test_hole_table(d, screw, fit, ok):
    fx = fx_of(block_with_hole(d), [HoleSpec(screw, fit, (0, 0, 5))])
    assert status(fx, "holes") == ("pass" if ok else "fail")


def test_hole_missing_where_declared():
    fx = fx_of(block_with_hole(3.4), [HoleSpec("M3", "normal", (5, 0, 5))])
    rep = check(fx)
    assert rep.results["holes"].status == "fail"
    assert rep.results["holes"].details["holes"][0]["measured_mm"] is None


def test_hole_table_values():
    s = SCREWS
    assert (s["M3"].close, s["M3"].normal) == (3.2, 3.4)
    assert (s["M4"].close, s["M4"].normal) == (4.3, 4.5)
    assert (s["M6"].close, s["M6"].normal) == (6.4, 6.6)
    assert s["#8"].close == pytest.approx(4.572) and s["#8"].normal == pytest.approx(4.9784)
    assert s["1/4-20"].close == pytest.approx(6.746875) and s["1/4-20"].normal == pytest.approx(7.14375)


# ------------------------------------------------------------------ overhangs
def test_overhang_wide_shelf_is_flagged():
    t = Box(10, 10, 20) + Pos(0, 0, 12.5) * Box(60, 30, 5)                  # T: 25 mm cantilevers
    rep = check(fx_of(t))
    assert rep.results["overhangs"].status == "flag" and rep.verdict == "FLAG"


def test_overhang_short_bridge_is_accepted_and_listed():
    arch = Box(28, 10, 15) - Pos(0, 0, -2.5) * Box(8, 12, 10)                 # 8 mm bridge
    res = check(fx_of(arch)).results["overhangs"]
    assert res.status == "pass"
    assert len(res.details["bridges"]) == 1 and res.details["bridges"][0]["span_mm"] == pytest.approx(8.0, abs=0.05)


def test_overhang_long_bridge_is_flagged():
    arch = Box(40, 10, 15) - Pos(0, 0, -2.5) * Box(20, 12, 10)                # 20 mm bridge
    assert status(fx_of(arch), "overhangs") == "flag"


@pytest.mark.parametrize("angle,ok", [(45.0, True), (40.0, True), (50.0, False)])
def test_overhang_angle_limit(angle, ok):
    import math
    h = 10.0
    out = h * math.tan(math.radians(angle))
    prof = Polygon((0, 0), (10, 0), (10 + out, h), (-out, h), align=None)    # widens upward
    solid = extrude(Plane.XZ * prof, 10)
    assert status(fx_of(solid), "overhangs") == ("pass" if ok else "flag")


# ------------------------------------------------------------------ bad part parameters (C6)
@pytest.mark.parametrize("name,kw,key,want", [
    ("gridfinity_bin", dict(cells_x=7), "build_volume", "fail"),
    ("cable_clip", dict(wall=0.6), "min_wall", "fail"),
    ("cable_clip", dict(od=3.0, wall=1.0), "min_wall", "fail"),
    ("breadboard_adapter", dict(device_hole_d=4.0), "holes", "fail"),
    ("cable_clip", dict(style="screw", hole_d=3.0), "holes", "fail"),
    ("instrument_riser", dict(size=80.0, pad_d=20.0), "overhangs", "flag"),
    ("cable_clip", dict(opening=0.4), "overhangs", "flag"),
])
def test_bad_parameters_are_caught(name, kw, key, want):
    rep = check(make(name, **kw))
    assert rep.results[key].status == want, rep.text()
    assert rep.verdict == want.upper()


# ------------------------------------------------------------------ command line (C7)
@pytest.mark.parametrize("args,code", [(["cable_clip"], 0), (["cable_clip", "--set", "wall=0.6"], 1),
                                       (["cable_clip", "--set", "opening=0.4"], 2)])
def test_cli_exit_codes(args, code, capsys):
    assert main(args) == code
    out = capsys.readouterr().out
    assert out.startswith("cable_clip: ")
