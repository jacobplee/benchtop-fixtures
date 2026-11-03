"""Syringe or tube cradle, laid out from a list of (barrel OD, barrel length).

Barrels lie side by side along Y. Each barrel gets two saddles at the minimum-sag support points
of a uniformly loaded beam, 0.2232 L from each end, so a long barrel sits level. Frame: bed at
z = 0, cradle centred on the origin, barrel axes parallel to Y.
"""
from __future__ import annotations

import math

from build123d import Axis, Box, Cylinder, Pos, Rot, chamfer, extrude, Circle

from .. import standards as S
from ..core import Fixture, HoleSpec, as_part, check_positive, rr_prism

SUPPORT_AT = 0.2232     # minimum-deflection support points of a uniformly loaded beam, fraction of L


def tube_cradle(
    barrels: tuple = ((14.0, 80.0), (17.0, 120.0), (29.5, 115.0)),
    clearance: float = 0.4,
    wrap_deg: float = 200.0,
    saddle_width: float = 10.0,
    web: float = 4.0,
    floor: float = 3.0,
    base_thickness: float = 3.0,
    support_at: float = SUPPORT_AT,
    mount_screw: str | None = "M4",
    mount_fit: str = "normal",
    bottom_chamfer: float = 0.4,
) -> Fixture:
    """Syringe or tube cradle.

    barrels         list of (outside diameter, length) in mm, one lane each, left to right
    clearance       added to each diameter for the saddle bore
    wrap_deg        how far the saddle wraps the barrel; above 180 it snaps in (max 270)
    saddle_width    saddle thickness along the barrel
    web             material beside each bore and between lanes
    floor           material under each bore, above the base plate
    base_thickness  base plate thickness
    support_at      saddle position as a fraction of barrel length from each end
    mount_screw     screw size for four corner mounting holes, or None
    mount_fit       clearance class for the mounting holes
    bottom_chamfer  45 deg chamfer on the base's bottom edge, against elephant's foot
    """
    barrels = [tuple(map(float, b)) for b in barrels]
    if not barrels:
        raise ValueError("barrels must list at least one (diameter, length)")
    for d, length in barrels:
        check_positive(diameter=d, length=length)
    check_positive(saddle_width=saddle_width, web=web, floor=floor, base_thickness=base_thickness)
    if not 180.0 <= wrap_deg <= 270.0:
        raise ValueError("wrap_deg must be between 180 and 270")
    if not 0.05 <= support_at < 0.5:
        raise ValueError("support_at must be in [0.05, 0.5)")

    bores = [d + clearance for d, _ in barrels]
    xs, cur = [], web
    for b in bores:
        xs.append(cur + b / 2)
        cur += b + web
    W = cur
    xs = [x - W / 2 for x in xs]

    lift = math.sin(math.radians(wrap_deg / 2 - 90.0))   # lip height above the axis, per unit radius
    saddles = None
    lanes = []
    for (d, length), b, x in zip(barrels, bores, xs):
        r = b / 2
        zc = base_thickness + floor + r
        top = zc + r * lift
        yc = (0.5 - support_at) * length
        if yc < saddle_width / 2:
            raise ValueError(f"barrel {d} x {length}: saddles would overlap; shorten saddle_width")
        lanes.append(dict(x=round(x, 6), bore=b, axis_z=round(zc, 6), saddle_y=round(yc, 6), top=round(top, 6)))
        for y in (-yc, yc):
            blk = Pos(x, y, top / 2) * Box(b + 2 * web, saddle_width, top)
            blk = blk - Pos(x, y, zc) * Rot(90, 0, 0) * Cylinder(r, saddle_width + 2)
            saddles = blk if saddles is None else saddles + blk

    y_max = max(l["saddle_y"] for l in lanes) + saddle_width / 2
    holes: list[HoleSpec] = []
    if mount_screw:
        ms = S.screw(mount_screw)
        hd = ms.clearance(mount_fit)
        tab = max(2.5 * hd, hd + 6.0)
        L = 2 * (y_max + tab)
        base = rr_prism(W, L, 3.0, 0.0, base_thickness)
        if bottom_chamfer > 0:
            base = chamfer(base.edges().group_by(Axis.Z)[0], bottom_chamfer)
        hx, hy = W / 2 - max(hd + 2.5, 6.0), y_max + tab / 2
        for sx in (-1, 1):
            for sy in (-1, 1):
                base = base - Pos(sx * hx, sy * hy, -1) * extrude(Circle(hd / 2), base_thickness + 2)
                holes.append(HoleSpec(ms.name, mount_fit, (sx * hx, sy * hy, base_thickness / 2), label="mount"))
    else:
        L = 2 * (y_max + 3.0)
        base = rr_prism(W, L, 3.0, 0.0, base_thickness)
        if bottom_chamfer > 0:
            base = chamfer(base.edges().group_by(Axis.Z)[0], bottom_chamfer)
    body = base + saddles

    notes = [f"lane {i + 1}: OD {d:g} x {length:g} mm, bore {l['bore']:.2f}, saddles at y = +/-{l['saddle_y']:.1f}"
             for i, ((d, length), l) in enumerate(zip(barrels, lanes))]
    fx = Fixture("tube_cradle", as_part(body), {}, holes, notes)
    fx.lanes = lanes
    return fx
