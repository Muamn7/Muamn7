"""
IgG Antibody - 3D-print version split BY COLOUR (Blender 4.2+ / 5.x)

Every colour becomes its own set of watertight pieces, so each colour can be
printed in its own filament and the pieces glued together:

    blue   (heavy chain)      pink (light chain)     purple (antigen-binding site)
    yellow (disulfide bonds)  lightblue (hinge links) black (pedestal)

Where two colours overlap, the higher-priority colour keeps the volume and the
other one gets a smooth "seat" cut into it (with clearance), so the pieces nest
into each other and register by themselves when glued. The Fc columns get flat
bottoms and pins that drop into sockets in the pedestal.

Output (next to this script):
    print_colors/<colour>/<piece>.stl        (mm, one file per piece)
    print_colors/IgG_colour_pieces.blend     (assembled, coloured)
    print_colors/IgG_colour_pieces_preview.png  (with --render)

Headless:
    blender -b -P igg_antibody_print_colors.py -- --height 180 --render
"""

import os
import sys

import bpy
import bmesh  # noqa: E402  (must come after bpy when using the bpy pip module)
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import igg_antibody as igg  # noqa: E402
import igg_antibody_print as P  # noqa: E402

# --------------------------------------------------------------------------
# Settings (millimetres)
# --------------------------------------------------------------------------
PRINT_HEIGHT_MM = 180.0
VOXEL_MM = 0.35
MIN_ROD_MM = 1.8          # thicker tubes -> bigger glue surfaces
CLEARANCE_MM = 0.15       # gap between nesting pieces
PIN_CLEARANCE_MM = 0.2    # radial play of the pins in the pedestal
PIN_DEPTH_MM = 5.0
MIN_PIECE_MM3 = 4.0       # smaller fragments are dropped
MAX_TRIS_PER_COLOUR = 320_000
OUT_DIR = os.path.join(HERE, "print_colors")

# colour key -> (folder name, material key in igg_antibody)
COLOURS = {
    "heavy": "blue",
    "light": "pink",
    "var": "purple",
    "ss": "yellow",
    "linker": "lightblue",
}
# who keeps the overlapping volume: earlier wins
PRIORITY = ["heavy", "light", "var", "ss", "linker"]


# --------------------------------------------------------------------------
def displace(obj, dist):
    m = obj.modifiers.new("Offset", "DISPLACE")
    m.direction = "NORMAL"
    m.mid_level = 0.0
    m.strength = dist
    igg.bake_modifiers(obj)


def smooth(obj, iterations):
    m = obj.modifiers.new("Smooth", "CORRECTIVE_SMOOTH")
    m.use_only_smooth = True
    m.iterations = iterations
    m.factor = 0.5
    igg.bake_modifiers(obj)


def envelope(name, objs, gap):
    """
    Smooth shell around objs, `gap` larger than their surface: a morphological
    closing (dilate -> smooth -> erode) that fills the valleys between atoms, so
    the seat it cuts has no undercuts and the pieces can be pressed together.
    """
    env = P.combine(name, objs)
    r = 1.2
    P.voxel_union(env, VOXEL_MM)
    displace(env, r + gap)
    P.voxel_union(env, 0.5)
    smooth(env, 6)
    displace(env, -r)
    P.voxel_union(env, VOXEL_MM)
    return env


