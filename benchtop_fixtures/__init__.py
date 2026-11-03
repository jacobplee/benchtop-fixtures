"""benchtop-fixtures: parametric 3D-printable bench fixtures in build123d, with a printability checker."""
from __future__ import annotations

import inspect

from .core import Fixture, HoleSpec
from .parts.breadboard import breadboard_adapter
from .parts.clip import cable_clip
from .parts.cradle import tube_cradle
from .parts.gridfinity import gridfinity_bin
from .parts.riser import instrument_riser

__version__ = "0.1.0"

PARTS = {
    "breadboard_adapter": breadboard_adapter,
    "gridfinity_bin": gridfinity_bin,
    "tube_cradle": tube_cradle,
    "cable_clip": cable_clip,
    "instrument_riser": instrument_riser,
}

# Named configurations. Every preset is exported, checked and tested.
PRESETS: dict[str, tuple[str, dict]] = {
    "breadboard_adapter": ("breadboard_adapter", {}),
    "breadboard_adapter_metric": ("breadboard_adapter", dict(system="metric")),
    "gridfinity_bin": ("gridfinity_bin", {}),
    "gridfinity_bin_cylinder_pocket": ("gridfinity_bin", dict(cells_x=1, cells_y=1, units=6, pocket="cylinder",
                                                               pocket_d=30.0, pocket_depth=30.0)),
    "gridfinity_bin_box_pocket": ("gridfinity_bin", dict(pocket="box", pocket_size=(70.0, 28.0), pocket_r=3.0,
                                                          pocket_depth=10.0)),
    "tube_cradle": ("tube_cradle", {}),
    "cable_clip": ("cable_clip", {}),
    "cable_clip_screw": ("cable_clip", dict(style="screw", od=10.0)),
    "instrument_riser": ("instrument_riser", {}),
    "instrument_riser_square": ("instrument_riser", dict(shape="square", size=60.0, height=40.0)),
}


def make(name: str, **overrides) -> Fixture:
    """Build a part or preset by name, with parameter overrides. `params` holds every parameter."""
    if name in PRESETS:
        part, params = PRESETS[name]
        params = {**params, **overrides}
    elif name in PARTS:
        part, params = name, dict(overrides)
    else:
        raise KeyError(f"unknown part or preset {name!r}; known: {sorted(set(PARTS) | set(PRESETS))}")
    fn = PARTS[part]
    sig = inspect.signature(fn)
    unknown = set(params) - set(sig.parameters)
    if unknown:
        raise TypeError(f"{part}: unknown parameter(s) {sorted(unknown)}; accepts {list(sig.parameters)}")
    bound = sig.bind(**params)
    bound.apply_defaults()
    fx = fn(**bound.arguments)
    fx.params = dict(bound.arguments)
    return fx


__all__ = ["Fixture", "HoleSpec", "PARTS", "PRESETS", "make", *PARTS]
