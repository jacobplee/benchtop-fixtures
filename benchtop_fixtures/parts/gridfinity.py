"""Gridfinity-compatible bin: N x M cells, 7 mm height units, stacking lip, optional pocket.

Every profile number comes from `standards.py`, which cites the community specification.
Frame: bed at z = 0, bin centred on the origin, X along `cells_x`.
"""
from __future__ import annotations

import math

from build123d import (Axis, Edge, Face, Part, Pos, Wire, chamfer, extrude, fillet, sweep,
                       Circle, RectangleRounded)

from .. import standards as S
from ..core import Fixture, as_part, check_positive, rr_prism


def _foot(x: float, y: float) -> Part:
    """One cell's base: 35.6 (r 0.8) at z 0, 45 deg out 0.8, straight up 1.8, 45 deg out 2.15.

    Built from tapered extrusions so the 45 deg corners are exact cones (a loft would give B-splines).
    """
    (_, _), (o1, z1), (_, z2), (o3, z3) = S.GF_PROFILE
    w1, r1 = S.GF_BOTTOM + 2 * o1, S.GF_BOTTOM_R + o1
    band1 = extrude(RectangleRounded(S.GF_BOTTOM, S.GF_BOTTOM, S.GF_BOTTOM_R), amount=z1, taper=-45)
    band2 = Pos(0, 0, z1) * extrude(RectangleRounded(w1, w1, r1), amount=z2 - z1)
    band3 = Pos(0, 0, z2) * extrude(RectangleRounded(w1, w1, r1), amount=z3 - z2, taper=-45)
    return as_part(Pos(x, y, 0) * (band1 + band2 + band3))


def _rr_path(w: float, h: float, r: float, z: float) -> Wire:
    """Closed rounded-rectangle wire, counter-clockwise, starting mid right side (+X)."""
    a, b = w / 2, h / 2
    c = r * (1 - math.sqrt(0.5))
    pts = [
        ("L", (a, 0), (a, b - r)),
        ("A", (a, b - r), (a - c, b - c), (a - r, b)),
        ("L", (a - r, b), (-a + r, b)),
        ("A", (-a + r, b), (-a + c, b - c), (-a, b - r)),
        ("L", (-a, b - r), (-a, -b + r)),
        ("A", (-a, -b + r), (-a + c, -b + c), (-a + r, -b)),
        ("L", (-a + r, -b), (a - r, -b)),
        ("A", (a - r, -b), (a - c, -b + c), (a, -b + r)),
        ("L", (a, -b + r), (a, 0)),
    ]
    edges = []
    for kind, *p in pts:
        q = [(u, v, z) for u, v in p]
        edges.append(Edge.make_line(*q) if kind == "L" else Edge.make_three_point_arc(*q))
    return Wire(edges)


def lip_profile_points():
    """Stacking lip cross-section as (inset from the outer wall, z above the body top).

    Spec line STACKING_LIP_LINE: inner tip, 45 deg out 0.7, up 1.8, 45 deg out 1.9 to the outer
    wall. The knife edge at the top is rounded with the spec's 0.6 mm fillet, and a 45 deg support
    runs under the lip back to the wall (STACKING_LIP_SUPPORT_HEIGHT = 1.2) so it never floats.
    """
    rf = S.GF_LIP_FILLET
    d, h = S.GF_LIP_DEPTH, S.GF_LIP_H                    # 2.6, 4.4
    zc = h - rf - rf * math.sqrt(2)                       # fillet centre at inset rf, tangent to wall and slope
    t = rf / math.sqrt(2)
    support_bottom = -(S.GF_LIP_SUPPORT_H + d)            # 45 deg support from the wall up to the tip
    return dict(
        wall_bottom=(0.0, support_bottom),
        wall_top=(0.0, zc),
        arc_top=(rf, zc + rf),
        slope_top=(rf + t, zc + t),
        mid_top=(d - 0.7, 2.5),
        mid_bottom=(d - 0.7, 0.7),
        tip=(d, 0.0),
        tip_bottom=(d, -S.GF_LIP_SUPPORT_H),
        top_z=zc + rf,
    )


def _lip(w: float, h: float, z_top: float) -> Part:
    P = lip_profile_points()
    a = w / 2

    def to3(p):
        s, z = p
        return (a - s, 0.0, z_top + z)

    edges = []
    edges.append(Edge.make_line(to3(P["wall_bottom"]), to3(P["wall_top"])))
    edges.append(Edge.make_three_point_arc(to3(P["wall_top"]), to3(P["arc_top"]), to3(P["slope_top"])))
    chain = [P["slope_top"], P["mid_top"], P["mid_bottom"], P["tip"], P["tip_bottom"], P["wall_bottom"]]
    for p, q in zip(chain, chain[1:]):
        edges.append(Edge.make_line(to3(p), to3(q)))
    profile = Face(Wire(edges))
    path = _rr_path(w, h, S.GF_TOP_R, z_top)
    return as_part(sweep(profile, path=path))


