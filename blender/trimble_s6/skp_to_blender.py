"""
SketchUp 2021+ (.skp) -> Blender converter, no SketchUp or SDK needed.
=====================================================================
A .skp from SketchUp 2021 or newer is a zip: materials/*/material.xml hold the
colours/textures and model.dat holds the geometry as a nested
tag-length-value stream (u16 tag, u32 length, payload).  The tags used here
were decoded from the file itself:

  505/6000/6001  component / group definitions -> 5500 (5502 = name)
  5000           entity list: 5001 vertices, 5002 edges, 5003 faces,
                 5005 instances
  2500           vertex   : 1500/1502 id, 2501 = x y z (float64, inches)
  3000           edge     : 3001 start vertex id, 3002 end vertex id
  3500           face     : 2000/2001 front material, 3503 back material,
                 3501 plane (a b c d), 3502/4500 loops -> 4501 -> 4000
                 edge uses (4001 edge id, 4002 reversed flag)
  6500           instance : 6502 = 3x3 axes + origin + scale, 6503 = definition
  503/12500/12501/13000  materials (13004 = name)
  502/5000       the model's top-level entities

Usage
  python skp_to_blender.py MODEL.skp OUT_DIR [--render]      (bpy module)
  blender -b -P skp_to_blender.py -- MODEL.skp OUT_DIR [--render]

Writes OUT_DIR/<name>.blend, .glb, .fbx, .obj and a 200 mm tall STL.
Geometry stays at real-world size (SketchUp inches -> metres).
"""

import math
import os
import re
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET

import bpy
import bmesh
from mathutils import Matrix, Vector, geometry

INCH = 0.0254


# --------------------------------------------------------------------------
#  TLV reader
# --------------------------------------------------------------------------
class Node:
    __slots__ = ("tag", "start", "length", "kids")

    def __init__(self, tag, start, length):
        self.tag, self.start, self.length, self.kids = tag, start, length, None

    def child(self, tag):
        for k in self.kids or ():
            if k.tag == tag:
                return k
        return None

    def children(self, tag):
        return [k for k in (self.kids or ()) if k.tag == tag]


def _parse(d, off, end):
    out = []
    o = off
    while o < end:
        if o + 6 > end:
            return None
        tag, ln = struct.unpack_from("<HI", d, o)
        if o + 6 + ln > end:
            return None
        out.append(Node(tag, o + 6, ln))
        o += 6 + ln
    return out


def build_tree(d, off=0, end=None, depth=0):
    nodes = _parse(d, off, len(d) if end is None else end)
    if nodes is None:
        return None
    for n in nodes:
        if n.length >= 6 and depth < 48:
            n.kids = build_tree(d, n.start, n.start + n.length, depth + 1)
    return nodes


