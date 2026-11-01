"""Reusable helpers for parametric 3D-print parts.

Modelling with manifold3d (booleans, hulls), checks and export with trimesh,
previews and sections with matplotlib. Units are millimetres throughout.
"""

from __future__ import annotations

import json
import math
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import Manifold

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

SEGMENTS = 64

# Fit clearances per side that printed true on an FDM printer (BP-SCL6 box, Oct 2026).
FDM_FIT = {"pin": 0.10, "pocket": 0.25, "slide": 0.20, "rib_proud": 0.25}
# Print services (MJF/SLS nylon) need more room and no crush ribs.
SERVICE_FIT = {"pin": 0.25, "pocket": 0.30, "slide": 0.30, "rib_proud": 0.0}


# ---------------------------------------------------------------- primitives

def box(x0, x1, y0, y1, z0, z1) -> Manifold:
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def cyl(axis: str, center, r: float, length: float, r2: float | None = None,
        segments: int = SEGMENTS) -> Manifold:
    """Cylinder (or cone with r2) centred on `center` along axis 'x', 'y' or 'z'."""
    c = Manifold.cylinder(length, r, r if r2 is None else r2, segments, True)
    if axis == "x":
        c = c.rotate((0, 90, 0))
    elif axis == "y":
        c = c.rotate((-90, 0, 0))
    return c.translate(tuple(center))


def sphere(center, r: float, segments: int = SEGMENTS) -> Manifold:
    return Manifold.sphere(r, segments).translate(tuple(center))


def hull(*parts: Manifold) -> Manifold:
    return Manifold.batch_hull(list(parts))


def hull_points(points) -> Manifold:
    return Manifold.hull_points(np.asarray(points, dtype=float))


def arc(center2d, r: float, a0: float, a1: float, n: int = 16):
    """Points on a circular arc in a plane, angles in degrees."""
    a = np.radians(np.linspace(a0, a1, n))
    return [(center2d[0] + r * math.cos(t), center2d[1] + r * math.sin(t)) for t in a]


def inset_polygon(poly, d: float):
    """Move every edge of a convex 2D polygon inwards by d (outwards if d < 0)."""
    p = np.asarray(poly, dtype=float)
    area = 0.5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])
    if area < 0:
        p = p[::-1]
    n = len(p)
    lines = []
    for i in range(n):
        a, b = p[i], p[(i + 1) % n]
        t = (b - a) / np.linalg.norm(b - a)
        inward = np.array([-t[1], t[0]])          # left of the edge for CCW
        lines.append((a + inward * d, t))
    out = []
    for i in range(n):
        (p1, t1), (p2, t2) = lines[i - 1], lines[i]
        m = np.array([t1, -t2]).T
        s = np.linalg.solve(m, p2 - p1)
        out.append(p1 + t1 * s[0])
    return out


def rounded_hull(points, r: float, segments: int = 16) -> Manifold:
    """Hull of spheres of radius r at the given (already inset) 3D points.

    Gives a convex solid with every edge rounded by r. Build parts from such
    convex pieces instead of rounding afterwards: Minkowski opening in
    manifold3d produced broken meshes (genus 72, millions of degenerate faces)."""
    s = Manifold.sphere(r, segments)
    return Manifold.batch_hull([s.translate(tuple(p)) for p in points])


# ---------------------------------------------------------------- conversion

def to_trimesh(m: Manifold) -> trimesh.Trimesh:
    mesh = m.to_mesh()
    return trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3],
                           np.asarray(mesh.tri_verts), process=True)


def drop_to_bed(m: Manifold) -> Manifold:
    """Move a part so it rests on z=0, centred on x/y."""
    x0, y0, z0, x1, y1, z1 = m.bounding_box()
    return m.translate((-(x0 + x1) / 2, -(y0 + y1) / 2, -z0))


# ---------------------------------------------------------------- checks

