"""Printability checker. Every exported part runs through `check()`.

    python -m benchtop_fixtures.check <part-or-preset> [--set key=value ...] [--min-wall 1.2]
                                      [--max-bridge 10] [--printer prusa_mk4 ...] [--json]

Exit code: 0 PASS, 1 FAIL, 2 FLAG.

Checks, all measured on the generated geometry (exact B-rep or its tessellation):

solid         one valid B-rep solid, volume > 0, the tessellation is watertight with consistent
              winding, and the mesh volume matches the B-rep within 0.5 %.
build_volume  the bounding box in the modeled orientation (bed at z = 0) fits each printer, with a
              90 degree turn about Z allowed. Diagonal placement is not tried, so the answer is
              conservative. Fails if a required printer does not fit.
min_wall      local wall thickness, sampled. Points are drawn uniformly by area over the surface
              (about one per mm^2, 4 000 to 60 000). From each point a ray is cast inward along the
              facet normal, starting just outside the surface, and intersected with the exact B-rep.
              The distance from entry to exit is the local thickness. Any sample thinner than
              min_wall - 0.05 mm fails the check. Acute knife edges therefore fail (correctly);
              rounded tips pass when their radius is at least min_wall / 2.
holes         every hole the part declares (screw, fit, axis) is looked up in the B-rep: the
              smallest concave cylinder coaxial with the declared axis within 0.01 mm is the
              clearance bore. Its diameter must equal the table value within 0.01 mm.
overhangs     approximate, FDM oriented. A facet overhangs when its normal points down more
              than the limit (45 degrees from vertical, plus 0.5 degrees for tessellation) and it is
              not on the bed. Facet angles come from the exact B-rep normal at each facet centroid,
              so a 45 degree chamfer reads 45.00, not its tessellated 45.6. Overhanging facets are
              grouped into connected regions. An edge of a region is supported when the face across
              it has material below the edge (a wall going down), and not when it goes up (an open
              side). The span is twice the largest distance from any point of the region to its
              nearest supported edge: a ceiling held on two sides L apart spans L, a disc held all
              round spans its diameter, a shelf held on one side spans twice its depth. A region whose
              facets are all within 2 degrees of horizontal and whose span is at most max_bridge is
              flagged as a bridge and accepted. Every other region is flagged as needing support and
              makes the verdict FLAG. Bridge quality depends on the printer and slicer; the default
              10 mm limit is conservative for an untuned FDM machine.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import sys
from dataclasses import dataclass, field

import numpy as np
import trimesh
import shapely
from shapely.geometry import MultiLineString, Polygon
from shapely.ops import polylabel, unary_union

from . import standards as S
from .core import Fixture, MESH_ANG, MESH_TOL, exact_normal, mesh_with_faces

MIN_WALL = 1.2
MAX_BRIDGE = 10.0
OVERHANG_DEG = 45.0
WALL_TOL = 0.05
HOLE_TOL = 0.01
OVERHANG_SLACK = 0.05
FLAT_DEG = 88.0
WALL_ALIGN = 0.5          # exit face within 60 deg of the ray: a wall or a taper under 60 deg, not a corner


@dataclass
class Result:
    status: str                      # "pass", "fail" or "flag"
    summary: str
    details: dict = field(default_factory=dict)


@dataclass
class Report:
    name: str
    results: dict[str, Result]
    info: dict

    @property
    def verdict(self) -> str:
        st = [r.status for r in self.results.values()]
        return "FAIL" if "fail" in st else "FLAG" if "flag" in st else "PASS"

    @property
    def ok(self) -> bool:
        return self.verdict == "PASS"

    def to_dict(self) -> dict:
        return dict(name=self.name, verdict=self.verdict, info=self.info,
                    checks={k: dict(status=v.status, summary=v.summary, **v.details) for k, v in self.results.items()})

    def text(self) -> str:
        lines = [f"{self.name}: {self.verdict}",
                 f"  size {self.info['size_mm'][0]:.1f} x {self.info['size_mm'][1]:.1f} x {self.info['size_mm'][2]:.1f} mm,"
                 f" volume {self.info['volume_cm3']:.1f} cm3"]
        for k, r in self.results.items():
            lines.append(f"  [{r.status.upper():4}] {k:13} {r.summary}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- solid
def check_solid(fx: Fixture, mesh: trimesh.Trimesh) -> Result:
    solids = fx.shape.solids()
    brep_vol = float(fx.shape.volume)
    d = dict(solids=len(solids), brep_valid=bool(fx.shape.is_valid), brep_volume=round(brep_vol, 3),
             watertight=bool(mesh.is_watertight), winding_consistent=bool(mesh.is_winding_consistent),
             mesh_volume=round(float(mesh.volume), 3))
    rel = abs(mesh.volume - brep_vol) / brep_vol if brep_vol > 0 else math.inf
    d["volume_rel_diff"] = float(f"{rel:.2e}")
    ok = (len(solids) == 1 and d["brep_valid"] and brep_vol > 0 and d["watertight"]
          and d["winding_consistent"] and rel < 0.005)
    s = (f"1 solid, valid, watertight, {brep_vol / 1000:.2f} cm3" if ok else
         f"solids={len(solids)} valid={d['brep_valid']} watertight={d['watertight']} vol_diff={rel:.2%}")
    return Result("pass" if ok else "fail", s, d)


# --------------------------------------------------------------------------- build volume
def fits(size, printer: S.Printer) -> bool:
    x, y, z = size
    return z <= printer.z and ((x <= printer.x and y <= printer.y) or (x <= printer.y and y <= printer.x))


def check_build_volume(size, required) -> Result:
    per = {}
    for key, p in S.PRINTERS.items():
        per[key] = dict(name=p.name, volume=[p.x, p.y, p.z], fits=fits(size, p))
    missing = [k for k in required if not per[k]["fits"]]
    ok = not missing
    fit_names = [per[k]["name"] for k in per if per[k]["fits"]]
    s = ("fits " + ", ".join(fit_names)) if ok else ("does not fit " + ", ".join(per[k]["name"] for k in missing))
    return Result("pass" if ok else "fail", s, dict(size_mm=[round(v, 3) for v in size], required=list(required), printers=per))


# --------------------------------------------------------------------------- minimum wall
def wall_samples(fx: Fixture, mesh: trimesh.Trimesh, density: float = 1.0, seed: int = 0,
                 lo: int = 4000, hi: int = 60000, eps: float = 0.05):
    """Local thickness at area-uniform surface samples.

    Returns (points, thickness, alignment). thickness is NaN where the ray missed. alignment is the
    cosine between the ray and the outward normal of the face it leaves through: 1 for a wall with
    parallel faces, cos(a) for a wedge of angle a.
    """
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

    n = int(np.clip(mesh.area * density, lo, hi))
    pts, fidx = trimesh.sample.sample_surface(mesh, n, seed=seed)
    nrm = mesh.face_normals[fidx]
    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(fx.shape.wrapped, 1e-7)
    th = np.full(n, np.nan)
    al = np.full(n, np.nan)
    for k in range(n):
        p, v = pts[k], nrm[k]
        o = p + v * eps
        inter.Perform(gp_Lin(gp_Pnt(*o), gp_Dir(*(-v))), 0.0, 1e5)
        m = inter.NbPnt()
        if m < 2:
            continue
        hits = sorted((inter.WParameter(i), i) for i in range(1, m + 1))
        u = [hits[0]]
        for h in hits[1:]:
            if h[0] - u[-1][0] > 1e-6:
                u.append(h)
        if len(u) < 2 or u[0][0] > 2 * eps + 0.03:
            continue
        th[k] = u[1][0] - u[0][0]
        if th[k] < 4.0:                         # only short rays need the exit normal
            i = u[1][1]
            ne = exact_normal(inter.Face(i), inter.UParameter(i), inter.VParameter(i))
            al[k] = float(np.dot(-v, ne))
    return pts, th, al


def check_min_wall(fx: Fixture, mesh: trimesh.Trimesh, min_wall: float, seed: int = 0) -> Result:
    pts, th, al = wall_samples(fx, mesh, seed=seed)
    good = ~np.isnan(th)
    if not good.any():
        return Result("fail", "no thickness samples", {})
    short = good & (th < (min_wall - WALL_TOL))
    wall_like = np.where(np.isnan(al), True, al >= WALL_ALIGN)
    thin = short & wall_like
    corner = short & ~wall_like
    walls = good & (wall_like | (th >= min_wall - WALL_TOL))
    t = th[walls]
    k = int(np.nanargmin(np.where(walls, th, np.nan)))
    d = dict(min_wall_required=min_wall, samples=int(good.sum()), missed=int((~good).sum()),
             min_mm=round(float(t.min()), 3), p1_mm=round(float(np.percentile(t, 1)), 3),
             median_mm=round(float(np.median(t)), 3), thin_samples=int(thin.sum()),
             corner_samples=int(corner.sum()), min_at=[round(float(c), 2) for c in pts[k]])
    if thin.any():
        d["thin_at"] = [[round(float(c), 2) for c in p] for p in pts[thin][:10]]
        return Result("fail", f"thinnest {t.min():.2f} mm < {min_wall} mm at {d['min_at']} ({int(thin.sum())} samples)", d)
    return Result("pass", f"thinnest {t.min():.2f} mm >= {min_wall} mm ({int(good.sum())} samples)", d)


# --------------------------------------------------------------------------- holes
def concave_cylinders(shape):
    """[(diameter, axis point, axis direction)] for every hole-like cylindrical face of the B-rep."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    out = []
    for f in shape.faces():
        ad = BRepAdaptor_Surface(f.wrapped)
        if ad.GetType() != GeomAbs_Cylinder:
            continue
        cyl = ad.Cylinder()
        ax = cyl.Axis()
        o = np.array([ax.Location().X(), ax.Location().Y(), ax.Location().Z()])
        a = np.array([ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()])
        p = f.position_at(0.5, 0.5)
        nrm = f.normal_at(p)
        p = np.array([p.X, p.Y, p.Z])
        radial = (p - o) - np.dot(p - o, a) * a
        if np.dot(radial, np.array([nrm.X, nrm.Y, nrm.Z])) < 0:      # normal points at the axis: a hole
            out.append((2 * cyl.Radius(), o, a))
    return out