def gridfinity_bin(
    cells_x: int = 2,
    cells_y: int = 1,
    units: int = 3,
    wall: float = 1.2,
    lip: bool = True,
    floor_fillet: float | None = None,
    pocket: str | None = None,
    pocket_size: tuple[float, float] = (30.0, 20.0),
    pocket_d: float = 20.0,
    pocket_depth: float = 10.0,
    pocket_r: float = 2.0,
    pocket_offset: tuple[float, float] = (0.0, 0.0),
    pocket_chamfer: float = 0.8,
) -> Fixture:
    """Gridfinity-compatible bin.

    cells_x, cells_y  footprint in 42 mm grid cells
    units             height in 7 mm units, base included, stacking lip excluded (min 2)
    wall              wall thickness, mm
    lip               add the stacking lip
    floor_fillet      scoop radius where the floor meets the walls (default: spec 2.8, capped by the corner)
    pocket            None for an open bin, "box" or "cylinder" for a solid fill with one pocket cut in
    pocket_size       box pocket X, Y size; pocket_r its corner radius
    pocket_d          cylinder pocket diameter
    pocket_depth      pocket depth below the fill top
    pocket_offset     pocket centre offset from the bin centre
    pocket_chamfer    lead-in chamfer on the pocket rim
    """
    if int(cells_x) != cells_x or int(cells_y) != cells_y or cells_x < 1 or cells_y < 1:
        raise ValueError("cells_x and cells_y must be whole numbers >= 1")
    if int(units) != units or units < 2:
        raise ValueError("units must be a whole number >= 2 (one unit is the base alone)")
    check_positive(wall=wall)
    if pocket not in (None, "box", "cylinder"):
        raise ValueError("pocket must be None, 'box' or 'cylinder'")

    W = S.GF_PITCH * cells_x - S.GF_GAP
    D = S.GF_PITCH * cells_y - S.GF_GAP
    H = S.GF_UNIT_H * units
    r_out = S.GF_TOP_R
    r_in = r_out - wall
    if r_in <= 0.2:
        raise ValueError("wall too thick for the 3.75 mm outer corner")

    # feet, one per cell, on the 42 mm pitch
    body = None
    for i in range(cells_x):
        for j in range(cells_y):
            x = S.GF_PITCH * (i - (cells_x - 1) / 2)
            y = S.GF_PITCH * (j - (cells_y - 1) / 2)
            f = _foot(x, y)
            body = f if body is None else body + f
    # bridge + walls: one outline from the top of the profile to the body top
    body = body + rr_prism(W, D, r_out, S.GF_PROFILE_H, H)

    fill_top = H - S.GF_LIP_SUPPORT_H if lip else H - wall
    if pocket is None:
        cav = rr_prism(W - 2 * wall, D - 2 * wall, r_in, S.GF_BASE_H, H + 10)
        rf = S.GF_FLOOR_FILLET if floor_fillet is None else floor_fillet
        rf = min(rf, 0.75 * r_in)
        if rf > 0:
            cav = fillet(cav.edges().group_by(Axis.Z)[0], rf)
        body = body - cav
    else:
        cav = rr_prism(W - 2 * wall, D - 2 * wall, r_in, fill_top, H + 10)
        body = body - cav
        floor_z = fill_top - pocket_depth
        min_floor = S.GF_PROFILE_H + wall
        if floor_z < min_floor:
            raise ValueError(f"pocket_depth too deep: floor at z {floor_z:.2f}, minimum {min_floor:.2f}")
        ox, oy = pocket_offset
        if pocket == "box":
            px, py = pocket_size
            check_positive(pocket_x=px, pocket_y=py)
            half = (px / 2, py / 2)
            tool = rr_prism(px, py, pocket_r, floor_z, fill_top + 5, ox, oy)
        else:
            check_positive(pocket_d=pocket_d)
            half = (pocket_d / 2, pocket_d / 2)
            tool = Pos(ox, oy, floor_z) * extrude(Circle(pocket_d / 2), fill_top + 5 - floor_z)
        lim_x, lim_y = W / 2 - S.GF_LIP_DEPTH - wall, D / 2 - S.GF_LIP_DEPTH - wall
        if abs(ox) + half[0] > lim_x + 1e-9 or abs(oy) + half[1] > lim_y + 1e-9:
            raise ValueError(f"pocket does not fit: keep |offset| + half size within ({lim_x:.2f}, {lim_y:.2f})")
        body = body - tool
        if pocket_chamfer > 0:
            rim = body.edges().filter_by_position(Axis.Z, fill_top - 1e-4, fill_top + 1e-4)
            rim = [e for e in rim if _inside_pocket_rim(e, ox, oy, half)]
            if rim:
                body = chamfer(rim, pocket_chamfer)

    if lip:
        body = body + _lip(W, D, H)

    notes = [f"outer {W:.1f} x {D:.1f} mm, body {H:.1f} mm + lip" if lip else f"outer {W:.1f} x {D:.1f} x {H:.1f} mm"]
    return Fixture("gridfinity_bin", as_part(body), {}, holes=[], notes=notes)


def _inside_pocket_rim(edge, ox, oy, half) -> bool:
    c = edge.center()
    return abs(c.X - ox) <= half[0] + 1e-3 and abs(c.Y - oy) <= half[1] + 1e-3
