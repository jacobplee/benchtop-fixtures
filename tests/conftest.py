import functools
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchtop_fixtures import PRESETS, make  # noqa: E402
from benchtop_fixtures.check import check, concave_cylinders  # noqa: E402


@functools.lru_cache(maxsize=None)
def preset(name):
    return make(name)


@functools.lru_cache(maxsize=None)
def preset_report(name):
    return check(preset(name), name)


def holes_by_diameter(shape, d, tol=1e-6):
    """Axis points and directions of every concave cylinder of diameter d, measured on the B-rep."""
    return [(o, a) for dia, o, a in concave_cylinders(shape) if abs(dia - d) <= tol]


def cylinder_faces(shape, d, tol=1e-6):
    """B-rep cylindrical faces of diameter d (hole or boss)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    out = []
    for f in shape.faces():
        ad = BRepAdaptor_Surface(f.wrapped)
        if ad.GetType() == GeomAbs_Cylinder and abs(2 * ad.Cylinder().Radius() - d) <= tol:
            out.append(f)
    return out


@pytest.fixture(params=list(PRESETS))
def preset_name(request):
    return request.param


def is_multiple(x, step, tol=1e-6):
    k = np.round(x / step)
    return abs(x - k * step) <= tol