class Model:
    def __init__(self, path):
        self.zip = zipfile.ZipFile(path)
        self.d = self.zip.read("model.dat")
        self.tree = build_tree(self.d)
        if not self.tree or self.tree[0].tag != 500:
            raise ValueError("not a SketchUp 2021+ model.dat")
        self.root = self.tree[0]

    # leaf decoders
    def raw(self, n):
        return self.d[n.start:n.start + n.length]

    def int(self, n):
        return int.from_bytes(self.raw(n), "little") if n else None

    def doubles(self, n):
        return struct.unpack("<%dd" % (n.length // 8), self.raw(n))

    def eid(self, n):
        """Entity id stored in <n>/2000/1500/1502 or <n>/1500/1502."""
        base = n.child(2000) or n
        b = base.child(1500)
        return self.int(b.child(1502)) if b else None

    def section(self, tag):
        return self.root.child(tag)

    # materials ----------------------------------------------------------
    def materials(self):
        xml = {}
        for name in self.zip.namelist():
            if name.endswith("material.xml"):
                root = ET.fromstring(self.zip.read(name))
                m = root[0]
                a = m.attrib
                tex = None
                for t in m:
                    if t.tag.endswith("texture"):
                        tex = os.path.dirname(name) + "/" + t.attrib.get("textureFilename", "")
                xml[a["name"]] = dict(
                    rgb=(int(a["colorRed"]), int(a["colorGreen"]), int(a["colorBlue"])),
                    alpha=float(a.get("trans", 1.0)) if a.get("useTrans", "0") == "1" or float(a.get("trans", 1)) < 1 else 1.0,
                    texture=tex)
        out = {}
        sec = self.section(503)
        for m in sec.kids[0].kids[0].kids if sec else ():
            nm = self.raw(m.child(13004)).decode("utf-8", "replace")
            out[self.eid(m)] = (nm, xml.get(nm, dict(rgb=(200, 200, 200), alpha=1.0, texture=None)))
        return out

    # entities -------------------------------------------------------------
    def definitions(self):
        defs = {}
        sec = self.section(505)
        for lst in sec.kids if sec else ():
            for d6001 in lst.kids:
                d5500 = d6001.child(5500)
                ents = d5500.child(5000)
                name = self.raw(d5500.child(5502)).decode("utf-8", "replace")
                defs[self.eid(ents)] = (name, ents)
        return defs

    def mesh_data(self, ents):
        verts, vidx = [], {}
        for v in (ents.child(5001).kids if ents.child(5001) else ()):
            vidx[self.eid(v)] = len(verts)
            verts.append(Vector(self.doubles(v.child(2501))) * INCH)
        edges = {}
        for e in (ents.child(5002).kids if ents.child(5002) else ()):
            edges[self.eid(e)] = (self.int(e.child(3001)), self.int(e.child(3002)))
        faces = []
        for f in (ents.child(5003).kids if ents.child(5003) else ()):
            front = self.int((f.child(2000) or f).child(2001))
            back = self.int(f.child(3503))
            plane = Vector(self.doubles(f.child(3501))[:3])
            loops = []
            for lp in f.child(3502).kids:
                seq = []
                for use in lp.child(4501).kids:
                    a, b = edges[self.int(use.child(4001))]
                    seq.append(vidx[b if self.int(use.child(4002)) else a])
                loops.append(seq)
            faces.append(dict(loops=loops, front=front, back=back, normal=plane))
        return verts, faces

    def instances(self, ents):
        out = []
        for grp in ents.children(5005):
            for n7500 in grp.kids:
                for inst in n7500.kids:
                    t = self.doubles(inst.child(6502))
                    ref = self.int(inst.child(6503))
                    out.append((ref, t))
        return out


def skp_matrix(t):
    """6502: x-axis, y-axis, z-axis (rows of the rotation), origin, scale."""
    M = Matrix(((t[0], t[1], t[2], t[9] * INCH),
                (t[3], t[4], t[5], t[10] * INCH),
                (t[6], t[7], t[8], t[11] * INCH),
                (0, 0, 0, 1)))
    if len(t) > 12 and t[12] not in (0.0, 1.0):
        M = M @ Matrix.Scale(1.0 / t[12], 4)
    return M


# --------------------------------------------------------------------------
#  Blender side
# --------------------------------------------------------------------------
def srgb_to_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def make_material(name, info, zf, tex_dir):
    m = bpy.data.materials.new(name.strip("[]"))
    if bpy.app.version < (5, 0, 0):
        m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    r, g, b = info["rgb"]
    col = (srgb_to_lin(r), srgb_to_lin(g), srgb_to_lin(b), 1.0)
    bsdf.inputs["Base Color"].default_value = col
    bsdf.inputs["Roughness"].default_value = 0.45
    m.diffuse_color = col
    low = name.lower()
    if "metal" in low:
        bsdf.inputs["Metallic"].default_value = 0.8
        bsdf.inputs["Roughness"].default_value = 0.35
    if "water" in low or info["alpha"] < 1.0:           # lenses / glass
        bsdf.inputs["Roughness"].default_value = 0.03
        if "Coat Weight" in bsdf.inputs:
            bsdf.inputs["Coat Weight"].default_value = 1.0
        if info["alpha"] < 1.0 and "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = 1.0 - info["alpha"]
    if info.get("texture") and info["texture"] in zf.namelist() and "metal" not in low:
        os.makedirs(tex_dir, exist_ok=True)
        p = os.path.join(tex_dir, os.path.basename(info["texture"]))
        with open(p, "wb") as fh:
            fh.write(zf.read(info["texture"]))
    return m


def build_mesh(name, verts, faces, matmap, mat_slots):
    bm = bmesh.new()
    bv = [bm.verts.new(v) for v in verts]
    bm.verts.ensure_lookup_table()
    slot_of = {}
    skipped = 0
    for f in faces:
        mid = f["front"] if f["front"] is not None else f["back"]
        flip = f["front"] is None and f["back"] is not None    # painted on the back -> back faces out
        key = mid if mid in matmap else None
        if key not in slot_of:
            slot_of[key] = len(mat_slots)
            mat_slots.append(matmap.get(key))
        slot = slot_of[key]
        n = f["normal"] * (-1 if flip else 1)
        loops = [[i for k, i in enumerate(lp) if i != lp[k - 1]] for lp in f["loops"]]
        loops = [lp for lp in loops if len(lp) >= 3]
        if not loops:
            skipped += 1
            continue
        if len(loops) == 1:
            seq = loops[0]
            if geometry.normal([verts[i] for i in seq]).dot(n) < 0:
                seq = seq[::-1]
            try:
                face = bm.faces.new([bv[i] for i in seq])
                face.material_index = slot
            except ValueError:
                skipped += 1
            continue
        # face with holes -> tessellate outer + inner loops
        pts = [[verts[i] for i in lp] for lp in loops]
        flat = [i for lp in loops for i in lp]
        for tri in geometry.tessellate_polygon(pts):
            ids = [flat[k] for k in tri]
            if len(set(ids)) < 3:
                continue
            if geometry.normal([verts[i] for i in ids]).dot(n) < 0:
                ids = ids[::-1]
            try:
                face = bm.faces.new([bv[i] for i in ids])
                face.material_index = slot
            except ValueError:
                skipped += 1
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    for fc in bm.faces:
        fc.smooth = True
    for e in bm.edges:                                          # SketchUp-style smoothing
        e.smooth = e.is_manifold and e.calc_face_angle(0) <= math.radians(35)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me, skipped


def convert(skp_path):
    model = Model(skp_path)
    tex_dir = os.path.join(os.path.dirname(os.path.abspath(skp_path)), "textures")
    mats = {mid: make_material(nm, info, model.zip, tex_dir)
            for mid, (nm, info) in model.materials().items()}
    default = bpy.data.materials.new("SketchUp_Default")
    default.diffuse_color = (0.9, 0.9, 0.9, 1)
    if bpy.app.version < (5, 0, 0):
        default.use_nodes = True
    default.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1)
    mats[None] = default

    defs = model.definitions()
    coll = bpy.data.collections.new(os.path.splitext(os.path.basename(skp_path))[0])
    bpy.context.scene.collection.children.link(coll)
    meshes, objs = {}, []

    def place(ents, M, depth=0):
        for ref, t in model.instances(ents):
            if ref not in defs or depth > 16:
                continue
            name, sub = defs[ref]
            Mi = M @ skp_matrix(t)
            if ref not in meshes:
                verts, faces = model.mesh_data(sub)
                slots = []
                me, skipped = build_mesh(name, verts, faces, mats, slots)
                for s in slots:
                    me.materials.append(s or default)
                meshes[ref] = me
                print(f"[skp] {name}: {len(verts)} verts, {len(faces)} faces, "
                      f"{len(me.polygons)} polygons, skipped {skipped}", flush=True)
            if len(meshes[ref].polygons):
                ob = bpy.data.objects.new(name, meshes[ref])
                ob.matrix_world = Mi
                coll.objects.link(ob)
                objs.append(ob)
            place(sub, Mi, depth + 1)

    top = model.section(502).child(5000)
    verts, faces = model.mesh_data(top)
    if faces:
        slots = []
        me, _ = build_mesh("Model_Loose", verts, faces, mats, slots)
        for s in slots:
            me.materials.append(s or default)
        ob = bpy.data.objects.new("Model_Loose", me)
        coll.objects.link(ob)
        objs.append(ob)
    place(top, Matrix.Identity(4))
    return coll, objs


def ground_and_center(objs):
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    shift = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    for o in objs:
        o.matrix_world = Matrix.Translation(-shift) @ o.matrix_world
    return hi - lo


def stage(height):
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    if bpy.app.version < (5, 0, 0):
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.75, 0.74, 0.72, 1)
    bg.inputs["Strength"].default_value = 0.35
    floor = bpy.data.meshes.new("Floor")
    s = height * 8
    floor.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    fo = bpy.data.objects.new("Floor", floor)
    fm = bpy.data.materials.new("Floor_Grey")
    fm.diffuse_color = (0.6, 0.6, 0.6, 1)
    if bpy.app.version < (5, 0, 0):
        fm.use_nodes = True
    fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.45, 0.44, 0.42, 1)
    floor.materials.append(fm)
    sc.collection.objects.link(fo)
    for nm, loc, e in (("Key", (-1.2, -1.0, 1.6), 110), ("Fill", (1.4, -0.6, 0.9), 30),
                       ("Rim", (0.4, 1.4, 1.8), 60)):
        ld = bpy.data.lights.new(nm, 'AREA')
        ld.energy = e * height ** 2
        ld.size = height * 0.8
        ob = bpy.data.objects.new(nm, ld)
        ob.location = Vector(loc) * height
        ob.rotation_euler = (Vector((0, 0, height * 0.55)) - ob.location).to_track_quat('-Z', 'Y').to_euler()
        sc.collection.objects.link(ob)
    cams = {}
    for nm, loc, tz, lens in (("Cam_Full", (1.25, -2.0, 0.85), 0.5, 50),
                              ("Cam_Head", (0.35, -0.55, 1.08), 0.93, 50)):
        cd = bpy.data.cameras.new(nm)
        cd.lens = lens
        ob = bpy.data.objects.new(nm, cd)
        ob.location = Vector(loc) * height
        ob.rotation_euler = (Vector((0, 0, tz * height)) - ob.location).to_track_quat('-Z', 'Y').to_euler()
        sc.collection.objects.link(ob)
        cams[nm] = ob
    sc.camera = cams["Cam_Full"]
    return fo, cams


