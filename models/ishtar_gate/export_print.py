"""
Build the Ishtar Gate, save the .blend, and write print files.

    python export_print.py [--render]

Needs the `bpy` pip module (Blender as a Python module) plus
`manifold3d` and `trimesh`.  Inside the Blender app you can instead run
ishtar_gate.py and use File > Export > STL.

Outputs (next to this file):
    ishtar_gate.blend            the scene, materials, camera, lights
    stl/ishtar_gate_full.stl     one watertight piece - single colour print
    stl/color_<NAME>.stl         one file per colour, non-overlapping,
                                 same origin - load together for AMS/MMU
    stl/part_<NAME>.stl          split parts (gate, wings, plaza, palms...)
    ishtar_gate_multicolor.3mf   all colours as one multi-part object
    renders/preview.png          (with --render)
"""

import os
import sys

import bpy
import bmesh
import numpy as np
import manifold3d as m3d
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ishtar_gate as ig  # noqa: E402

GROW = 0.01   # mm


def to_manifold(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    # Grow every part by a few microns so parts that exactly touch (a wall
    # standing on the floor, two stacked merlon steps) truly overlap and fuse
    # instead of leaving kissing edges that weld into non-manifold STL edges.
    bm.normal_update()
    for vv in bm.verts:
        vv.co += vv.normal * GROW
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.verts.index_update()
    v = np.array([vv.co[:] for vv in bm.verts], dtype=np.float32)
    f = np.array([[vv.index for vv in fc.verts] for fc in bm.faces],
                 dtype=np.uint32)
    bm.free()
    # An object may hold many overlapping closed shells (the boxes of a
    # band, the steps of a merlon...).  Manifold does not resolve overlaps
    # inside one mesh, so every shell becomes its own Manifold and they are
    # unioned properly.
    tm = trimesh.Trimesh(v, f, process=False)
    parts = []
    for s in tm.split(only_watertight=False):
        mm = m3d.Manifold(m3d.Mesh(
            vert_properties=np.asarray(s.vertices, np.float32),
            tri_verts=np.asarray(s.faces, np.uint32)))
        if mm.status() != m3d.Error.NoError:
            s.fix_normals()
            mm = m3d.Manifold(m3d.Mesh(
                vert_properties=np.asarray(s.vertices, np.float32),
                tri_verts=np.asarray(s.faces, np.uint32)))
        if mm.status() == m3d.Error.NoError and not mm.is_empty():
            if mm.volume() < 0:
                print("  !! inverted shell in", ob.name)
            parts.append(mm)
        else:
            print("  !! bad shell in", ob.name, mm.status())
    return union(parts)


def union(lst):
    lst = [x for x in lst if x is not None]
    if not lst:
        return None
    return m3d.Manifold.batch_boolean(lst, m3d.OpType.Add)


def to_trimesh(man):
    mesh = man.to_mesh()
    tm = trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3],
                         np.asarray(mesh.tri_verts), process=True)
    # drop zero-volume slivers that exact booleans can leave along seams
    keep = [b for b in tm.split(only_watertight=False)
            if len(b.faces) >= 8 and abs(b.volume) > 1e-3]
    return trimesh.util.concatenate(keep)


def main():
    render = "--render" in sys.argv
    ig.build_all()
    os.makedirs(os.path.join(HERE, "stl"), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "ishtar_gate.blend"),
                                compress=True)

    by_grp, by_coll = {}, {}
    for ob in bpy.data.objects:
        if ob.type != "MESH" or ob.get("grp", "NONE") == "NONE":
            continue
        man = to_manifold(ob)
        if man is None:
            print("  !! skipped", ob.name)
            continue
        by_grp.setdefault(ob["grp"], []).append(man)
        cname = ob.users_collection[0].name
        by_coll.setdefault(cname, []).append(man)

    grp = {k: union(v) for k, v in by_grp.items()}

    # full single-piece model
    full = union(list(grp.values()))
    t = to_trimesh(full)
    print("FULL: watertight=%s tris=%d bounds=%s" %
          (t.is_watertight, len(t.faces), np.round(t.bounds, 2).tolist()))
    t.export(os.path.join(HERE, "stl", "ishtar_gate_full.stl"))

    # colour bodies, higher priority carves lower priority
    final = {}
    higher = None
    for name in reversed(ig.PRIORITY):
        if name not in grp:
            continue
        body = grp[name]
        if higher is not None:
            body = body - higher
        final[name] = body
        higher = body if higher is None else higher + grp[name]
    # lapis dots print with the blue wall filament
    if "DOTS" in final:
        final["BLUE"] = final["BLUE"] + final.pop("DOTS")
    scene = trimesh.Scene()
    hexes = {}
    for name, body in final.items():
        if body.is_empty():
            continue
        tm = to_trimesh(body)
        rgba = ig.COLORS[name][0]
        col = (np.clip(np.array(rgba) ** (1 / 2.2), 0, 1) * 255).astype(np.uint8)
        tm.visual.face_colors = col
        hexes[name] = "#%02x%02x%02x" % tuple(col[:3])
        tm.export(os.path.join(HERE, "stl", "color_%s.stl" % name))
        scene.add_geometry(tm, node_name=name, geom_name=name)
        print("  colour %-7s tris=%7d vol=%9.1f mm3" %
              (name, len(tm.faces), body.volume()))
    scene.export(os.path.join(HERE, "ishtar_gate_multicolor.3mf"))

    for cname, lst in by_coll.items():
        u = union(lst)
        to_trimesh(u).export(os.path.join(HERE, "stl", "part_%s.stl" % cname))
        print("  part", cname)
    print("filament colours:", hexes)

    if render:
        os.makedirs(os.path.join(HERE, "renders"), exist_ok=True)
        from mathutils import Vector
        sc = bpy.context.scene
        cam = sc.camera
        shots = [("preview.png", None, None, None),
                 ("detail_gate.png", (-12, -125, 42), (-12, 22, 30), 50),
                 ("detail_wing.png", (-190, -150, 100), (-60, 0, 22), 50),
                 ("top_view.png", (0, -120, 420), (0, 0, 0), 35)]
        for fn, loc, tgt, lens in shots:
            if loc:
                cam.location = loc
                cam.data.lens = lens
                cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat(
                    "-Z", "Y").to_euler()
            sc.render.filepath = os.path.join(HERE, "renders", fn)
            bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
