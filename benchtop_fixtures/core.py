"""Shared types and small geometry helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh
from build123d import (Circle, Location, Part, Pos, Rectangle, RectangleRounded, Solid, export_step,
                       export_stl, extrude)

# Tessellation used for STL export and for every mesh-based check.
MESH_TOL = 0.01          # mm, chordal deviation
MESH_ANG = 0.1           # rad


@dataclass
class HoleSpec:
    """A screw clearance hole the part promises to have. The checker measures it in the B-rep."""
    screw: str
    fit: str
    center: tuple[float, float, float]
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    label: str = ""


@dataclass
class Fixture:
    part: str
    shape: Part
    params: dict
    holes: list[HoleSpec] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def solid(self) -> Solid:
        solids = self.shape.solids()
        if len(solids) != 1:
            raise ValueError(f"{self.part}: expected one solid, got {len(solids)}")
        return solids[0]

    def mesh(self, tol: float = MESH_TOL, ang: float = MESH_ANG) -> trimesh.Trimesh:
        return to_mesh(self.shape, tol, ang)

    def export(self, folder: str | Path, name: str) -> tuple[Path, Path]:
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        step, stl = folder / f"{name}.step", folder / f"{name}.stl"
        export_step(self.shape, str(step))
        export_stl(self.shape, str(stl), tolerance=MESH_TOL, angular_tolerance=MESH_ANG)
        return step, stl


def to_mesh(shape, tol: float = MESH_TOL, ang: float = MESH_ANG) -> trimesh.Trimesh:
    return mesh_with_faces(shape, tol, ang)[0]


def mesh_with_faces(shape, tol: float = MESH_TOL, ang: float = MESH_ANG):
    """Tessellate the B-rep and keep, per triangle, the B-rep face it came from and its mean UV.

    Returns (mesh, faces, tri_face, tri_uv): `faces` is the list of TopoDS faces, `tri_face[i]`
    the index of triangle i's face, `tri_uv[i]` the (u, v) of its centroid on that face.
    """
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location

    BRepMesh_IncrementalMesh(shape.wrapped, tol, False, ang, True)
    verts, tris, tri_face, tri_uv, faces = [], [], [], [], []
    for f in shape.faces():
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f.wrapped, loc)
        if tri is None:
            continue
        fi = len(faces)
        faces.append(f.wrapped)
        trsf = loc.Transformation()
        rev = f.wrapped.Orientation() == TopAbs_REVERSED
        off = len(verts)
        uv = []
        for k in range(1, tri.NbNodes() + 1):
            p = tri.Node(k).Transformed(trsf)
            verts.append((p.X(), p.Y(), p.Z()))
            if tri.HasUVNodes():
                q = tri.UVNode(k)
                uv.append((q.X(), q.Y()))
            else:
                uv.append((np.nan, np.nan))
        uv = np.asarray(uv)
        for k in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(k).Get()
            if rev:
                b, c = c, b
            tris.append((off + a - 1, off + b - 1, off + c - 1))
            tri_face.append(fi)
            tri_uv.append(uv[[a - 1, b - 1, c - 1]].mean(axis=0))
    mesh = trimesh.Trimesh(np.asarray(verts, float), np.asarray(tris, np.int64), process=True, validate=False)
    if len(mesh.faces) != len(tri_face):
        raise RuntimeError("tessellation lost triangles while merging vertices")
    return mesh, faces, np.asarray(tri_face), np.asarray(tri_uv)


def exact_normal(face, u: float, v: float) -> np.ndarray:
    """Outward unit normal of a B-rep face at (u, v), honouring the face orientation."""
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.gp import gp_Pnt, gp_Vec

    p, n = gp_Pnt(), gp_Vec()
    BRepGProp_Face(face).Normal(u, v, p, n)
    m = n.Magnitude()
    return np.array([n.X(), n.Y(), n.Z()]) / m if m > 0 else np.zeros(3)


def rr_prism(w: float, h: float, r: float, z0: float, z1: float, x: float = 0.0, y: float = 0.0) -> Part:
    """Rounded-rectangle prism from z0 to z1, centred on (x, y)."""
    r = min(r, w / 2 - 1e-3, h / 2 - 1e-3)
    sk = RectangleRounded(w, h, r) if r > 1e-3 else Rectangle(w, h)
    return Pos(x, y, z0) * extrude(sk, z1 - z0)


def rr_face(w: float, h: float, r: float, z: float, x: float = 0.0, y: float = 0.0):
    r = min(r, w / 2 - 1e-3, h / 2 - 1e-3)
    return (Location((x, y, z)) * RectangleRounded(w, h, r)).faces()[0]


def circle_face(d: float, z: float, x: float = 0.0, y: float = 0.0):
    return (Location((x, y, z)) * Circle(d / 2)).faces()[0]


def as_part(shape) -> Part:
    """Normalise a build123d result to a Part holding exactly what it holds."""
    if isinstance(shape, Part):
        return shape
    return Part(shape.wrapped)


def check_positive(**kw):
    for k, v in kw.items():
        if v is None or v <= 0:
            raise ValueError(f"{k} must be > 0, got {v!r}")