@dataclass
class Report:
    name: str
    results: list = field(default_factory=list)

    def add(self, check: str, ok: bool, detail: str, value=None):
        self.results.append({"check": check, "ok": bool(ok), "detail": detail,
                             "value": value})
        return ok

    @property
    def ok(self) -> bool:
        return all(r["ok"] for r in self.results)

    def print(self):
        print(f"\n== Checks: {self.name} ==")
        for r in self.results:
            print(f"  [{'OK ' if r['ok'] else 'FAIL'}] {r['check']}: {r['detail']}")
        print(f"  => {'ALL OK' if self.ok else 'FAILURES'}")

    def save(self, path: Path):
        path.write_text(json.dumps({"name": self.name, "ok": self.ok,
                                    "results": self.results}, indent=2))


def check_solid(rep: Report, m: Manifold, label: str = "part"):
    t = to_trimesh(m)
    bodies = len(m.decompose())
    rep.add(f"{label} watertight", t.is_watertight, f"watertight={t.is_watertight}")
    rep.add(f"{label} one piece", bodies == 1, f"{bodies} body/bodies")
    x0, y0, z0, x1, y1, z1 = m.bounding_box()
    rep.add(f"{label} size", True,
            f"{x1 - x0:.2f} x {y1 - y0:.2f} x {z1 - z0:.2f} mm, "
            f"{m.volume() / 1000:.2f} cm3", [x1 - x0, y1 - y0, z1 - z0])
    return t


def check_no_overlap(rep: Report, a: Manifold, b: Manifold, label: str,
                     allowed_mm3: float = 0.0):
    """Intersection volume of two solids must stay below `allowed_mm3`."""
    v = (a ^ b).volume()
    return rep.add(label, v <= allowed_mm3 + 1e-6,
                   f"overlap {v:.2f} mm3 (allowed {allowed_mm3:.2f})", v)


def check_gap(rep: Report, a: Manifold, b: Manifold, label: str, min_mm: float):
    """Smallest distance between two solids must be at least `min_mm`."""
    g = a.min_gap(b, min_mm * 4 + 1)
    return rep.add(label, g >= min_mm - 1e-6, f"min gap {g:.2f} mm (need {min_mm})", g)


def check_keepout(rep: Report, part: Manifold, zones: dict[str, Manifold]):
    for name, z in zones.items():
        check_no_overlap(rep, part, z, f"keep-out: {name}")


def wall_thickness(mesh: trimesh.Trimesh, samples: int = 6000, seed: int = 1):
    """Sample surface points, cast a ray inwards, return (points, thickness)."""
    pts, fi = trimesh.sample.sample_surface_even(mesh, samples, seed=seed)
    normals = mesh.face_normals[fi]
    origins = pts - normals * 1e-3
    locs, ray_idx, _ = mesh.ray.intersects_location(origins, -normals,
                                                    multiple_hits=False)
    th = np.full(len(pts), np.inf)
    d = np.linalg.norm(locs - origins[ray_idx], axis=1)
    np.minimum.at(th, ray_idx, d)
    return pts, th


def check_wall_thickness(rep: Report, mesh: trimesh.Trimesh, min_mm: float,
                         samples: int = 6000, ignore_frac: float = 0.002):
    """Fail if more than `ignore_frac` of sampled points are thinner than min_mm.

    A tiny fraction is ignored because samples right at sharp edges see
    the neighbouring face and report near-zero distances."""
    pts, th = wall_thickness(mesh, samples)
    finite = th[np.isfinite(th)]
    thin = finite < min_mm
    frac = thin.mean() if len(finite) else 0.0
    where = ""
    if thin.any():
        p = pts[np.isfinite(th)][thin]
        where = f", thin spots around {np.round(p.mean(axis=0), 1).tolist()}"
    rep.add("wall thickness", frac <= ignore_frac,
            f"p1={np.percentile(finite, 1):.2f} mm, p5={np.percentile(finite, 5):.2f} mm, "
            f"{frac * 100:.2f}% below {min_mm} mm{where}",
            {"p1": float(np.percentile(finite, 1)), "frac_thin": float(frac)})
    return pts, th


