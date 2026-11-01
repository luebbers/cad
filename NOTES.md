# Learnings for the CAD skill

Collected while building parts, to be distilled into a skill later.

## Setup
- `uv run python -I <script>` in this repo; deps in `pyproject.toml`.
- trimesh needs `scipy` or `networkx` for `split()`, `rtree` for ray casts, `lxml` for 3MF.
- manifold3d has `min_gap()` for clearance checks; `rotate((0,-90,0))` maps x -> z.

## Workflow that worked (cable_clip v1, 2026-10-29)
1. Ask for measurements first (thickness at several points, radii, keep-out zones such
   as the visible screen area), never design around estimates.
2. Agree on the concept with an ASCII sketch before modelling.
3. Model in a frame anchored on the mating object (monitor corner = origin), keep the
   mating object as its own solid: it doubles as the subtractor (grown by clearance)
   and as the reference for overlap/gap checks.
4. Checks: watertight, one piece, overlap/gap vs. mating object, intended interference
   volume (ribs), keep-out zones, functional fits (cable vs. gap), wall thickness by
   ray cast, overhangs in print orientation.
5. Look at the pictures every time; the checks found real problems on the first run:
   - lead-in chamfer on the C-ring gap made knife edges (0.4-0.9 mm)
   - support flank under a horizontally printed ring was ~55 deg instead of 45
6. Allow remaining findings only in the part script, with a comment why, not by
   loosening cadlib defaults.

## Iteration after the first print (v1 -> v2)
- Feedback v1: overall fit right, but slid off when the cable moved, cable slipped
  out of the ring, edges felt sharp.
- Friction clips: 0.3 mm net rib squeeze was too little for PETG on a smooth
  monitor back; v2 uses 0.6 mm and 5 ribs. Think about the pull direction: the
  cable pulled exactly along the mounting direction.
- Snap-in ring: gap 85% of the cable was too wide, v2 uses ~70% (3.2 for 4.5),
  bore 1.33x the cable.
- Edge rounding: do NOT round afterwards with Minkowski opening in manifold3d (8 min,
  genus 72 or millions of degenerate faces). Build from convex pieces with
  `cadlib.rounded_hull` (hull of spheres at `inset_polygon` points) instead:
  1.5 s, watertight.
  - Inset polygons pull back far at acute corners (r / sin(angle/2)); fill such
    corners with an extra piece and cut the mating object back out.
  - Build the bed side r too far out and `trim_by_plane` it flat, otherwise the
    bed edges become overhanging roundings.
- Keep every version's outputs in `out/<version>/`, note the reason for each change
  in the part script header.

## Pictures
- matplotlib previews are too coarse to judge a part; render with local OpenSCAD:
  export clip/context/cable as STL, `scene.scad` with `color() import()`, then
  `OpenSCAD -o x.png --render --colorscheme=Tomorrow --projection=p --camera=tx,ty,tz,rx,ry,rz,dist`.
- In this frame (y = back) `rz=35` looks from the front left, `rz=215` from the back left.
- Show the part on the mating object and alone; tile into one sheet.

## Design rules
- Print orientation decides the shape: choose it first, then shape every feature so
  it rises as walls or <= 45 deg flanks (teardrop rings, 45 deg chamfers, no
  outer fillets on edges facing the bed).
- FDM fits that printed true: pin 0.10, pocket 0.25 per side, ribs 0.25 proud
  (BP-SCL6 box). Clamping parts (PETG, P2S): clearance 0.2 + 5 ribs (r 1.5) with
  0.6 net interference - confirmed by print v2 (2026-10-29), 0.3 was too loose.
- Snap-in cable channel: gap ~70% of cable diameter, bore ~1.33x cable - confirmed
  by print v2; 85% / 1.55x let the cable slip out.
- Rounded edges r 0.8 via convex slabs were enough to remove the "sharp" feel.
- Two print iterations to a working part; budget for at least one.