def split_pieces(obj, min_volume):
    """Split obj into its loose parts, dropping fragments below min_volume."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    seen, islands = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, isl = [f], []
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            isl.append(cur.index)
            for e in cur.edges:
                for o in e.link_faces:
                    if o.index not in seen:
                        seen.add(o.index)
                        stack.append(o)
        islands.append(isl)
    bm.free()

    pieces = []
    for i, isl in enumerate(islands):
        keep = set(isl)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
        loose = [v for v in bm.verts if not v.link_faces]
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
        vol = bm.calc_volume(signed=False)
        if vol >= min_volume:
            me = bpy.data.meshes.new(f"{obj.name}_{i}")
            bm.to_mesh(me)
            pieces.append(P.link(bpy.data.objects.new(me.name, me)))
        bm.free()
    return pieces


def centroid(obj):
    vs = obj.data.vertices
    return sum((v.co for v in vs), Vector()) / max(len(vs), 1)


def main(height_mm=PRINT_HEIGHT_MM, render=False):
    os.makedirs(OUT_DIR, exist_ok=True)

    # 1) build the coloured model with print-safe tubes, scale to mm
    igg.MIN_ROD = MIN_ROD_MM / (height_mm / 6.0)
    parts = igg.build()
    pedestal = bpy.data.objects["Pedestal"]
    top = max((p.matrix_world @ Vector(c)).z for p in parts for c in p.bound_box)
    S = height_mm / top
    for o in parts + [pedestal]:
        o.data.transform(o.matrix_world)
        o.parent = None
        o.matrix_world = Matrix.Identity(4)
        o.data.transform(Matrix.Scale(S, 4))
    base_top = igg.BASE_TOP * S
    print(f"scale {S:.2f} mm/unit, pedestal top at {base_top:.1f} mm")

    groups = {k: [] for k in COLOURS}
    for p in parts:
        key = p.data.materials[0].name.replace("MAT_", "")
        groups[key].append(p)
    mats = {k: bpy.data.materials["MAT_" + k] for k in COLOURS}
    mats["base"] = bpy.data.materials["MAT_base"]

    # pins: a post under each Fc column, reaching PIN_DEPTH_MM into the pedestal,
    # plus a spine CH3 -> CH2 so each column stays one solid piece
    pins = []
    for side in ("L", "R"):
        c3 = centroid(bpy.data.objects[f"Fc_CH3_{side}"])
        c2 = centroid(bpy.data.objects[f"Fc_CH2_{side}"])
        foot = Vector((c3.x, c3.y, base_top - PIN_DEPTH_MM))
        pin = P.tube(f"Pin_{side}", foot, Vector((c3.x, c3.y, base_top + 8.0)), 3.0)
        pins.append(pin)
        groups["heavy"].append(pin)
        groups["heavy"].append(P.tube(f"Spine_{side}", c3, c2, 0.21 * S))

    # 2) one watertight solid per colour (before any cutting)
    raw = {}
    for k in PRIORITY:
        s = P.combine(f"raw_{k}", groups[k])
        P.voxel_union(s, VOXEL_MM)
        P.decimate(s, MAX_TRIS_PER_COLOUR)
        raw[k] = s
        print(f"{k}: {len(s.data.polygons):,} faces")

    # 3) pedestal: sockets for the pins; Fc columns get flat bottoms on it
    base = P.combine("black_Pedestal", [pedestal])
    sockets = P.combine("sockets", pins)
    displace(sockets, PIN_CLEARANCE_MM)
    P.boolean(base, sockets, "DIFFERENCE")
    final = {"base": base}

    floor = P.box("floor", -1e3, base_top)
    heavy = P.combine("heavy", [raw["heavy"]])
    keep_pins = P.combine("keep_pins", pins)
    P.boolean(floor, keep_pins, "DIFFERENCE")     # floor with the pins carved out
    P.boolean(heavy, floor, "DIFFERENCE")         # flat bottoms, pins kept
    final["heavy"] = heavy
    for o in (floor, keep_pins, sockets):
        bpy.data.objects.remove(o)

    # 4) every other colour gets the seats of the colours above it
    for i, k in enumerate(PRIORITY[1:], start=1):
        env = envelope(f"env_{k}", [raw[w] for w in PRIORITY[:i]], CLEARANCE_MM)
        piece = P.combine(k, [raw[k]])
        P.boolean(piece, env, "DIFFERENCE")
        bpy.data.objects.remove(env)
        final[k] = piece
        print(f"cut {k} by {PRIORITY[:i]}")

    # 5) split into loose pieces, name them after the nearest original part
    coll = igg.get_collection("Print_Pieces")
    originals = [p for p in parts]
    report, pieces_all = [], []
    for k, solid in final.items():
        folder = "black" if k == "base" else COLOURS[k]
        os.makedirs(os.path.join(OUT_DIR, folder), exist_ok=True)
        for f in os.listdir(os.path.join(OUT_DIR, folder)):
            os.remove(os.path.join(OUT_DIR, folder, f))
        pieces = [solid] if k == "base" else split_pieces(solid, MIN_PIECE_MM3)
        names = {}
        for pc in pieces:
            c = centroid(pc)
            if k == "base":
                nm = "Pedestal"
            else:
                cands = [o for o in originals if o.data.materials[0] == mats[k]] or originals
                nm = min(cands, key=lambda o: (centroid(o) - c).length).name
                nm = nm.replace("Fc_Disulfide", "Fc_Bridge").replace("Hinge_Disulfide", "Hinge")
            names[nm] = names.get(nm, 0) + 1
            label = nm if names[nm] == 1 else f"{nm}_{names[nm]}"
            pc.name = f"{folder}_{label}"
            pc.data.materials.clear()
            pc.data.materials.append(mats[k])
            if k != "base":
                igg.shade_smooth(pc.data)
            for c_ in pc.users_collection:
                c_.objects.unlink(pc)
            coll.objects.link(pc)
            nm_edges, vol, tris = P.check_solid(pc)
            dims = pc.dimensions
            report.append((folder, pc.name, dims.copy(), vol, tris, nm_edges))
            pieces_all.append(pc)

            # export: piece standing on the bed, centred
            me = pc.data.copy()
            lo = Vector((min(v.co.x for v in me.vertices), min(v.co.y for v in me.vertices),
                         min(v.co.z for v in me.vertices)))
            hi = Vector((max(v.co.x for v in me.vertices), max(v.co.y for v in me.vertices), 0))
            me.transform(Matrix.Translation((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)))
            tmp = P.link(bpy.data.objects.new("tmp_export", me))
            for o in bpy.context.scene.objects:
                o.select_set(False)
            tmp.select_set(True)
            bpy.context.view_layer.objects.active = tmp
            bpy.ops.wm.stl_export(filepath=os.path.join(OUT_DIR, folder, label + ".stl"),
                                  export_selected_objects=True, ascii_format=False,
                                  global_scale=1.0)
            bpy.data.objects.remove(tmp)
            bpy.data.meshes.remove(me)

    print("\nPIECES")
    for folder, name, d, vol, tris, nm in report:
        print(f"  {name:32s} {d.x:6.1f} x {d.y:5.1f} x {d.z:6.1f} mm  {vol / 1000:6.2f} cm3  "
              f"{tris:7,} tris  non-manifold {nm}")

    # 6) keep only the pieces (assembled, coloured) in the saved file
    keep = set(pieces_all)
    for o in list(bpy.data.objects):
        if o.type == "MESH" and o not in keep and o.name != "Backdrop":
            bpy.data.objects.remove(o)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT_DIR, "IgG_colour_pieces.blend"),
                                compress=True)
    if render:
        render_exploded(pieces_all, S)
    return report


def render_exploded(pieces, S):
    """Exploded preview: every piece pushed away from the model's centre line."""
    centre_z = 95.0
    for pc in pieces:
        c = centroid(pc)
        if pc.name.startswith("black"):
            continue
        off = Vector((c.x * 0.22, 0.0, (c.z - centre_z) * 0.12 + 18.0))
        pc.location = off
    sc = bpy.context.scene
    for o in bpy.data.objects:
        if o.type == "LIGHT":
            o.location *= S
            o.data.energy *= S * S
            o.data.size *= S
        if o.name == "Backdrop":
            o.scale = (S, S, S)
    cam = sc.camera
    cam.location = Vector((0, -650, 260))
    t = Vector((0, 0, 115))
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 60
    cam.data.clip_end = 5000
    igg.setup_render(64)
    sc.render.resolution_x, sc.render.resolution_y = 1200, 1300
    sc.render.filepath = os.path.join(OUT_DIR, "IgG_colour_pieces_preview.png")
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    h = float(argv[argv.index("--height") + 1]) if "--height" in argv else PRINT_HEIGHT_MM
    main(h, render="--render" in argv)
