"""
Export the "Dr / Rahma Ali" letters and the heartbeat line as a two-colour
3MF for a multi-material printer (Bambu AMS, Prusa MMU, ...).

The piece lies flat, back on the bed, letter faces up:
  - part 1 "Gold":  the letter bodies with their bevelled edges
  - part 2 "Black": the flat front of every letter, FACE_THICKNESS deep
The two parts never overlap, so the slicer only has to give each one a filament.

Usage
-----
Inside Blender: open this file in the Scripting tab and Run Script
(dental_nameplate.py must be in the same folder).

Command line:
    blender -b -P export_letters_3mf.py -- --out letters.3mf --width 240

Options after "--":
    --out PATH       output .3mf (default: letters.3mf next to this script)
    --width MM       total width of the print in mm, 0 keeps the model size
    --face MM        thickness of the black face in mm
    --name / --title / --font   same as dental_nameplate.py
"""

import bpy  # noqa: F401  (must be imported before bmesh when bpy runs as a module)

import os
import struct
import sys
import zipfile

import bmesh
from mathutils import Matrix


def _script_dir():
    here = globals().get("__file__")
    if here and os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(here)), "dental_nameplate.py")):
        return os.path.dirname(os.path.abspath(here))
    for text in bpy.data.texts:
        if text.filepath and os.path.basename(text.filepath) == "export_letters_3mf.py":
            return os.path.dirname(bpy.path.abspath(text.filepath))
    raise RuntimeError("Put export_letters_3mf.py next to dental_nameplate.py")


HERE = _script_dir()
sys.path.insert(0, HERE)
import dental_nameplate as plate  # noqa: E402

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

OUTPUT = os.path.join(HERE, "letters.3mf")
TARGET_WIDTH_MM = 240.0      # fits a 256 mm bed; 0 keeps the model's real size (~270 mm)
FACE_THICKNESS_MM = 1.0      # black layer on top of each letter
BAR_HEIGHT = 0.0025           # hidden bars on the back that hold the letters together
BAR_DEPTH = 0.003

GOLD_COLOR = "#D4A94AFF"
BLACK_COLOR = "#111111FF"

# World (x, y, z) -> print (x, z, -y): the letter fronts (world -Y) face up (+Z).
TO_PRINT = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def print_mesh(obj):
    """Copy of obj's mesh in print orientation, back of the piece at z = 0."""
    me = obj.data.copy()
    me.transform(TO_PRINT @ obj.matrix_world)
    z0 = min(v.co.z for v in me.vertices)
    me.transform(Matrix.Translation((0, 0, -z0)))
    # Curve conversion leaves the caps and the bevelled sides as separate
    # surfaces; weld them into a closed solid or the booleans fall apart.
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return me