def export_all(objs, out_dir, base, height):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=os.path.join(out_dir, base + ".glb"),
                              use_selection=True, export_format='GLB')
    bpy.ops.export_scene.fbx(filepath=os.path.join(out_dir, base + ".fbx"),
                             use_selection=True, apply_unit_scale=True)
    bpy.ops.wm.obj_export(filepath=os.path.join(out_dir, base + ".obj"),
                          export_selected_objects=True, export_materials=True)
    # 200 mm tall print version (same proportions as the photo-matched model)
    bpy.ops.wm.stl_export(filepath=os.path.join(out_dir, base + "_200mm.stl"),
                          export_selected_objects=True, global_scale=200.0 / (height * 1000.0) * 1000.0)


def render(out_dir, cams, samples=64):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = 'Standard'
    sc.render.resolution_x, sc.render.resolution_y = 1000, 1250
    os.makedirs(out_dir, exist_ok=True)
    for nm, cam in cams.items():
        sc.camera = cam
        sc.render.filepath = os.path.join(out_dir, nm[4:].lower() + ".png")
        bpy.ops.render.render(write_still=True)
        print("[skp] rendered", sc.render.filepath, flush=True)
    sc.camera = cams["Cam_Full"]


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return
    skp, out_dir = argv[0], argv[1]
    os.makedirs(out_dir, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    coll, objs = convert(skp)
    size = ground_and_center(objs)
    print(f"[skp] size: {size.x:.3f} x {size.y:.3f} x {size.z:.3f} m", flush=True)
    base = re.sub(r"[^A-Za-z0-9_]+", "_", coll.name).strip("_")
    floor, cams = stage(size.z)
    if "--render" in argv:
        render(os.path.join(out_dir, "renders"), cams, int(os.environ.get("SKP_SAMPLES", "64")))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(os.path.join(out_dir, base + ".blend")))
    export_all(objs, out_dir, base, size.z)
    print("[skp] wrote", out_dir, flush=True)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(args)