def check_overhangs(rep: Report, mesh: trimesh.Trimesh, max_angle: float = 45.0,
                    bed_tol: float = 0.2, allowed_mm2: float = 5.0):
    """Area of downward faces steeper than max_angle (from vertical), not on the bed.

    The mesh must already be in print orientation (z up, bed at z=0)."""
    n = mesh.face_normals
    # angle between face normal and straight down
    down = n[:, 2] < -math.cos(math.radians(90 - max_angle)) - 1e-6
    centers = mesh.triangles_center
    on_bed = centers[:, 2] < mesh.bounds[0][2] + bed_tol
    bad = down & ~on_bed
    area = mesh.area_faces[bad].sum()
    where = ""
    if bad.any():
        where = f", around {np.round(centers[bad].mean(axis=0), 1).tolist()}"
    return rep.add("overhangs", area <= allowed_mm2,
                   f"{area:.1f} mm2 steeper than {max_angle} deg (allowed "
                   f"{allowed_mm2}){where}", float(area))


# ---------------------------------------------------------------- export

def export_parts(parts: dict[str, Manifold], outdir: Path, basename: str,
                 spacing: float = 10.0) -> dict[str, str]:
    """Write one STL per part and a 3MF with all parts side by side on the bed.

    Parts must already be in print orientation. Returns file -> sha256."""
    outdir.mkdir(parents=True, exist_ok=True)
    scene = trimesh.Scene()
    hashes = {}
    x_cursor = 0.0
    for name, m in parts.items():
        t = to_trimesh(drop_to_bed(m))
        stl = outdir / f"{basename}_{name}.stl"
        t.export(stl)
        hashes[stl.name] = _sha256(stl)
        w = t.bounds[1][0] - t.bounds[0][0]
        placed = t.copy()
        placed.apply_translation((x_cursor - t.bounds[0][0], 0, 0))
        scene.add_geometry(placed, node_name=name, geom_name=name)
        x_cursor += w + spacing
    mf = outdir / f"{basename}.3mf"
    scene.export(mf, file_type="3mf")
    back = trimesh.load(mf, file_type="3mf")
    n_back = len(back.geometry) if isinstance(back, trimesh.Scene) else 1
    assert n_back == len(parts), f"3MF read-back has {n_back} objects"
    hashes[mf.name] = _sha256(mf)
    return hashes


def _sha256(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------- pictures

def _shade(tris, light=(0.4, -0.6, 0.7), base=(0.30, 0.55, 0.85)):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    lv = np.asarray(light) / np.linalg.norm(light)
    k = 0.35 + 0.65 * np.clip(n @ lv, 0, 1)
    return np.clip(np.outer(k, base), 0, 1)


def render_views(objects: list[tuple[trimesh.Trimesh, tuple, float]], path: Path,
                 views: list[tuple[str, float, float]], title: str = ""):
    """Shaded 3D views. objects: (mesh, rgb, alpha); views: (label, elev, azim)."""
    allpts = np.vstack([o[0].vertices for o in objects])
    lo, hi = allpts.min(0), allpts.max(0)
    mid, span = (lo + hi) / 2, (hi - lo).max() / 2
    fig = plt.figure(figsize=(5 * len(views), 5.2))
    for i, (label, elev, azim) in enumerate(views):
        ax = fig.add_subplot(1, len(views), i + 1, projection="3d")
        for mesh, rgb, alpha in objects:
            tris = mesh.triangles
            pc = Poly3DCollection(tris, facecolors=_shade(tris, base=rgb),
                                  edgecolors="none", alpha=alpha)
            ax.add_collection3d(pc)
        for setlim, k in ((ax.set_xlim, 0), (ax.set_ylim, 1), (ax.set_zlim, 2)):
            setlim(mid[k] - span, mid[k] + span)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev, azim)
        ax.set_title(label)
        ax.set_axis_off()
    if title:
        fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


OPENSCAD = (os.environ.get("OPENSCAD") or shutil.which("openscad")
            or "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD")