def face_prism(me, depth, rise=0.0005):
    """Solid under the black front faces: from `rise` above them to `depth` below."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != 1], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bmesh.ops.translate(bm, vec=(0, 0, rise), verts=bm.verts)
    res = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces), use_keep_orig=True)
    moved = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, -(depth + rise)), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    out = bpy.data.meshes.new("FacePrism")
    bm.to_mesh(out)
    bm.free()
    return out


def loose_parts(meshes):
    """Every closed shell of the given meshes as its own mesh."""
    parts = []
    for me in meshes:
        bm = bmesh.new()
        bm.from_mesh(me)
        seen = set()
        for start in bm.faces:
            if start.index in seen:
                continue
            island, stack = [], [start]
            seen.add(start.index)
            while stack:
                f = stack.pop()
                island.append(f)
                for e in f.edges:
                    for g in e.link_faces:
                        if g.index not in seen:
                            seen.add(g.index)
                            stack.append(g)
            part = bm.copy()
            keep = {f.index for f in island}
            bmesh.ops.delete(part, geom=[f for f in part.faces if f.index not in keep], context="FACES")
            bmesh.ops.delete(part, geom=[v for v in part.verts if not v.link_faces], context="VERTS")
            out = bpy.data.meshes.new("Part")
            part.to_mesh(out)
            part.free()
            parts.append(out)
        bm.free()
    return parts


def clean(me, min_volume=1e-9):
    """Drop the paper-thin islands booleans leave where surfaces just touch."""
    bm = bmesh.new()
    bm.from_mesh(me)
    seen, doomed = set(), []
    for start in bm.faces:
        if start in seen:
            continue
        island, stack = [], [start]
        seen.add(start)
        while stack:
            f = stack.pop()
            island.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g not in seen:
                        seen.add(g)
                        stack.append(g)
        volume = sum(f.calc_center_median().dot(f.normal) * f.calc_area() for f in island) / 3
        if abs(volume) < min_volume:
            doomed += island
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(me)
    bm.free()
    return me


SOLVER = "MANIFOLD" if "MANIFOLD" in {i.identifier for i in
                                      bpy.types.BooleanModifier.bl_rna.properties["solver"].enum_items} else "EXACT"


def boolean(name, base_me, operand, operation):
    """Apply one boolean. `operand` is a mesh or a list of meshes (unioned together)."""
    coll = bpy.context.scene.collection
    base = bpy.data.objects.new(name, base_me.copy())
    coll.objects.link(base)
    mod = base.modifiers.new("Boolean", "BOOLEAN")
    mod.operation = operation
    mod.solver = SOLVER
    if SOLVER == "EXACT":
        mod.use_self = True
    temp = []
    if isinstance(operand, list):
        group = bpy.data.collections.new(name + " operands")
        for me in operand:
            obj = bpy.data.objects.new(name + " operand", me)
            group.objects.link(obj)
            temp.append(obj)
        mod.operand_type = "COLLECTION"
        mod.collection = group
    else:
        obj = bpy.data.objects.new(name + " operand", operand)
        coll.objects.link(obj)
        temp.append(obj)
        mod.object = obj
    bpy.context.view_layer.update()
    result = clean(bpy.data.meshes.new_from_object(base.evaluated_get(bpy.context.evaluated_depsgraph_get())))
    bpy.data.objects.remove(base)
    for obj in temp:
        bpy.data.objects.remove(obj)
    if isinstance(operand, list):
        bpy.data.collections.remove(group)
    return result


def union(name, meshes):
    parts = loose_parts(meshes)
    return boolean(name, parts[0], parts[1:], "UNION") if len(parts) > 1 else parts[0]


def box(x0, x1, y0, y1, z0, z1):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(x1 - x0, y1 - y0, z1 - z0), verts=bm.verts)
    bmesh.ops.translate(bm, vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), verts=bm.verts)
    me = bpy.data.meshes.new("Bar")
    bm.to_mesh(me)
    bm.free()
    return me


def connector_bars(name_me, pieces_me):
    """Bars on the back of the piece so it prints as one part: one along the
    baseline (joins the words), and one from every other loose piece, such as
    the dot of an i, down to it. From the front they hide behind the letters."""
    xs = [v.co.x for v in name_me.vertices]
    y0 = min(v.co.y for v in name_me.vertices)
    rail = (min(xs) + 0.002, max(xs) - 0.002, y0 + 0.0004, y0 + BAR_HEIGHT)
    bars = [box(rail[0], rail[1], rail[2], rail[3], 0.0, BAR_DEPTH)]
    for part in loose_parts([pieces_me]):
        low = min(part.vertices, key=lambda v: v.co.y).co
        if low.y <= rail[3]:
            continue
        x = min(max(low.x, rail[0] + BAR_HEIGHT), rail[1] - BAR_HEIGHT)
        top = (low.y + max(v.co.y for v in part.vertices)) / 2
        bars.append(box(x - BAR_HEIGHT / 2, x + BAR_HEIGHT / 2, rail[2], top, 0.0, BAR_DEPTH))
    return bars


def triangles(me, scale, offset):
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.verts.index_update()
    verts = [((v.co.x - offset[0]) * scale, (v.co.y - offset[1]) * scale, v.co.z * scale) for v in bm.verts]
    tris = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    return verts, tris


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def mesh_xml(obj_id, name, pindex, verts, tris):
    lines = [f'  <object id="{obj_id}" name="{name}" type="model" pid="1" pindex="{pindex}">',
             "   <mesh>", "    <vertices>"]
    lines += [f'     <vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in verts]
    lines += ["    </vertices>", "    <triangles>"]
    lines += [f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris]
    lines += ["    </triangles>", "   </mesh>", "  </object>"]
    return "\n".join(lines)


def write_3mf(path, parts, title):
    """parts: [(name, colour, verts, tris)] -> one object made of one component per part."""
    colours = "\n".join(f'   <base name="{n}" displaycolor="{c}"/>' for n, c, _, _ in parts)
    objects = [mesh_xml(i + 2, n, i, v, t) for i, (n, _, v, t) in enumerate(parts)]
    group_id = len(parts) + 2
    comps = "\n".join(f'   <component objectid="{i + 2}"/>' for i in range(len(parts)))
    model = f"""<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
 <metadata name="Title">{title}</metadata>
 <metadata name="Application">Blender dental_nameplate</metadata>
 <resources>
  <basematerials id="1">
{colours}
  </basematerials>
{chr(10).join(objects)}
  <object id="{group_id}" name="{title}" type="model">
   <components>
{comps}
   </components>
  </object>
 </resources>
 <build>
  <item objectid="{group_id}"/>
 </build>
