# -*- coding: utf-8 -*-
"""
Print-ready top signs (1G ... 5G) as 3MF files, one per generation.

Each sign is a FLAT disc (no raised parts) made of three parts whose top
faces are all flush at the same height, so the slicer keeps every part
and prints the text as a colour change in the top layers:
  * Ring  - full disc body (column colour), with a hole for the pin
  * Face  - 1 mm inlay in the centre (white)
  * Text  - 1 mm inlay of the label cut into the face (black)
A separate Pin (6 mm) joins the disc to the top of its column panel.

Run:  blender -b -P make_sign_3mf.py
      (or with the bpy Python module: python make_sign_3mf.py)
"""
import bpy
import bmesh
import math
import os
import zipfile
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(HERE, "..", "DejaVuSans-Bold.ttf")

DIAMETER = 100.0       # mm
THICK = 10.0           # mm, disc thickness
FACE_D = 81.0          # mm, white face diameter
INLAY = 1.0            # mm, depth of the face/text colour layers (5 layers @ 0.2)
TEXT_SIZE = 41.0       # mm, font size of the label
PIN_D = 6.0            # mm, pin diameter
HOLE_D = 6.3           # mm, hole for the pin (0.3 mm clearance)
HOLE_DEPTH = 15.0      # mm
PIN_LEN = 30.0         # mm
SEG = 160
TEXT_RES = 24          # curve resolution of the glyphs

SIGNS = [("1G", "#353537"), ("2G", "#1452C4"), ("3G", "#138A3A"),
         ("4G", "#EA6410"), ("5G", "#6A2FB8")]
FACE_COLOR, TEXT_COLOR = "#F7F7F5", "#0A0A0A"


def clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for blk in (bpy.data.meshes, bpy.data.curves):
        for d in list(blk):
            blk.remove(d)


def cylinder(name, r, z0, z1, axis="Z", center=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=SEG,
                          radius1=r, radius2=r, depth=z1 - z0)
    bmesh.ops.translate(bm, vec=Vector((0, 0, (z0 + z1) / 2)), verts=bm.verts)
    if axis == "Y":
        from mathutils import Matrix
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(-90), 3, "X"),
                         verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def text_solid(name, label, z0, z1, font):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = label
    cu.font = font
    cu.size = TEXT_SIZE
    cu.extrude = (z1 - z0) / 2
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.resolution_u = TEXT_RES
    ob = bpy.data.objects.new(name + "_curve", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob, do_unlink=True)
    # centre the glyphs exactly on the disc and place between z0..z1
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    off = Vector((-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, (z0 + z1) / 2))
    for v in me.vertices:
        v.co += off
    tob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(tob)
    return tob


def subtract(target, cutter, use_self=False):
    mod = target.modifiers.new("bool", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.use_self = use_self      # needed when the cutter's glyph shells touch each other
    mod.object = cutter
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(target.evaluated_get(dg))
    target.modifiers.clear()
    target.data = me
    bpy.data.objects.remove(cutter, do_unlink=True)


def tri_data(ob, merge=1e-4):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    if merge:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bad = [e for e in bm.edges if not e.is_manifold]
    verts = [tuple(v.co) for v in bm.verts]
    idx = {v: i for i, v in enumerate(bm.verts)}
    tris = [tuple(idx[v] for v in f.verts) for f in bm.faces]
    bm.free()
    return verts, tris, len(bad)


def mesh_xml(verts, tris):
    v = "".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in verts)
    t = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris)
    return f"<mesh><vertices>{v}</vertices><triangles>{t}</triangles></mesh>"


def write_3mf(path, sign_name, parts, pin, plate=(128.0, 128.0), positions=None,
              extra_name="Pin", extra_color=None):
    """parts: [(name, colour, verts, tris)] -> one object made of parts; pin: extra object.
    positions: optional ((x, y) of the parts object, (x, y) of the extra object) on the bed"""
    res = ['<basematerials id="1">']
    res += [f'<base name="{n}" displaycolor="{c}FF"/>' for n, c, _, _ in parts]
    res += [f'<base name="{extra_name}" displaycolor="{extra_color or parts[0][1]}FF"/>',
            "</basematerials>"]
    oid = 2
    comp_ids = []
    for i, (n, c, v, t) in enumerate(parts):
        res.append(f'<object id="{oid}" type="model" pid="1" pindex="{i}" name="{n}">'
                   f'{mesh_xml(v, t)}</object>')
        comp_ids.append(oid)
        oid += 1
    sign_id = oid
    comps = "".join(f'<component objectid="{i}"/>' for i in comp_ids)
    res.append(f'<object id="{sign_id}" type="model" name="{sign_name}">'
               f'<components>{comps}</components></object>')
    px, py = plate
    if pin is None:
        build = f'<item objectid="{sign_id}" transform="1 0 0 0 1 0 0 0 1 {px:.1f} {py:.1f} 0"/>'
    else:
        pin_id = sign_id + 1
        res.append(f'<object id="{pin_id}" type="model" pid="1" pindex="{len(parts)}" '
                   f'name="{extra_name}">'
                   f'{mesh_xml(*pin)}</object>')
        (ax, ay), (bx, by) = positions or ((px - 12, py), (px + 50, py))
        build = (f'<item objectid="{sign_id}" transform="1 0 0 0 1 0 0 0 1 {ax:.1f} {ay:.1f} 0"/>'
                 f'<item objectid="{pin_id}" transform="1 0 0 0 1 0 0 0 1 {bx:.1f} {by:.1f} 0"/>')
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             f'<metadata name="Title">{sign_name}</metadata>'
             f'<resources>{"".join(res)}</resources><build>{build}</build></model>')
    ctypes = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
              '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
            '</Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)


def build_sign(label, ring_color, font):
    clear()
    top = THICK
    # ring/body: full disc minus the inlay pocket and the pin hole
    ring = cylinder("Ring", DIAMETER / 2, 0.0, top)
    subtract(ring, cylinder("pocket", FACE_D / 2, top - INLAY, top + 1.0))
    subtract(ring, cylinder("pin_hole", HOLE_D / 2, 0.0, HOLE_DEPTH + 1.0, axis="Y",
                            center=(0, -DIAMETER / 2 - 1.0, THICK / 2)))
    # face: inlay disc minus the text
    face = cylinder("Face", FACE_D / 2, top - INLAY, top)
    subtract(face, text_solid("text_cut", label, top - INLAY - 0.2, top + 0.2, font))
    # text: same depth, flush with the face
    txt = text_solid("Text", label, top - INLAY, top, font)
    parts = []
    for name, col, ob in (("Ring", ring_color, ring), ("Face", FACE_COLOR, face),
                          ("Text", TEXT_COLOR, txt)):
        v, t, bad = tri_data(ob)
        print(f"  {label} {name}: {len(t)} triangles, non-manifold edges = {bad}")
        parts.append((name, col, v, t))
    # pin lies flat on the bed
    pin = cylinder("Pin", PIN_D / 2, 0.0, PIN_LEN, axis="Y", center=(0, -PIN_LEN / 2, 0))
    pv, pt, _ = tri_data(pin)
    pv = [(x, y, z + PIN_D / 2) for x, y, z in pv]
    out = os.path.join(HERE, f"sign_{label}.3mf")
    write_3mf(out, f"Sign_{label}", parts, (pv, pt))
    print("saved", out)


if __name__ == "__main__":
    font = bpy.data.fonts.load(os.path.abspath(FONT_PATH), check_existing=True)
    for label, col in SIGNS:
        build_sign(label, col, font)