def check_holes(fx: Fixture) -> Result:
    if not fx.holes:
        return Result("pass", "no screw holes declared", dict(holes=[]))
    cyls = concave_cylinders(fx.shape)
    rows, bad = [], 0
    for h in fx.holes:
        sc = S.screw(h.screw)
        want = sc.clearance(h.fit)
        c = np.asarray(h.center, float)
        a = np.asarray(h.axis, float)
        a = a / np.linalg.norm(a)
        found = []
        for dia, o, ax in cyls:
            if abs(abs(float(np.dot(ax, a))) - 1) > 1e-6:
                continue
            off = (c - o) - np.dot(c - o, ax) * ax
            if np.linalg.norm(off) <= HOLE_TOL:
                found.append(dia)
        got = min(found) if found else None
        ok = got is not None and abs(got - want) <= HOLE_TOL
        bad += not ok
        rows.append(dict(label=h.label, screw=h.screw, fit=h.fit, center=[round(v, 4) for v in h.center],
                         expected_mm=round(want, 4), measured_mm=None if got is None else round(got, 4), ok=ok))
    if bad:
        first = next(r for r in rows if not r["ok"])
        why = "not found" if first["measured_mm"] is None else f"{first['measured_mm']} mm, table {first['expected_mm']} mm"
        return Result("fail", f"{bad} of {len(rows)} holes off the table ({first['screw']} {first['fit']} {first['label']}: {why})",
                      dict(holes=rows))
    kinds = sorted({f"{r['screw']} {r['fit']}" for r in rows})
    return Result("pass", f"{len(rows)} holes match the table ({', '.join(kinds)})", dict(holes=rows))


