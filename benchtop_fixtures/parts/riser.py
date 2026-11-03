"""Instrument foot or riser with anti-slip pad recesses.

A tapered block that goes under an instrument foot: adhesive anti-slip pads sit in shallow
recesses underneath and stand proud by `pad_protrusion`; an optional cup on top locates the
instrument's own foot; an optional centre screw with a counterbore from below can bolt the riser
to the instrument. Frame: bed at z = 0 (the bottom), centred on the origin.
"""
from __future__ import annotations

import math

from build123d import Axis, Circle, Location, Pos, chamfer, extrude, loft

from .. import standards as S
from ..core import Fixture, HoleSpec, as_part, check_positive, circle_face, rr_face


def instrument_riser(
    shape: str = "round",
    size: float = 50.0,
    height: float = 25.0,
    taper_deg: float = 8.0,
    corner_r: float = 6.0,
    cup_d: float = 28.0,
    cup_depth: float = 3.0,
    pads: int = 4,
    pad_d: float = 9.5,
    pad_thickness: float = 2.0,
    pad_protrusion: float = 0.8,
    pad_clearance: float = 0.4,
    screw: str | None = "M4",
    fit: str = "normal",
    top_chamfer: float = 1.0,
    bottom_chamfer: float = 0.4,
) -> Fixture:
    """Instrument foot or riser.

    shape            "round" or "square"
    size             bottom diameter (round) or side (square), mm
    height           overall height
    taper_deg        side draft, top smaller than bottom (0 to 30)
    corner_r         bottom corner radius for the square shape
    cup_d, cup_depth locating cup on top for the instrument foot; cup_depth 0 disables it
    pads             number of pad recesses on the bottom (0 disables)
    pad_d            pad diameter; the recess is pad_d + pad_clearance
    pad_thickness    pad thickness; recess depth is pad_thickness - pad_protrusion
    pad_protrusion   how far each pad stands proud of the bottom
    screw, fit       centre screw clearance hole and counterbore from below, or screw=None
    top_chamfer      chamfer on the top outer edge
    bottom_chamfer   45 deg chamfer on the bottom edge, against elephant's foot
    """
    if shape not in ("round", "square"):
        raise ValueError("shape must be 'round' or 'square'")
    check_positive(size=size, height=height)
    if not 0.0 <= taper_deg <= 30.0:
        raise ValueError("taper_deg must be in [0, 30]")
    inset = height * math.tan(math.radians(taper_deg))
    top = size - 2 * inset
    if top < 0.5 * size:
        raise ValueError("taper too steep for this height: the top would be under half the bottom")

    # Both chamfers are built into the ruled loft as extra sections (exact 45 deg bands), which is
    # more robust than chamfering the lofted corners afterwards.
    tan_t = math.tan(math.radians(taper_deg))
    bc, tc = max(bottom_chamfer, 0.0), max(top_chamfer, 0.0)
    r0 = min(corner_r, size / 2 - 0.5)
    r_min = tc + 1.0

    def section(z, shrink=0.0):                    # `size` is the full size, reached at z = bottom chamfer
        dz = max(z - bc, 0.0)
        s = size - 2 * dz * tan_t - 2 * shrink
        if shape == "round":
            return circle_face(s, z)
        r = max(r0 - dz * tan_t, r_min) - shrink
        return rr_face(s, s, r, z)

    secs = []
    if bc > 0:
        secs.append(section(0.0, bc))
    secs.append(section(bc))
    secs.append(section(height - tc))
    if tc > 0:
        secs.append(section(height - tc, tc).moved(Location((0, 0, tc))))
    body = as_part(loft(secs, ruled=True))

    holes: list[HoleSpec] = []
    cb_h = cb_d = 0.0
    if screw:
        sc = S.screw(screw)
        hd = sc.clearance(fit)
        cb_d, cb_h = sc.cbore_d, sc.head_h + 0.4
        body = body - Pos(0, 0, -1) * extrude(Circle(hd / 2), height + 2)
        body = body - Pos(0, 0, -1) * extrude(Circle(cb_d / 2), cb_h + 1)
        holes.append(HoleSpec(sc.name, fit, (0.0, 0.0, height / 2), label="centre"))

    if cup_depth > 0:
        if cup_d / 2 + 2.0 > top / 2 - top_chamfer:
            raise ValueError("cup_d too large for the top face")
        if height - cup_depth - cb_h < 3.0:
            raise ValueError("cup and counterbore leave under 3 mm between them")
        body = body - Pos(0, 0, height - cup_depth) * extrude(Circle(cup_d / 2), cup_depth + 1)
        rim = body.edges().filter_by_position(Axis.Z, height - 1e-4, height + 1e-4)
        rim = [e for e in rim if math.hypot(e.center().X, e.center().Y) < cup_d / 2 + 0.01]
        if rim:
            body = chamfer(rim, min(0.8, cup_depth / 2))

    pocket_d = pad_d + pad_clearance
    depth = pad_thickness - pad_protrusion
    pad_pts = []
    if pads:
        if depth <= 0:
            raise ValueError("pad_thickness must exceed pad_protrusion")
        edge = 3.0 + bottom_chamfer
        if shape == "square" and pads == 4:
            a = size / 2 - pocket_d / 2 - edge
            pad_pts = [(sx * a, sy * a) for sx in (-1, 1) for sy in (-1, 1)]
        else:
            rp = size / 2 - pocket_d / 2 - edge
            pad_pts = [(rp * math.cos(math.radians(45 + 360 * k / pads)), rp * math.sin(math.radians(45 + 360 * k / pads)))
                       for k in range(pads)]
        for i, (x, y) in enumerate(pad_pts):
            if screw and math.hypot(x, y) - pocket_d / 2 - cb_d / 2 < 2.0:
                raise ValueError("pad recesses run into the centre counterbore; use a larger size or smaller pad_d")
            for (x2, y2) in pad_pts[i + 1:]:
                if math.hypot(x - x2, y - y2) - pocket_d < 2.0:
                    raise ValueError("pad recesses overlap; use fewer pads, a smaller pad_d or a larger size")
            body = body - Pos(x, y, -1) * extrude(Circle(pocket_d / 2), depth + 1)

    notes = [f"{pads} pad recesses {pocket_d:.1f} mm x {depth:.1f} mm deep (pads stand {pad_protrusion} mm proud)"
             if pads else "no pad recesses"]
    fx = Fixture("instrument_riser", as_part(body), {}, holes, notes)
    fx.pad_points = pad_pts
    fx.pad_recess = (pocket_d, depth)
    return fx