</model>
"""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)


def write_stl(path, verts, tris):
    with open(path, "wb") as f:
        f.write(b"dental_nameplate".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            f.write(struct.pack("<3f", 0, 0, 0))
            for i in (a, b, c):
                f.write(struct.pack("<3f", *verts[i]))
            f.write(b"\0\0")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def export(out=OUTPUT, width_mm=TARGET_WIDTH_MM, face_mm=FACE_THICKNESS_MM,
           title=plate.TITLE, name=plate.NAME, font=None):
    plate.build(title, name, font)
    objs = [bpy.data.objects[n] for n in ("Name Letters", "Title Letters", "Heartbeat Line")]
    meshes = [print_mesh(o) for o in objs]
    body = union("Body", meshes + connector_bars(meshes[0], union("Pieces", meshes)))
    if len(loose_parts([body])) > 1:
        print("[3mf] warning: the letters are still in more than one piece")
    faces = union("Faces", [face_prism(me, face_mm / 1000.0) for me in meshes])
    gold = boolean("Gold", body, faces, "DIFFERENCE")
    black = boolean("Black", body, faces.copy(), "INTERSECT")

    xs = [v.co.x for v in gold.vertices]
    ys = [v.co.y for v in gold.vertices]
    real_width_mm = (max(xs) - min(xs)) * 1000.0
    scale = 1000.0 * (width_mm / real_width_mm if width_mm else 1.0)
    offset = (min(xs), min(ys))

    parts = []
    for part_name, colour, me in (("Gold", GOLD_COLOR, gold), ("Black", BLACK_COLOR, black)):
        verts, tris = triangles(me, scale, offset)
        parts.append((part_name, colour, verts, tris))
        write_stl(os.path.splitext(out)[0] + f"_{part_name.lower()}.stl", verts, tris)
    write_3mf(out, parts, f"{title} {name}")

    size = [(max(v[i] for v in parts[0][2]) - min(v[i] for v in parts[0][2])) for i in range(3)]
    print(f"[3mf] wrote {out}  size {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm")
    return out


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = dict(zip(argv[::2], argv[1::2]))
    return {
        "out": os.path.abspath(opts.get("--out", OUTPUT)),
        "width_mm": float(opts.get("--width", TARGET_WIDTH_MM)),
        "face_mm": float(opts.get("--face", FACE_THICKNESS_MM)),
        "title": opts.get("--title", plate.TITLE),
        "name": opts.get("--name", plate.NAME),
        "font": opts.get("--font"),
    }


if __name__ == "__main__":
    export(**parse_args())
