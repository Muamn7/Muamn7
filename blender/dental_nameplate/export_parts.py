"""
Export every part of the nameplate model for 3D printing, at real size in mm.

Writes into a `print_parts` folder next to this script:
  - one STL per part, each standing on z = 0
  - nameplate_parts.3mf with all parts in their assembled positions, one
    object per part, coloured gold / white / black / marble

The letters print best from letters.3mf (export_letters_3mf.py), which splits
the black faces from the gold bodies.

Usage: Scripting tab -> Run Script, or
    blender -b -P export_parts.py
"""

import bpy  # noqa: F401  (must be imported before bmesh when bpy runs as a module)

import os
import re
import sys

import bmesh


def _script_dir():
    here = globals().get("__file__")
    if here and os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(here)), "dental_nameplate.py")):
        return os.path.dirname(os.path.abspath(here))
    for text in bpy.data.texts:
        if text.filepath and os.path.basename(text.filepath) == "export_parts.py":
            return os.path.dirname(bpy.path.abspath(text.filepath))
    raise RuntimeError("Put export_parts.py next to dental_nameplate.py")


HERE = _script_dir()
sys.path.insert(0, HERE)
import dental_nameplate as plate  # noqa: E402
from export_letters_3mf import write_3mf, write_stl  # noqa: E402

OUT_DIR = os.path.join(HERE, "print_parts")

COLOURS = {
    "Gold": "#D4A94AFF",
    "Enamel": "#F2EFE8FF",
    "Black": "#111111FF",
    "Marble": "#E6E6E3FF",
    "Mirror": "#C8CCD0FF",
}


def colour_of(obj):
    name = obj.data.materials[0].name if obj.data.materials else ""
    for key in ("Enamel", "Black", "Marble", "Mirror"):
        if key in name:
            return key
    return "Gold"


def world_triangles(obj, depsgraph):
    """Triangles of the object with its modifiers (bevels) applied, in mm, world space."""
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
    me.transform(obj.matrix_world)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.verts.index_update()
    verts = [tuple(c * 1000.0 for c in v.co) for v in bm.verts]
    tris = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    bpy.data.meshes.remove(me)
    return verts, tris


def export(out_dir=OUT_DIR):
    plate.build()
    os.makedirs(out_dir, exist_ok=True)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    plate_coll = bpy.data.collections["Nameplate"]

    parts = []
    for obj in sorted(plate_coll.objects, key=lambda o: o.name):
        if obj.type != "MESH":
            continue
        verts, tris = world_triangles(obj, depsgraph)
        parts.append((obj.name, COLOURS[colour_of(obj)], verts, tris))
        z0 = min(v[2] for v in verts)
        slug = re.sub(r"[^a-z0-9]+", "_", obj.name.lower()).strip("_")
        write_stl(os.path.join(out_dir, slug + ".stl"), [(x, y, z - z0) for x, y, z in verts], tris)

    write_3mf(os.path.join(out_dir, "nameplate_parts.3mf"), parts, "Dental nameplate")
    print(f"[parts] wrote {len(parts)} STL files and nameplate_parts.3mf to {out_dir}")
    return out_dir


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    export(os.path.abspath(argv[argv.index("--out") + 1]) if "--out" in argv else OUT_DIR)