# --------------------------------------------------------------------------- overhangs
def _probes(tris: np.ndarray, max_points: int = 20000) -> np.ndarray:
    """XY points covering a region: its vertices, its densified outline and a grid inside it."""
    polys = [Polygon(t[:, :2]) for t in tris]
    outline = unary_union([p for p in polys if p.area > 1e-10])
    h = max(0.1, math.sqrt(max(outline.area, 1e-9) / max_points))
    x0, y0, x1, y1 = outline.bounds
    gx, gy = np.meshgrid(np.arange(x0, x1 + h, h), np.arange(y0, y1 + h, h))
    gx, gy = gx.ravel(), gy.ravel()
    inside = shapely.contains_xy(outline, gx, gy)
    edge = shapely.get_coordinates(shapely.segmentize(outline.boundary, h))
    poles = [polylabel(Polygon(g.exterior), tolerance=0.005).coords[0] for g in getattr(outline, "geoms", [outline])]
    return np.vstack([tris.reshape(-1, 3)[:, :2], edge, np.column_stack([gx[inside], gy[inside]]), np.asarray(poles)])


def overhang_regions(mesh: trimesh.Trimesh, faces, tri_face, tri_uv, limit_deg: float = OVERHANG_DEG,
                     max_bridge: float = MAX_BRIDGE):
    fn = mesh.face_normals
    cand = np.nonzero(fn[:, 2] < -math.sin(math.radians(limit_deg - 5.0)))[0]
    if cand.size == 0:
        return []
    nz = np.zeros(len(fn))
    for i in cand:                                     # exact B-rep normal at each candidate's centroid
        u, v = tri_uv[i]
        nz[i] = exact_normal(faces[tri_face[i]], u, v)[2] if np.isfinite(u) else fn[i, 2]
    zmin = mesh.bounds[0][2]
    tri_z = mesh.vertices[mesh.faces][:, :, 2]
    on_bed = (tri_z <= zmin + 1e-3).all(axis=1)
    over = np.zeros(len(fn), bool)
    over[cand] = nz[cand] < -math.sin(math.radians(limit_deg + OVERHANG_SLACK))
    over &= ~on_bed
    idx = np.nonzero(over)[0]
    if idx.size == 0:
        return []
    sel = np.zeros(len(fn), bool)
    sel[idx] = True
    fa, fe = mesh.face_adjacency, mesh.face_adjacency_edges
    inner = sel[fa[:, 0]] & sel[fa[:, 1]]
    comps = trimesh.graph.connected_components(fa[inner], nodes=idx, min_len=1)
    region_of = np.full(len(fn), -1)
    for r, comp in enumerate(comps):
        region_of[list(comp)] = r
    # boundary edges of each region, and whether the face across the edge has material below it
    border = sel[fa[:, 0]] ^ sel[fa[:, 1]]
    supported = {r: [] for r in range(len(comps))}
    for (a, b), e in zip(fa[border], fe[border]):
        mine, other = (a, b) if sel[a] else (b, a)
        z_edge = mesh.vertices[e][:, 2].mean()
        if tri_z[other].min() < z_edge - 1e-4:
            supported[region_of[mine]].append(mesh.vertices[e][:, :2])
    regions = []
    for r, comp in enumerate(comps):
        comp = np.asarray(sorted(comp))
        ang = np.degrees(np.arcsin(np.clip(-nz[comp], -1, 1)))
        tris = mesh.vertices[mesh.faces[comp]]
        if supported[r]:
            sup = MultiLineString([tuple(map(tuple, seg)) for seg in supported[r]])
            span = 2 * float(shapely.distance(sup, shapely.points(_probes(tris))).max())
        else:
            span = math.inf
        flat = bool(ang.min() >= FLAT_DEG)
        kind = "bridge" if flat and span <= max_bridge + 0.05 else "support"
        regions.append(dict(kind=kind, flat=flat, area_mm2=round(float(mesh.area_faces[comp].sum()), 2),
                            span_mm=None if math.isinf(span) else round(span, 2),
                            max_angle_deg=round(float(ang.max()), 1),
                            z_mm=[round(float(tris[:, :, 2].min()), 2), round(float(tris[:, :, 2].max()), 2)],
                            centre=[round(float(v), 2) for v in tris.reshape(-1, 3).mean(axis=0)]))
    return regions


