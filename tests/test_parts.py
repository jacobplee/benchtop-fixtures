"""Every preset: one valid solid, positive volume, watertight, on the bed, and checker PASS."""
import json
import math

import pytest
import trimesh
from build123d import import_step

from benchtop_fixtures import PARTS, PRESETS, make
from conftest import ROOT, preset, preset_report

EXPORTS = ROOT / "exports"


def test_every_part_has_a_preset():
    assert {p for p, _ in PRESETS.values()} == set(PARTS)


def test_solid_and_volume(preset_name):
    fx = preset(preset_name)
    assert len(fx.shape.solids()) == 1
    assert fx.shape.is_valid
    assert fx.shape.volume > 0


def test_watertight_mesh(preset_name):
    m = preset(preset_name).mesh()
    assert m.is_watertight and m.is_winding_consistent and m.is_volume
    assert m.volume == pytest.approx(preset(preset_name).shape.volume, rel=5e-3)


def test_modeled_on_the_bed(preset_name):
    bb = preset(preset_name).shape.bounding_box()
    assert bb.min.Z == pytest.approx(0.0, abs=1e-6)


def test_checker_passes_every_preset(preset_name):
    rep = preset_report(preset_name)
    assert rep.verdict == "PASS", rep.text()


def test_unknown_parameter_is_rejected():
    with pytest.raises(TypeError):
        make("cable_clip", diameter=6)


# ------------------------------------------------------------------ exported files (D1, D2)
def test_report_lists_every_preset():
    rep = json.loads((EXPORTS / "report.json").read_text())
    assert list(rep["presets"]) == list(PRESETS)
    assert all(v["verdict"] == "PASS" for v in rep["presets"].values())


@pytest.mark.parametrize("name", list(PRESETS))
def test_exported_stl_is_watertight_and_current(name):
    m = trimesh.load(EXPORTS / f"{name}.stl", force="mesh")
    assert m.is_watertight and m.is_winding_consistent
    # stale-export guard: the committed STL must match the geometry the code builds today
    assert m.volume == pytest.approx(preset(name).shape.volume, rel=5e-3)


@pytest.mark.parametrize("name", list(PRESETS))
def test_exported_step_reimports_as_one_solid(name):
    s = import_step(str(EXPORTS / f"{name}.step"))
    solids = s.solids()
    assert len(solids) == 1
    assert solids[0].volume == pytest.approx(preset(name).shape.volume, rel=1e-3)
    assert not math.isnan(solids[0].volume)
