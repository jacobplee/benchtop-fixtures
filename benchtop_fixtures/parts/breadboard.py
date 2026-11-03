"""Optical breadboard adapter plate.

Bolts to a breadboard with counterbored clearance slots and carries a device on a rectangular
bolt pattern. Frame: bed at z = 0 (the face that sits on the breadboard), plate centred on the
origin. With the plate centred, breadboard holes under it sit at odd multiples of half a pitch
when `units` is even and at whole multiples when it is odd, so slot ends always land on holes.
"""
from __future__ import annotations

import math

from build123d import (Axis, Circle, Pos, RegularPolygon, SlotCenterToCenter, chamfer, extrude)

from .. import standards as S
from ..core import Fixture, HoleSpec, as_part, check_positive, rr_prism


def breadboard_adapter(
    system: str = "imperial",
    units: tuple[int, int] = (5, 4),
    thickness: float = 12.0,
    corner_r: float = 4.0,
    slot_fit: str = "normal",
    device_pattern: tuple[float, float] = (60.0, 40.0),
    device_screw: str = "M4",
    device_fit: str = "close",
    nut_traps: bool = True,
    device_hole_d: float | None = None,
    top_chamfer: float = 1.0,
    bottom_chamfer: float = 0.4,
) -> Fixture:
    """Breadboard adapter plate.

    system          "imperial" (1/4-20 on a 25.4 mm grid) or "metric" (M6 on a 25 mm grid)
    units           plate size in grid pitches (nx, ny), each >= 2
    thickness       plate thickness, mm
    slot_fit        clearance class for the breadboard screws: "close" or "normal"
    device_pattern  device hole spacing (X, Y), mm, centred; use 0 on an axis for a single row
    device_screw    device screw size from the table
    device_fit      clearance class for the device screws
    nut_traps       hex nut pockets under each device hole
    device_hole_d   override the device hole diameter (the checker flags values off the table)
    top_chamfer     chamfer on the top outer edge
    bottom_chamfer  45 deg chamfer on the bottom outer edge, against elephant's foot
    """
    if system not in S.BREADBOARD:
        raise ValueError(f"system must be one of {sorted(S.BREADBOARD)}")
    nx, ny = (int(units[0]), int(units[1]))
    if nx < 2 or ny < 2:
        raise ValueError("units must be at least (2, 2)")
    check_positive(thickness=thickness)
    p = S.BREADBOARD[system]["pitch"]
    bs = S.screw(S.BREADBOARD[system]["screw"])
    slot_d = bs.clearance(slot_fit)
    cb_d, cb_h = bs.cbore_d, bs.head_h + 0.5
    if thickness - cb_h < 4.0:
        raise ValueError(f"thickness leaves {thickness - cb_h:.1f} mm under the screw head; need >= 4 mm")
    W, H = nx * p, ny * p

    plate = rr_prism(W, H, corner_r, 0.0, thickness)
    if top_chamfer > 0:
        plate = chamfer(plate.edges().group_by(Axis.Z)[-1], top_chamfer)
    if bottom_chamfer > 0:
        plate = chamfer(plate.edges().group_by(Axis.Z)[0], bottom_chamfer)

    # slots: one row along each long edge, centred between two grid holes, one pitch of travel
    holes: list[HoleSpec] = []
    ys = (-H / 2 + p / 2, H / 2 - p / 2)
    xs = sorted({round(-W / 2 + p, 9), round(W / 2 - p, 9)})
    slot_cuts = None
    for y in ys:
        for x in xs:
            thru = Pos(x, y, -1) * extrude(SlotCenterToCenter(p, slot_d), thickness + 2)
            cb = Pos(x, y, thickness - cb_h) * extrude(SlotCenterToCenter(p, cb_d), cb_h + 1)
            cut = thru + cb
            slot_cuts = cut if slot_cuts is None else slot_cuts + cut
            for e in (-p / 2, p / 2):
                holes.append(HoleSpec(bs.name, slot_fit, (x + e, y, thickness / 2), label=f"slot end ({x + e:.2f}, {y:.2f})"))
    plate = plate - slot_cuts

    # device pattern, centred
    ds = S.screw(device_screw)
    dd = ds.clearance(device_fit) if device_hole_d is None else float(device_hole_d)
    dx, dy = device_pattern
    pts = sorted({(sx * dx / 2, sy * dy / 2) for sx in (-1, 1) for sy in (-1, 1)})
    nut_af = ds.nut_af + 0.3
    nut_r = nut_af / math.sqrt(3)              # circumradius of the hex pocket
    nut_h = ds.nut_h + 0.4
    feature_r = nut_r if nut_traps else dd / 2
    edge = 3.0
    for (x, y) in pts:
        if abs(x) + feature_r + edge > W / 2 or abs(y) + feature_r + edge > H / 2:
            raise ValueError(f"device hole at ({x}, {y}) is too close to the plate edge")
        for sy in ys:
            for sx in xs:
                along = max(0.0, abs(x - sx) - p / 2)          # distance to the slot's centre segment
                gap = math.hypot(along, y - sy) - cb_d / 2 - feature_r
                if gap < 2.0:
                    raise ValueError(f"device hole at ({x}, {y}) runs into a breadboard slot "
                                     f"({gap:.1f} mm apart); change device_pattern or units")
    dev = None
    for (x, y) in pts:
        c = Pos(x, y, -1) * extrude(Circle(dd / 2), thickness + 2)
        if nut_traps:
            c = c + Pos(x, y, -1) * extrude(RegularPolygon(nut_r, 6), nut_h + 1)
        dev = c if dev is None else dev + c
        holes.append(HoleSpec(ds.name, device_fit, (x, y, thickness / 2), label=f"device ({x:.1f}, {y:.1f})"))
    plate = plate - dev

    notes = [f"{system}: {bs.name} slots, pitch {p} mm, travel {p} mm; device {ds.name} {device_fit} on {dx} x {dy} mm"]
    if nut_traps:
        notes.append(f"{ds.name} hex nut traps from below, {nut_af:.1f} mm across flats, {nut_h:.1f} mm deep")
    return Fixture("breadboard_adapter", as_part(plate), {}, holes, notes)