def check_overhangs(mesh: trimesh.Trimesh, faces, tri_face, tri_uv, limit_deg: float, max_bridge: float) -> Result:
    regions = overhang_regions(mesh, faces, tri_face, tri_uv, limit_deg, max_bridge)
    bridges = [r for r in regions if r["kind"] == "bridge"]
    support = [r for r in regions if r["kind"] == "support"]
    d = dict(limit_deg=limit_deg, max_bridge_mm=max_bridge, bridges=bridges, needs_support=support)
    if support:
        worst = max(support, key=lambda r: r["area_mm2"])
        return Result("flag", f"{len(support)} region(s) need support or a new orientation "
                              f"(largest {worst['area_mm2']} mm2 at z {worst['z_mm'][0]}, up to {worst['max_angle_deg']} deg)", d)
    if bridges:
        span = max(r["span_mm"] for r in bridges)
        return Result("pass", f"{len(bridges)} flat bridge(s) flagged, longest span {span:.1f} mm <= {max_bridge:g}; "
                              f"nothing else past {limit_deg:g} deg", d)
    return Result("pass", f"none past {limit_deg:g} deg", d)


# --------------------------------------------------------------------------- driver
def check(fx: Fixture, name: str | None = None, *, min_wall: float = MIN_WALL, max_bridge: float = MAX_BRIDGE,
          overhang_deg: float = OVERHANG_DEG, printers=None, seed: int = 0) -> Report:
    printers = tuple(S.PRINTERS) if printers is None else tuple(printers)
    for p in printers:
        if p not in S.PRINTERS:
            raise ValueError(f"unknown printer {p!r}; known: {sorted(S.PRINTERS)}")
    mesh, faces, tri_face, tri_uv = mesh_with_faces(fx.shape, MESH_TOL, MESH_ANG)
    bb = fx.shape.bounding_box()
    size = (bb.size.X, bb.size.Y, bb.size.Z)
    res = {
        "solid": check_solid(fx, mesh),
        "build_volume": check_build_volume(size, printers),
        "min_wall": check_min_wall(fx, mesh, min_wall, seed=seed),
        "holes": check_holes(fx),
        "overhangs": check_overhangs(mesh, faces, tri_face, tri_uv, overhang_deg, max_bridge),
    }
    info = dict(part=fx.part, size_mm=[round(v, 3) for v in size], volume_cm3=round(fx.shape.volume / 1000, 3),
                bed_z=round(bb.min.Z, 6), params=jsonable(fx.params), notes=fx.notes)
    return Report(name or fx.part, res, info)


