"""Public reference numbers used by the parts and the checker, each with its source.

Units are millimetres unless a name says otherwise. Inch values are converted once, here.
"""
from __future__ import annotations

from dataclasses import dataclass

INCH = 25.4

# --------------------------------------------------------------------------- screws
#
# Clearance holes, close and normal fit:
#   metric: ASME B18.2.8-1999 metric table (same values as ISO 273 fine / medium series)
#   inch:   ASME B18.2.8-1999 inch table, smallest drill in each class
#           (#8: close #15 drill 0.180 in, normal #9 drill 0.196 in;
#            1/4: close 17/64 in = 0.2656 in, normal 9/32 in = 0.28125 in)
# Socket head cap screw heads: ISO 4762 (metric), ASME B18.3 (inch).
# Hex nuts: ISO 4032 (metric), ASME B18.6.3 machine screw nut (#8), ASME B18.2.2 (1/4).
# Counterbore diameters are the common practice of head diameter plus about 1 mm
# (Machinery's Handbook lists 5/16 in for #8 and 7/16 in for 1/4 socket heads).


@dataclass(frozen=True)
class Screw:
    name: str
    nominal: float          # major diameter
    close: float            # close-fit clearance hole
    normal: float           # normal-fit clearance hole
    head_d: float           # socket head diameter
    head_h: float           # socket head height
    cbore_d: float          # counterbore diameter for the socket head
    nut_af: float           # hex nut width across flats
    nut_h: float            # hex nut thickness

    def clearance(self, fit: str) -> float:
        if fit not in FITS:
            raise ValueError(f"fit must be one of {FITS}, got {fit!r}")
        return getattr(self, fit)


FITS = ("close", "normal")

SCREWS: dict[str, Screw] = {
    "M3": Screw("M3", 3.0, 3.2, 3.4, 5.5, 3.0, 6.5, 5.5, 2.4),
    "M4": Screw("M4", 4.0, 4.3, 4.5, 7.0, 4.0, 8.0, 7.0, 3.2),
    "M6": Screw("M6", 6.0, 6.4, 6.6, 10.0, 6.0, 11.0, 10.0, 5.2),
    "#8": Screw("#8", 0.164 * INCH, 0.180 * INCH, 0.196 * INCH,
                0.270 * INCH, 0.164 * INCH, 0.3125 * INCH, 0.34375 * INCH, 0.125 * INCH),
    "1/4-20": Screw("1/4-20", 0.250 * INCH, (17 / 64) * INCH, (9 / 32) * INCH,
                    0.375 * INCH, 0.250 * INCH, (7 / 16) * INCH, (7 / 16) * INCH, (7 / 32) * INCH),
}


def screw(name: str) -> Screw:
    try:
        return SCREWS[name]
    except KeyError:
        raise ValueError(f"unknown screw {name!r}; the table has {sorted(SCREWS)}") from None


# --------------------------------------------------------------------------- optical breadboards
# Industry convention for optical tables and breadboards: 1/4-20 tapped holes on a 1 in grid
# (imperial) or M6 tapped holes on a 25 mm grid (metric).
BREADBOARD = {
    "imperial": dict(pitch=1.0 * INCH, screw="1/4-20"),
    "metric": dict(pitch=25.0, screw="M6"),
}

# --------------------------------------------------------------------------- Gridfinity
# Gridfinity is the open modular storage system created by Zack Freedman. There is no single
# formal standard document; the numbers below are the community specification as encoded in
# kennetek/gridfinity-rebuilt-openscad, file src/core/standard.scad (MIT licence), which itself
# cites https://gridfinity.xyz/specification/ . Checked against that file on 2026-11-02.
GF_PITCH = 42.0                      # GRID_DIMENSIONS_MM
GF_UNIT_H = 7.0                      # fromGridfinityUnits(): 1 unit = 7 mm, base included, lip excluded
GF_GAP = 0.5                         # BASE_GAP_MM = 42 - 41.5
GF_TOP = 41.5                        # BASE_TOP_DIMENSIONS
GF_TOP_R = 7.5 / 2                   # BASE_TOP_RADIUS
GF_PROFILE = ((0.0, 0.0), (0.8, 0.8), (0.8, 2.6), (2.95, 4.75))   # BASE_PROFILE (inset-out, z)
GF_PROFILE_H = 4.75                  # 0.8 + 1.8 + 2.15
GF_BASE_H = 7.0                      # BASE_HEIGHT (profile plus the bridge tying the feet together)
GF_BOTTOM = GF_TOP - 2 * 2.95        # 35.6, base_bottom_dimensions()
GF_BOTTOM_R = GF_TOP_R - 2.95        # 0.8, BASE_BOTTOM_RADIUS
GF_LIP = ((0.0, 0.0), (0.7, 0.7), (0.7, 2.5), (2.6, 4.4))         # STACKING_LIP_LINE
GF_LIP_DEPTH = 2.6                   # STACKING_LIP_SIZE.x
GF_LIP_H = 4.4                       # STACKING_LIP_SIZE.y
GF_LIP_FILLET = 0.6                  # STACKING_LIP_FILLET_RADIUS
GF_LIP_SUPPORT_H = 1.2               # STACKING_LIP_SUPPORT_HEIGHT
GF_FLOOR_FILLET = 2.8                # r_f2, internal fillet radius
GF_MAGNET = (6.0, 2.0)               # gridfinity.xyz: 6 mm x 2 mm magnets (not used by the bin yet)

# --------------------------------------------------------------------------- printers
@dataclass(frozen=True)
class Printer:
    key: str
    name: str
    x: float
    y: float
    z: float


# Build volumes from the manufacturers' published specifications.
PRINTERS: dict[str, Printer] = {
    "prusa_mk4": Printer("prusa_mk4", "Prusa MK4", 250.0, 210.0, 220.0),
    "bambu_x1c": Printer("bambu_x1c", "Bambu Lab X1C", 256.0, 256.0, 256.0),
    "form3": Printer("form3", "Formlabs Form 3", 145.0, 145.0, 185.0),
}