def render_openscad(objects: list[tuple[str, trimesh.Trimesh, tuple]], outdir: Path,
                    views: list[tuple[str, str, tuple, list[str]]],
                    sheet: Path | None = None, title: str = ""):
    """Proper shaded renders via the local OpenSCAD.

    objects: (name, mesh, rgb); views: (label, file, camera, object names) with
    camera = (tx, ty, tz, rx, ry, rz, dist). Optionally tiles all views into one
    sheet. Returns the list of written PNGs."""
    import subprocess
    outdir.mkdir(parents=True, exist_ok=True)
    for name, mesh, _ in objects:
        mesh.export(outdir / f"{name}.stl")
    colors = {name: rgb for name, _, rgb in objects}
    pngs = []
    for label, fname, cam, names in views:
        scad = outdir / f"{Path(fname).stem}.scad"
        scad.write_text("".join(
            f'color([{",".join(str(c) for c in colors[n])}]) import("{n}.stl");\n'
            for n in names))
        png = outdir / fname
        subprocess.run([OPENSCAD, "-o", str(png), "--imgsize=1600,1200",
                        "--colorscheme=Tomorrow", "--render", "--projection=p",
                        "--camera=" + ",".join(str(v) for v in cam), str(scad)],
                       check=True, capture_output=True)
        pngs.append((label, png))
    if sheet:
        import matplotlib.image as mpimg
        cols = 2
        rows = math.ceil(len(pngs) / cols)
        fig, axes = plt.subplots(rows, cols, figsize=(8 * cols, 6 * rows))
        for ax in np.atleast_1d(axes).flat:
            ax.axis("off")
        for ax, (label, png) in zip(np.atleast_1d(axes).flat, pngs):
            ax.imshow(mpimg.imread(png))
            ax.set_title(label, fontsize=14)
        if title:
            fig.suptitle(title, fontsize=16)
        fig.tight_layout()
        fig.savefig(sheet, dpi=100)
        plt.close(fig)
    return [p for _, p in pngs]


def _section_segments(mesh: trimesh.Trimesh, axis: int, value: float):
    normal = np.zeros(3)
    normal[axis] = 1
    origin = np.zeros(3)
    origin[axis] = value
    return trimesh.intersections.mesh_plane(mesh, normal, origin)


def plot_sections(sections: list[dict], path: Path, title: str = ""):
    """Planar cuts with dimension notes.

    Each section: {"label", "axis": 0|1|2, "value", "u": axis, "v": axis,
    "objects": [(mesh, color, linestyle)], "dims": [((u0,v0),(u1,v1),text)],
    "notes": [((u,v), text)]}"""
    fig, axes = plt.subplots(1, len(sections), figsize=(6 * len(sections), 6))
    axes = np.atleast_1d(axes)
    for ax, s in zip(axes, sections):
        for mesh, color, ls in s["objects"]:
            seg = _section_segments(mesh, s["axis"], s["value"])
            for a, b in seg:
                ax.plot([a[s["u"]], b[s["u"]]], [a[s["v"]], b[s["v"]]],
                        color=color, ls=ls, lw=1.4)
        for (p0, p1, text) in s.get("dims", []):
            ax.annotate("", p0, p1, arrowprops=dict(arrowstyle="<->", color="crimson",
                                                    lw=0.9))
            ax.text((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, f" {text}",
                    color="crimson", fontsize=8, va="bottom")
        for (p, text) in s.get("notes", []):
            ax.text(p[0], p[1], text, fontsize=8, color="0.25")
        # annotations do not count for autoscaling; without this, dims placed
        # next to the part end up outside the axes
        extra = [p for d in s.get("dims", []) for p in d[:2]]
        extra += [n[0] for n in s.get("notes", [])]
        if extra:
            ax.update_datalim(np.asarray(extra, dtype=float))
            ax.autoscale_view()
        ax.set_aspect("equal")
        ax.grid(alpha=0.25)
        ax.set_title(s["label"], fontsize=10)
        ax.set_xlabel("xyz"[s["u"]] + " [mm]")
        ax.set_ylabel("xyz"[s["v"]] + " [mm]")
        if s.get("invert_v"):
            ax.invert_yaxis()
    if title:
        fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