def jsonable(x):
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    return x


def parse_value(text: str):
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text


def main(argv=None) -> int:
    from . import PARTS, PRESETS, make

    ap = argparse.ArgumentParser(prog="python -m benchtop_fixtures.check", description=__doc__.split("\n\n")[0])
    ap.add_argument("name", help=f"part or preset: {', '.join(sorted(set(PARTS) | set(PRESETS)))}")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a parameter (Python literal)")
    ap.add_argument("--min-wall", type=float, default=MIN_WALL)
    ap.add_argument("--max-bridge", type=float, default=MAX_BRIDGE)
    ap.add_argument("--overhang", type=float, default=OVERHANG_DEG)
    ap.add_argument("--printer", action="append", choices=sorted(S.PRINTERS), help="required printer(s); default all")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    ap.add_argument("--export", metavar="DIR", help="also write <name>.step and <name>.stl to DIR")
    a = ap.parse_args(argv)
    overrides = {}
    for kv in a.set:
        if "=" not in kv:
            ap.error(f"--set expects KEY=VALUE, got {kv!r}")
        k, v = kv.split("=", 1)
        overrides[k.strip()] = parse_value(v.strip())
    fx = make(a.name, **overrides)
    rep = check(fx, a.name, min_wall=a.min_wall, max_bridge=a.max_bridge, overhang_deg=a.overhang, printers=a.printer)
    print(json.dumps(rep.to_dict(), indent=1) if a.json else rep.text())
    if a.export:
        for p in fx.export(a.export, a.name):
            print(f"  wrote {p}")
    return {"PASS": 0, "FAIL": 1, "FLAG": 2}[rep.verdict]


if __name__ == "__main__":
    sys.exit(main())
