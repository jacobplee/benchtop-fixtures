"""Cable and tube clip for a given outside diameter.

The clip is a C-ring on a flat base, extruded along the cable (Y). `style="snap"` is the ring on
an adhesive base; `style="screw"` adds a screw tab. Frame: bed at z = 0, ring axis on
x = 0, z = base + bore radius.

Print note: the lip tips sit at least 45 degrees from the top of the ring, so the inside of the
ring never overhangs more than 45 degrees. A narrower opening than that needs support; the
checker flags it.
"""
from __future__ import annotations

import math

from build123d import (BuildSketch, Circle, Locations, Mode, Plane, Polygon, Pos, Rectangle, extrude)

from .. import standards as S
from ..core import Fixture, HoleSpec, as_part, check_positive


def cable_clip(
    od: float = 6.0,
    clearance: float = 0.3,
    wall: float = 2.0,
    width: float = 10.0,
    opening: float = 0.8,
    base: float = 2.0,
    style: str = "snap",
    screw: str = "M3",
    fit: str = "normal",
    tabs: int = 1,
    tab_thickness: float = 3.0,
    hole_d: float | None = None,
) -> Fixture:
    """Cable and tube clip.

    od             cable or tube outside diameter, mm
    clearance      added to od for the bore
    wall           ring wall thickness (the lip tips are full rounds of this diameter)
    width          clip length along the cable
    opening        clear gap between the lip tips as a fraction of od (snap retention)
    base           material under the bore
    style          "snap" (adhesive base) or "screw" (adds screw tabs)
    screw, fit     screw tab hole size and clearance class
    tabs           1 or 2 screw tabs
    tab_thickness  screw tab thickness
    hole_d         override the tab hole diameter (the checker flags values off the table)
    """
    if style not in ("snap", "screw"):
        raise ValueError("style must be 'snap' or 'screw'")
    check_positive(od=od, wall=wall, width=width, opening=opening, base=base)
    ri = (od + clearance) / 2
    ro = ri + wall
    rm = ri + wall / 2
    zc = base + ri
    gap = opening * od
    s = (gap + wall) / (2 * rm)
    if s >= 1.0:
        raise ValueError("opening is wider than the ring; lower `opening`")
    psi = math.asin(s)                       # lip tip angle from the top of the ring

    with BuildSketch(Plane.XZ) as sk:
        with Locations((0, zc)):
            Circle(ro)
        with Locations((0, zc / 2)):
            Rectangle(2 * ro, zc)
        # remove the wedge above the lip tips
        n = 24
        R = 3 * ro
        wedge = [(0.0, zc)] + [(R * math.sin(a), zc + R * math.cos(a))
                               for a in [-psi + 2 * psi * k / n for k in range(n + 1)]]
        Polygon(*wedge, align=None, mode=Mode.SUBTRACT)
        # round lip tips
        for sgn in (-1, 1):
            with Locations((sgn * rm * math.sin(psi), zc + rm * math.cos(psi))):
                Circle(wall / 2)
        with Locations((0, zc)):
            Circle(ri, mode=Mode.SUBTRACT)
    clip = extrude(sk.sketch, amount=width / 2, both=True)

    holes: list[HoleSpec] = []
    if style == "screw":
        if tabs not in (1, 2):
            raise ValueError("tabs must be 1 or 2")
        sc = S.screw(screw)
        hd = sc.clearance(fit) if hole_d is None else float(hole_d)
        edge = max(2.5, 0.6 * hd)
        tab_len = hd + 2 * edge
        if width < hd + 2 * 1.5:
            raise ValueError("width too small for the tab hole")
        for sgn in ((1,) if tabs == 1 else (1, -1)):
            xc = sgn * (ro + tab_len / 2)
            tab = Pos(sgn * (ro + tab_len / 2 - 0.5), 0, tab_thickness / 2) * _box(tab_len + 1.0, width, tab_thickness)
            tab = tab - Pos(xc, 0, -1) * extrude(Circle(hd / 2), tab_thickness + 2)
            clip = clip + tab
            holes.append(HoleSpec(sc.name, fit, (xc, 0.0, tab_thickness / 2), label="tab"))

    notes = [f"bore {2 * ri:.2f} mm for OD {od:g}, opening {gap:.2f} mm, lip tips {math.degrees(psi):.1f} deg from top"]
    fx = Fixture("cable_clip", as_part(clip), {}, holes, notes)
    fx.bore = 2 * ri
    fx.gap = gap
    fx.axis_z = zc
    return fx


def _box(x, y, z):
    from build123d import Box
    return Box(x, y, z)
