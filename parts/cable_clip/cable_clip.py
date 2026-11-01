"""Corner cable clip for an LG 32" Ergo monitor (top-left corner).

Holds the Quest 3 USB-C cable in an open C-ring on top of the monitor so it
runs from the headset hook (left, above) or the user's head (front) over the
corner and down behind the monitor.

Frame: monitor top-left front corner at the origin.
  x  to the right along the top edge
  y  from the front face (y=0) to the back
  z  up; the monitor occupies z <= 0, s = -z is the distance below the top edge
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import cadlib as cl  # noqa: E402

VERSION = "v2"
# v2 (after first print): clip slid off when the cable moved -> 0.6 mm rib squeeze
# and 5 ribs; cable slipped out of the ring -> gap 3.2, bore 6.0; edges too sharp
# -> all outer edges rounded.

# ---- measured (Enno, 2026-10-29)
MON_T0 = 17.0          # thickness at the corner
MON_DT_X = 0.04        # +2.0 mm over 50 mm along the top edge
MON_DT_S = 0.02        # +1.0 mm over 50 mm down the left edge
MON_R = 2.5            # corner radius seen from the front
BEZEL = 8.0            # picture starts 8 mm from top and left edge
CABLE_D = 4.5

# ---- fit (PETG on Bambu P2S)
CLR = cl.FDM_FIT["slide"]  # free space around the monitor, per side
RIB_INTERF = 0.60          # net squeeze of the rear ribs (0.30 in v1 was too loose)
RIB_R = 1.5
RIB_LEN = 10.0

# ---- shape
WALL = 2.4             # web over the edges and rear plate (6 lines at 0.4)
WALL_FRONT = 2.0       # front lip plate
H_FRONT = 6.0          # front lip reaches 6 mm onto the bezel (bezel is 8)
H_REAR = 15.0          # rear lip reaches 15 mm down/in on the back
L_TOP = 45.0           # arm along the top edge
L_SIDE = 35.0          # arm down the left edge
CHAMFER = 4.0          # outer corner, 45 deg so it prints without supports
EDGE_R = 0.8           # rounding of all outer edges; < half the thinnest plate

# ---- cable ring
RING_X = 22.0          # ring centre along the top edge
RING_BORE = 6.0        # cable still slides (7.0 in v1 rattled)
RING_WALL = 2.4
RING_GAP = 3.2         # ~70% of the cable; 3.8 in v1 let the cable slip out
RING_LEN = 14.0
RING_FLARE = 1.2       # bore widens by this at both ends, over 2 mm
GAP_CHAMFER = 0.6      # small lead-in at the gap; more makes knife edges

OUT = HERE / "out" / VERSION


def mon_t(x, s):
    return MON_T0 + MON_DT_X * x + MON_DT_S * s


def wedge_prism(outline_xs, y_front, back_offset):
    """Convex prism over an (x, s) outline; back face follows the monitor wedge."""
    pts = []
    for x, s in outline_xs:
        pts.append((x, y_front, -s))
        pts.append((x, mon_t(max(x, 0), max(s, 0)) + back_offset, -s))
    return cl.hull_points(pts)


def monitor(clearance=0.0, ext=(80.0, 60.0)):
    """The monitor corner, optionally grown by `clearance` on every side."""
    c = clearance
    outline = [(ext[0], -c), (ext[0], ext[1]), (-c, ext[1])]
    outline += cl.arc((MON_R, MON_R), MON_R + c, 180, 270)   # in (x, s): corner arc
    return wedge_prism(outline, -c, c)


def slab(outline_xs, y0, y1, r=None):
    """Rounded convex plate over an (x, s) outline, between y0(x, s) and y1(x, s)."""
    r = EDGE_R if r is None else r
    pts = []
    for x, s in cl.inset_polygon(outline_xs, r):
        pts.append((x, y0(x, s) + r, -s))
        pts.append((x, y1(x, s) - r, -s))
    return cl.rounded_hull(pts, r)


def build():
    c, w, r = CLR, WALL, EDGE_R
    o = c + w                      # outer offset of the webs from the monitor edge
    ch = CHAMFER
    # The bed side (x = -o) is built r too far out and trimmed flat afterwards,
    # so the print gets sharp bed edges instead of overhanging roundings.
    e = -o - r
    b = (e, ch - o + r)            # chamfer x + s = ch - 2o, extended to x = e
    t0 = (ch - o, -o)
    y_front = -c - WALL_FRONT
    yf = lambda x, s: y_front      # noqa: E731
    yi = lambda x, s: -c           # noqa: E731
    yr = lambda x, s: mon_t(x, s) + c  # noqa: E731
    yb = lambda x, s: mon_t(x, s) + o  # noqa: E731
    slabs = [
        # top arm: web over the top edge, front lip, rear lip
        slab([t0, (L_TOP, -o), (L_TOP, -c), (ch - 2 * o + c, -c)], yf, yb),
        slab([b, t0, (L_TOP, -o), (L_TOP, H_FRONT), (e, H_FRONT)], yf, yi),
        slab([b, t0, (L_TOP, -o), (L_TOP, H_REAR), (e, H_REAR)], yr, yb),
        # side arm
        slab([b, (-c, ch - 2 * o + c), (-c, L_SIDE), (e, L_SIDE)], yf, yb),
        slab([b, t0, (H_FRONT, -o), (H_FRONT, L_SIDE), (e, L_SIDE)], yf, yi),
        slab([b, t0, (H_REAR, -o), (H_REAR, L_SIDE), (e, L_SIDE)], yr, yb),
    ]
    # The insets leave a notch where the two webs meet at the chamfer (acute
    # corner). Fill the corner and cut the monitor (with clearance) back out.
    slabs.append(slab([b, t0, (MON_R + 2, -o), (MON_R + 2, MON_R + 2),
                       (e, MON_R + 2)], yf, yb))
    body = sum(slabs[1:], slabs[0]) - monitor(c)

    # crush ribs on the inside of the rear plate, along x (vertical when printed)
    rib_y = lambda x, s: mon_t(x, s) + c - (c + RIB_INTERF) + RIB_R  # noqa: E731
    ribs = []
    for (xc, s) in [(L_TOP - 8, 9.0), (L_TOP - 21, 9.0), (9.0, 9.0),
                    (9.0, 20.0), (9.0, L_SIDE - 5)]:
        x0, x1 = xc - RIB_LEN / 2, xc + RIB_LEN / 2
        ribs.append(cl.hull(cl.sphere((x0 + RIB_R, rib_y(x0, s), -s), RIB_R, 32),
                            cl.sphere((x1 - RIB_R, rib_y(x1, s), -s), RIB_R, 32)))
    ribs = sum(ribs[1:], ribs[0])
    # keep only the part of the ribs that sits inside the monitor gap or the wall
    ribs = ribs ^ wedge_prism([(0, 0), (200, 0), (200, 200), (0, 200)], 0, o)

    # cable ring on the top web, rounded ends, 45 deg flank towards the bed
    z_top = o
    ro = RING_BORE / 2 + RING_WALL
    zc = z_top + ro - 0.8
    yc = (mon_t(RING_X, 0)) / 2
    y0, y1 = yc - RING_LEN / 2 + r, yc + RING_LEN / 2 - r
    pts = [(x, y, z) for (x, z) in cl.arc((RING_X, zc), ro - r, 0, 360, 33)[:-1]
           for y in (y0, y1)]
    k = (ro - r) / 2 ** 0.5
    z_f = z_top - 1.0              # foot buried in the web
    x_f = RING_X - k - (zc + k - z_f)
    pts += [(x, y, z_f) for x in (x_f, RING_X) for y in (y0, y1)]
    boss = cl.rounded_hull(pts, r)
    rb = RING_BORE / 2
    bore = cl.cyl("y", (RING_X, yc, zc), rb, RING_LEN + 2)
    # cones at both ends: radius at low y first, then at high y
    bore = bore + cl.cyl("y", (RING_X, yc - RING_LEN / 2 + 0.9, zc),
                         rb + RING_FLARE, 2.2, rb)
    bore = bore + cl.cyl("y", (RING_X, yc + RING_LEN / 2 - 0.9, zc),
                         rb, 2.2, rb + RING_FLARE)
    gap = cl.hull(cl.box(RING_X, RING_X + ro - GAP_CHAMFER, yc - RING_LEN,
                         yc + RING_LEN, zc - RING_GAP / 2, zc + RING_GAP / 2),
                  cl.box(RING_X + ro, RING_X + ro + 0.5, yc - RING_LEN, yc + RING_LEN,
                         zc - RING_GAP / 2 - GAP_CHAMFER,
                         zc + RING_GAP / 2 + GAP_CHAMFER))
    frame = (body + boss - bore - gap).trim_by_plane((1, 0, 0), -o)
    part = frame + (ribs - bore)
    cable = cl.cyl("y", (RING_X, yc, zc - rb + CABLE_D / 2), CABLE_D / 2, 60)
    return {"part": part, "body_no_ribs": frame,
            "ribs": ribs, "cable": cable, "ring_center": (RING_X, yc, zc)}


def print_orientation(m):
    """Side web on the bed: everything else rises as vertical walls."""
    return cl.drop_to_bed(m.rotate((0, -90, 0)))


def checks(g):
    rep = cl.Report(f"cable_clip {VERSION}")
    part = g["part"]
    cl.check_solid(rep, part)
    mon = monitor(0.0)
    cl.check_no_overlap(rep, g["body_no_ribs"], mon, "frame clears monitor")
    cl.check_gap(rep, g["body_no_ribs"], mon, "frame clearance", CLR * 0.9)
    v_ribs = (part ^ mon).volume()
    rep.add("rib squeeze", 0 < v_ribs < 80,
            f"ribs press {RIB_INTERF} mm into the back, {v_ribs:.1f} mm3", v_ribs)
    screen = cl.box(BEZEL, 300, -50, 0.0, -300, -BEZEL)
    cl.check_keepout(rep, part, {"screen area in front of the picture": screen})
    cl.check_no_overlap(rep, part, g["cable"], "cable sits free in the ring")
    rep.add("cable snaps in", RING_GAP < CABLE_D,
            f"gap {RING_GAP} mm < cable {CABLE_D} mm, bore {RING_BORE} mm", RING_GAP)
    pm = cl.to_trimesh(print_orientation(part))
    # the C-ring jaws taper to ~1.2 mm right at their tips by design
    cl.check_wall_thickness(rep, pm, min_mm=1.6, ignore_frac=0.01)
    # ~0.7 mm ledges where the bore meets the gap; bridged without supports
    cl.check_overhangs(rep, pm, 45.0, allowed_mm2=12.0)
    return rep, pm


def pictures(g, pm):
    t = cl.to_trimesh
    part, mon = t(g["part"]), t(monitor(0.0, (70, 50)))
    cable = t(g["cable"])
    blue, black, white = (0.2, 0.45, 0.85), (0.12, 0.12, 0.14), (0.92, 0.92, 0.92)
    objs = [("clip", part, blue), ("monitor", t(monitor(0.0, (120, 80))), black),
            ("cable", cable, white), ("print", pm, blue)]
    on_mon = ["clip", "monitor", "cable"]
    cl.render_openscad(objs, OUT / "render", [
        ("Vorne links, am Monitor", "front.png", (20, 10, -5, 62, 0, 35, 190), on_mon),
        ("Hinten links, am Monitor", "back.png", (20, 10, -5, 62, 0, 215, 190), on_mon),
        ("Clip allein, vorne", "clip_front.png", (20, 10, -8, 70, 0, 35, 150),
         ["clip"]),
        ("Druckausrichtung", "print.png", (0, 0, 20, 60, 0, 30, 170), ["print"]),
    ], sheet=OUT / f"kabelclip_{VERSION}_ansichten.png",
        title=f"Kabelclip {VERSION} (Quest-3-Kabel, LG 32\" Ergo)")
    rx, yc, zc = g["ring_center"]
    tt = mon_t(30, 0)
    cl.plot_sections([
        {"label": "Schnitt x=30 (oberer Arm)", "axis": 0, "value": 30.0, "u": 1, "v": 2,
         "objects": [(part, "tab:blue", "-"), (mon, "0.3", "--")],
         "dims": [((0, 4), (tt, 4), f"Monitor {tt:.1f}"),
                  ((-4, 0), (-4, -H_FRONT), f"{H_FRONT:.0f}"),
                  ((tt + 4, 0), (tt + 4, -H_REAR), f"{H_REAR:.0f}")]},
        {"label": "Schnitt z=-20 (seitlicher Arm)", "axis": 2, "value": -20.0,
         "u": 0, "v": 1, "objects": [(part, "tab:blue", "-"), (mon, "0.3", "--")],
         "invert_v": True},
        {"label": f"Schnitt y={yc:.1f} (Kabelring)", "axis": 1, "value": yc,
         "u": 0, "v": 2,
         "objects": [(part, "tab:blue", "-"), (mon, "0.3", "--"),
                     (cable, "tab:orange", "-")],
         "notes": [((rx + 5, zc + 4), f"Spalt {RING_GAP}"),
                   ((rx - 4, zc + 6.5), f"Bohrung {RING_BORE}")]},
    ], OUT / "sections.png", f"Kabelclip {VERSION}, Maße in mm")


def main():
    OUT.mkdir(exist_ok=True)
    g = build()
    rep, pm = checks(g)
    rep.print()
    rep.save(OUT / "checks.json")
    pictures(g, pm)
    hashes = cl.export_parts({"clip": print_orientation(g["part"])}, OUT,
                             f"cable_clip_{VERSION}")
    for k, v in hashes.items():
        print(f"  {k}  {v[:16]}")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
