# -*- coding: utf-8 -*-
"""
طقم طباعة ثلاثية الأبعاد لنموذجي BCC و HCP — ارتفاع كل مجسم 15 سم.

كل ذرة تُطبع نصفين (الوجه المسطح على السرير، بدون دعامات)، ثم تُلصق.
الثقوب في الذرات تستقبل القضبان. الثقوب الأفقية تقع على خط القص فتظهر
كنصف مجرى في كل نصف، وتصبح ثقباً كاملاً بعد اللصق.
في مركز كل نصف ثقب صغير لدبوس من خيط طباعة 1.75 مم لمحاذاة النصفين.

التشغيل:
  blender -b -P crystal_print_kit.py -- --out .  [--render]
أو داخل Blender: Scripting -> Run Script (يبني المشهد فقط).

كل الأرقام بالمليمتر (1 وحدة = 1 مم).
"""
import bpy
import bmesh
import math
import os
import struct
import sys
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

# ======================================================= الإعدادات (مم)
TOTAL_HEIGHT = 150.0          # الارتفاع الكلي لكل مجسم بعد التركيب

# BCC: نفس نِسَب جدول المقاسات (ضلع 20، ذرة زاوية 3، مركزية 3.5) مصغّرة
_k = TOTAL_HEIGHT / (200.0 + 30.0)
BCC_EDGE = 200.0 * _k         # 130.4 مم مركز-مركز
BCC_CORNER_D = 30.0 * _k      # 19.6 مم
BCC_CENTER_D = 35.0 * _k      # 22.8 مم

# HCP: c/a = 1.633 وقطر الذرة = 0.3a
HCP_A = TOTAL_HEIGHT / (1.633 + 0.3)   # 77.6 مم
HCP_C = 1.633 * HCP_A                  # 126.7 مم
HCP_D = 0.3 * HCP_A                    # 23.3 مم

ROD_D = 5.0          # قطر القضيب
HOLE_CLEAR = 0.3     # خلوص الثقب (ثقب 5.3 مم) — زِده إلى 0.4 إن كان الإدخال صعباً
INSERT = 4.0         # عمق دخول القضيب في الذرة
GLUE_GAP = 0.4       # فراغ إضافي في قاع الثقب للغراء
ROD_CHAMFER = 0.5    # شطف طرف القضيب لسهولة الإدخال
ROD_FLAT = 0.4       # سطح مستوٍ أسفل القضيب ليثبت على السرير
PIN_D = 1.9          # ثقب دبوس المحاذاة (لقطعة خيط 1.75 مم)
PIN_DEPTH = 3.0

BED = 200.0          # مساحة الصف المضمونة (تناسب أسرّة 220×220 فأكبر)
SPH_U, SPH_V = 96, 48
ROD_SEG = 48

# ======================================================= أدوات الشبكات


def finish(bm, name):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    return me


def hemisphere(r, upper=True):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=SPH_U, v_segments=SPH_V, radius=r)
    n = (0, 0, 1) if upper else (0, 0, -1)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                           plane_co=(0, 0, 0), plane_no=n, clear_inner=True)
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for f in bm.faces:
        f.smooth = abs(f.normal.z) < 0.999
    return finish(bm, "hemi")


def cylinder(radius, z0, z1, seg=ROD_SEG, twist=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                          radius1=radius, radius2=radius, depth=z1 - z0)
    # تدوير نصف قطعة حتى لا يقع رأس على مستوى القص (يحمي عملية Boolean)
    rot = Matrix.Rotation(math.pi / seg if twist else 0, 4, 'Z')
    bmesh.ops.transform(bm, matrix=Matrix.Translation((0, 0, (z0 + z1) / 2)) @ rot, verts=bm.verts)
    return bm


def rod_mesh(length, name):
    """قضيب ممدد على محور X، أسفله مستوٍ، وطرفاه مشطوفان. يبدأ من x=0."""
    r = ROD_D / 2
    prof = [(0.0, r - ROD_CHAMFER), (ROD_CHAMFER, r), (length - ROD_CHAMFER, r), (length, r - ROD_CHAMFER)]
    bm = bmesh.new()
    rings = []
    for x, rad in prof:
        ring = []
        for i in range(ROD_SEG):
            t = 2 * math.pi * (i + 0.5) / ROD_SEG
            ring.append(bm.verts.new((x, rad * math.cos(t), rad * math.sin(t))))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for i in range(ROD_SEG):
            j = (i + 1) % ROD_SEG
            f = bm.faces.new((a[i], a[j], b[j], b[i]))
            f.smooth = True
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    zmin = -r + ROD_FLAT
    for v in bm.verts:            # سطح مستوٍ أسفل القضيب
        if v.co.z < zmin:
            v.co.z = zmin
    for v in bm.verts:
        v.co.z -= zmin
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return finish(bm, name)


def apply_booleans(ob, cutters):
    for i, c in enumerate(cutters):
        m = ob.modifiers.new("cut%d" % i, 'BOOLEAN')
        m.operation = 'DIFFERENCE'
        m.solver = 'MANIFOLD'
        m.object = c
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)
    return me


# ======================================================= الذرات


def atom_halves(name, r, dirs, scratch):
    """يبني نصفي ذرة (في إطار الذرة) مع ثقوب في الاتجاهات dirs."""
    cutters = []
    s0 = r - INSERT - GLUE_GAP
    for d in dirs:
        bm = cylinder((ROD_D + HOLE_CLEAR) / 2, s0, r + 2.0)
        q = Vector((0, 0, 1)).rotation_difference(d)
        bmesh.ops.transform(bm, matrix=q.to_matrix().to_4x4(), verts=bm.verts)
        c = bpy.data.objects.new("cutter", finish(bm, "cutter"))
        scratch.objects.link(c)
        cutters.append(c)
    bm = cylinder(PIN_D / 2, -PIN_DEPTH, PIN_DEPTH, seg=24)
    pin = bpy.data.objects.new("pin", finish(bm, "pin"))
    scratch.objects.link(pin)
    cutters.append(pin)

    halves = {}
    for upper in (True, False):
        ob = bpy.data.objects.new("%s_%s" % (name, "U" if upper else "L"), hemisphere(r, upper))
        scratch.objects.link(ob)
        apply_booleans(ob, cutters)
        scratch.objects.unlink(ob)
        halves[upper] = ob
    for c in cutters:
        bpy.data.objects.remove(c)
    return halves


FLIP = Matrix.Rotation(math.pi, 4, 'X')   # النصف السفلي يُقلب ليصبح وجهه المسطح للأسفل


def half_signature(r, dirs, upper):
    """بصمة النصف في وضع الطباعة — لتجميع الأنصاف المتطابقة (بالتدوير حول Z)."""
    pts = []
    for d in dirs:
        v = Vector(d) if upper else (FLIP.to_3x3() @ Vector(d))
        if v.z < -1e-6:
            continue
        el = math.degrees(math.asin(max(-1, min(1, v.z))))
        if el > 89.9:                     # ثقب عمودي: لا اتجاه أفقي له
            pts.append((None, 90.0))
            continue
        az = math.degrees(math.atan2(v.y, v.x))
        pts.append((az, round(el, 1)))
    if not pts:
        return (round(r, 2), ())
    refs = [az for az, _ in pts if az is not None] or [0.0]
    best = None
    for az0 in refs:
        s = tuple(sorted(((-1.0 if az is None else round((az - az0) % 360.0, 1) % 360.0), el)
                         for az, el in pts))
        if best is None or s < best:
            best = s
    return (round(r, 2), best)


# ======================================================= الهياكل


def bcc_layout():
    e = BCC_EDGE
    rc, rz = BCC_CORNER_D / 2, BCC_CENTER_D / 2
    z0 = e / 2 + rc
    C = Vector((0, 0, z0))
    atoms = {"Center": (C, rz)}
    for ix in (-1, 1):
        for iy in (-1, 1):
            for iz in (-1, 1):
                atoms["Corner%+d%+d%+d" % (ix, iy, iz)] = (C + Vector((ix, iy, iz)) * e / 2, rc)
    bonds = []
    keys = [k for k in atoms if k != "Center"]
    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1:]:
            if (atoms[k1][0] - atoms[k2][0]).length < e * 1.01:
                bonds.append((k1, k2, "edge"))
    for k in keys:
        bonds.append(("Center", k, "diag"))
    return atoms, bonds


def hcp_layout():
    a, c, r = HCP_A, HCP_C, HCP_D / 2
    zb, zt, zm = r, r + c, r + c / 2
    names = {0: "R", 60: "BR", 120: "BL", 180: "L", 240: "FL", 300: "FR"}
    atoms = {}
    for tag, z in (("Top", zt), ("Bot", zb)):
        atoms["%s_C" % tag] = (Vector((0, 0, z)), r)
        for deg, nm in names.items():
            t = math.radians(deg)
            atoms["%s_%s" % (tag, nm)] = (Vector((a * math.cos(t), a * math.sin(t), z)), r)
    mids = {}
    for deg, nm in ((90, "B"), (210, "FL"), (330, "FR")):
        t = math.radians(deg)
        mids[nm] = "Mid_%s" % nm
        atoms["Mid_%s" % nm] = (Vector((a / math.sqrt(3) * math.cos(t), a / math.sqrt(3) * math.sin(t), zm)), r)
    order = ["R", "BR", "BL", "L", "FL", "FR"]
    cell = {frozenset(p) for p in (("C", "FL"), ("FL", "FR"), ("FR", "R"), ("R", "C"))}
    cell_v = {"C", "FL", "FR", "R"}
    bonds = []
    for tag in ("Top", "Bot"):
        for i, nm in enumerate(order):
            nx = order[(i + 1) % 6]
            col = "yellow" if frozenset((nm, nx)) in cell else "grey"
            bonds.append(("%s_%s" % (tag, nm), "%s_%s" % (tag, nx), "short_" + col))
            col = "yellow" if frozenset(("C", nm)) in cell else "grey"
            bonds.append(("%s_C" % tag, "%s_%s" % (tag, nm), "short_" + col))
    for nm in ["C"] + order:
        col = "yellow" if nm in cell_v else "grey"
        bonds.append(("Bot_%s" % nm, "Top_%s" % nm, "long_" + col))
    mk = list(mids.values())
    for i in range(3):
        bonds.append((mk[i], mk[(i + 1) % 3], "short_grey"))
    for m in mk:
        bonds.append((m, "Top_C", "short_grey"))
        bonds.append((m, "Bot_C", "short_grey"))
    return atoms, bonds


def rod_length(p1, r1, p2, r2):
    return (p2 - p1).length - (r1 - INSERT) - (r2 - INSERT)


# ======================================================= المواد


def mat(name, color, metallic=0.0, rough=0.4, transmission=0.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    b.inputs["Transmission Weight"].default_value = transmission
    m.diffuse_color = (*color, 1)
    return m


# ======================================================= البناء


class Kit:
    def __init__(self, label, atoms, bonds, atom_mat, rod_mats, origin):
        self.label, self.atoms, self.bonds = label, atoms, bonds
        self.atom_mat, self.rod_mats, self.origin = atom_mat, rod_mats, Vector(origin)
        self.halves = []     # (sig, mesh_print, atom_key, upper)
        self.rods = []       # (kind, length, mesh)
        self.types = {}      # sig -> type name


def build_kit(kit, root, scratch):
    asm = bpy.data.collections.new(kit.label + "_Assembled")
    root.children.link(asm)
    dirs = {k: [] for k in kit.atoms}
    for k1, k2, kind in kit.bonds:
        p1, p2 = kit.atoms[k1][0], kit.atoms[k2][0]
        dirs[k1].append((p2 - p1).normalized())
        dirs[k2].append((p1 - p2).normalized())

    # أنصاف الذرات
    for key, (p, r) in kit.atoms.items():
        hv = atom_halves(key, r, dirs[key], scratch)
        for upper, ob in hv.items():
            sig = half_signature(r, dirs[key], upper)
            ob.data.materials.clear()
            pm = ob.data.copy()
            pm.name = "%s_%s_%s_print" % (kit.label, key, "U" if upper else "L")
            if not upper:
                pm.transform(FLIP)
            kit.halves.append((sig, pm, key, upper))
            ob.data.materials.clear()
            ob.data.materials.append(kit.atom_mat)
            ob.location = kit.origin + p
            ob.name = "%s_Atom_%s_%s" % (kit.label, key, "Upper" if upper else "Lower")
            asm.objects.link(ob)

    # القضبان
    lengths = {}
    for k1, k2, kind in kit.bonds:
        (p1, r1), (p2, r2) = kit.atoms[k1], kit.atoms[k2]
        L = round(rod_length(p1, r1, p2, r2), 2)
        lengths.setdefault(kind, L)
        me = rod_mesh(L, "%s_Rod_%s" % (kit.label, kind))
        me.materials.append(kit.rod_mats[kind.split("_")[-1]])
        kit.rods.append((kind, L, me))
        # في المجسم المركّب: محور القضيب يمر بمركزي الذرتين
        d = (p2 - p1).normalized()
        start = p1 + d * (r1 - INSERT)
        r = ROD_D / 2
        ob = bpy.data.objects.new("%s_Rod_%s_%s-%s" % (kit.label, kind, k1, k2), me)
        q = Vector((1, 0, 0)).rotation_difference(d)
        # الشبكة مرفوعة بمقدار (r - flat) — نعيدها للمحور
        ob.matrix_world = (Matrix.Translation(kit.origin + start) @ q.to_matrix().to_4x4()
                           @ Matrix.Translation((0, 0, -(r - ROD_FLAT))))
        asm.objects.link(ob)
    kit.lengths = lengths

    # تسمية أنواع الأنصاف
    counts = {}
    for sig, *_ in kit.halves:
        counts[sig] = counts.get(sig, 0) + 1
    for sig in counts:
        kit.types[sig] = None
    return asm


def check_fit(asm, label):
    """يتأكد أنه لا يوجد تداخل بين أي قضيب وأي ذرة أو قضيب آخر بعد التركيب."""
    bpy.context.view_layer.update()
    objs = list(asm.objects)
    trees = {}
    for ob in objs:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.transform(ob.matrix_world)
        trees[ob.name] = BVHTree.FromBMesh(bm)
        bm.free()
    bad = []
    names = [o.name for o in objs]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if "_Rod_" not in a and "_Rod_" not in b:
                continue      # أنصاف الذرة تتلامس على وجه القص — طبيعي
            if trees[a].overlap(trees[b]):
                bad.append((a, b))
    print("[%s] fit check: %d collisions" % (label, len(bad)))
    for a, b in bad[:20]:
        print("   ", a, "<->", b)
    return bad


# ======================================================= الصفّ على السرير


def place(coll, me, x, y, plate_origin, m=None):
    ob = bpy.data.objects.new(me.name, me)
    ob.location = Vector(plate_origin) + Vector((x, y, 0))
    if m is not None and not me.materials:
        me.materials.append(m)
    coll.objects.link(ob)
    return ob


def bed_plate(coll, origin, name):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=BED / 2 + 8)
    bmesh.ops.translate(bm, vec=(BED / 2, BED / 2, -1.0), verts=bm.verts)
    me = finish(bm, name)
    me.materials.append(mat("Print_Bed", (0.05, 0.05, 0.06), metallic=0.3, rough=0.35))
    ob = bpy.data.objects.new(name, me)
    ob.location = origin
    ob["bed"] = True
    coll.objects.link(ob)
    return ob


def layout_atoms(kit, coll, origin, atom_mat):
    items = sorted(kit.halves, key=lambda h: (h[0], h[2], h[3]))
    rmax = max(r for _, r in kit.atoms.values())
    pitch = 2 * rmax + 6.0
    per_row = int(BED // pitch)
    objs = []
    for i, (sig, me, key, upper) in enumerate(items):
        row, col = divmod(i, per_row)
        x = pitch / 2 + col * pitch
        y = pitch / 2 + row * pitch
        me.materials.clear()
        me.materials.append(atom_mat)
        objs.append(place(coll, me, x, y, origin))
    assert (len(items) + per_row - 1) // per_row * pitch <= BED, "atoms don't fit"
    return objs


def layout_rods(rods, coll, origin):
    """يصف القضبان أفقياً؛ القصيرة اثنين في الصف إن اتسعت."""
    pitch = ROD_D + 4.0
    rods = sorted(rods, key=lambda r: -r[1])
    rows = []
    for kind, L, me in rods:
        for row in rows:
            if row["used"] + 6.0 + L <= BED:
                row["items"].append((L, me))
                row["used"] += 6.0 + L
                break
        else:
            rows.append({"used": L, "items": [(L, me)]})
    assert len(rows) * pitch <= BED, "rods don't fit"
    objs = []
    for j, row in enumerate(rows):
        x = (BED - row["used"]) / 2
        for L, me in row["items"]:
            objs.append(place(coll, me, x, pitch / 2 + j * pitch, origin))
            x += L + 6.0
    return objs


# ======================================================= STL


def write_stl(path, objects, origin=Vector()):
    bpy.context.view_layer.update()
    tris = []
    for ob in objects:
        me = ob.data
        me.calc_loop_triangles()
        mw = Matrix.Translation(-origin) @ ob.matrix_world
        vs = [mw @ v.co for v in me.vertices]
        for t in me.loop_triangles:
            a, b, c = (vs[i] for i in t.vertices)
            n = (b - a).cross(c - a)
            n = n.normalized() if n.length > 0 else n
            tris.append((n, a, b, c))
    with open(path, "wb") as f:
        f.write(b"crystal print kit (mm)".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for n, a, b, c in tris:
            f.write(struct.pack("<12fH", n.x, n.y, n.z, a.x, a.y, a.z, b.x, b.y, b.z, c.x, c.y, c.z, 0))
    return len(tris)


# ======================================================= main


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.name = "Crystal_Print_Kit"
    us = sc.unit_settings
    us.system, us.scale_length, us.length_unit = 'METRIC', 0.001, 'MILLIMETERS'

    scratch = bpy.data.collections.new("_scratch")
    sc.collection.children.link(scratch)

    m_bcc_atom = mat("PLA_Black_Silk", (0.06, 0.06, 0.07), metallic=0.85, rough=0.22)
    m_clear = mat("PETG_Clear", (0.85, 0.9, 0.95), rough=0.08, transmission=1.0)
    m_hcp_atom = mat("PLA_Silver_Silk", (0.55, 0.56, 0.58), metallic=0.9, rough=0.3)
    m_grey = mat("PLA_Grey", (0.45, 0.46, 0.48), metallic=0.6, rough=0.35)
    m_yellow = mat("PLA_Yellow", (0.85, 0.55, 0.05), rough=0.4)

    root = sc.collection
    a, b = bcc_layout()
    bcc = Kit("BCC", a, b, m_bcc_atom, {"edge": m_clear, "diag": m_clear}, (-130, 0, 0))
    a, b = hcp_layout()
    hcp = Kit("HCP", a, b, m_hcp_atom, {"grey": m_grey, "yellow": m_yellow}, (130, 0, 0))

    asm_b = build_kit(bcc, root, scratch)
    asm_h = build_kit(hcp, root, scratch)
    bpy.data.collections.remove(scratch)

    plates = bpy.data.collections.new("Print_Plates")
    root.children.link(plates)
    plate_defs = []

    def plate(name, ox, oy):
        c = bpy.data.collections.new(name)
        plates.children.link(c)
        o = Vector((ox, oy, 0))
        bed_plate(c, o, name + "_bed")
        plate_defs.append((name, c, o))
        return c, o

    y0 = -520
    c, o = plate("BCC_Plate1_Atoms_Black", -470, y0)
    layout_atoms(bcc, c, o, m_bcc_atom)
    c, o = plate("BCC_Plate2_Rods_Clear", -250, y0)
    layout_rods(bcc.rods, c, o)
    c, o = plate("HCP_Plate1_Atoms_Silver", 30, y0)
    layout_atoms(hcp, c, o, m_hcp_atom)
    c, o = plate("HCP_Plate2_Rods_Grey", 250, y0)
    layout_rods([r for r in hcp.rods if r[0].endswith("grey")], c, o)
    c, o = plate("HCP_Plate3_Rods_Yellow", 470, y0)
    layout_rods([r for r in hcp.rods if r[0].endswith("yellow")], c, o)

    return sc, bcc, hcp, asm_b, asm_h, plate_defs


def label(coll, body, loc, size=6.0):
    cu = bpy.data.curves.new("T", 'FONT')
    cu.body = body
    cu.size = size
    cu.align_x = 'CENTER'
    cu.extrude = 0.2
    m = mat("Label_Black", (0.02, 0.02, 0.025), rough=0.5)
    cu.materials.append(m)
    ob = bpy.data.objects.new("Label_" + body.split("\n")[0], cu)
    ob.location = loc
    coll.objects.link(ob)
    return ob


def catalog_row(kit, types, coll, y0):
    """نسخة واحدة من كل نوع قطعة مع اسمها وعددها — للفرز بعد الطباعة."""
    x = 0.0
    for t in types:
        ob = bpy.data.objects.new("CAT_" + t["name"], t["me"])
        ob.location = (x, y0 + 30, 0)
        coll.objects.link(ob)
        # نسخة مقلوبة تُظهر الوجه المسطح (المجاري ودبوس المحاذاة)
        fl = bpy.data.objects.new("CAT_" + t["name"] + "_face", t["me"])
        fl.rotation_euler = (math.pi, 0, 0)
        fl.location = (x, y0, t["d"] / 2)
        coll.objects.link(fl)
        label(coll, "%s\nx%d" % (t["name"].split("_", 1)[1], t["count"]), (x, y0 - 24, 0), size=7.5)
        x += 58.0
    kinds = {}
    for kind, L, me in kit.rods:
        kinds.setdefault(kind, [L, 0, me])[1] += 1
    y = y0 - 62
    for kind, (L, cnt, me) in sorted(kinds.items(), key=lambda kv: -kv[1][0]):
        ob = bpy.data.objects.new("CAT_rod_" + kind, me)
        ob.location = (-20, y, 0)
        coll.objects.link(ob)
        label(coll, "rod %s  %.1f mm  x%d" % (kind, L, cnt), (-20 + L + 72, y - 2, 0), size=8)
        y -= 22
    label(coll, kit.label + "  (150 mm)", (-65, y0 + 14, 0), size=12)


def name_types(kit):
    """يعطي كل نوع نصف اسماً مقروءاً ويرجع جدول القطع."""
    groups = {}
    for sig, me, key, upper in kit.halves:
        groups.setdefault(sig, []).append((me, key, upper))
    out = []
    for sig, items in sorted(groups.items(), key=lambda kv: (-kv[0][0], len(kv[0][1]), kv[0][1])):
        r = sig[0]
        nholes = sum(1 for _, el in sig[1] if abs(el) > 0.05)
        ngroove = sum(1 for _, el in sig[1] if abs(el) <= 0.05)
        keys = sorted({k for _, k, _ in items})
        base = keys[0].split("_")[0].rstrip("+-0123456789") if kit.label == "BCC" else keys[0].split("_")[0]
        if kit.label == "HCP":
            base = {"Top": "Layer", "Bot": "Layer", "Mid": "Mid"}[base]
            if base == "Layer":
                base = "HexCenter" if any(k.endswith("_C") for k in keys) else "HexCorner"
        out.append(dict(sig=sig, me=items[0][0], count=len(items), d=2 * r, holes=nholes,
                        grooves=ngroove, base=base, keys=keys))
    # حرف لكل نوع داخل نفس الأساس
    seen = {}
    for t in out:
        n = seen.get(t["base"], 0)
        seen[t["base"]] = n + 1
        t["name"] = "%s_%s_%s" % (kit.label, t["base"], "AB"[n] if n < 2 else str(n))
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    out = os.path.abspath(argv[argv.index("--out") + 1]) if "--out" in argv else None
    render = "--render" in argv

    sc, bcc, hcp, asm_b, asm_h, plates = build()
    bad = check_fit(asm_b, "BCC") + check_fit(asm_h, "HCP")
    if not out:
        return
    os.makedirs(os.path.join(out, "stl", "parts"), exist_ok=True)
    os.makedirs(os.path.join(out, "stl", "plates"), exist_ok=True)

    report = {"collisions": len(bad), "kits": {}}
    catalog = bpy.data.collections.new("Parts_Catalog")
    sc.collection.children.link(catalog)
    for row, kit in enumerate((bcc, hcp)):
        types = name_types(kit)
        y0 = 520 + row * 230
        catalog_row(kit, types, catalog, y0)
        info = {"atom_types": [], "rods": {}}
        for t in types:
            tmp = bpy.data.objects.new(t["name"], t["me"])
            n = write_stl(os.path.join(out, "stl", "parts", t["name"] + ".stl"), [tmp])
            bpy.data.objects.remove(tmp)
            info["atom_types"].append(dict(name=t["name"], count=t["count"], d=round(t["d"], 2),
                                           holes=t["holes"], grooves=t["grooves"], tris=n,
                                           sig=t["sig"][1]))
        kinds = {}
        for kind, L, me in kit.rods:
            kinds.setdefault(kind, [L, 0, me])[1] += 1
        for kind, (L, cnt, me) in kinds.items():
            nm = "%s_Rod_%s_%dmm" % (kit.label, kind, round(L))
            tmp = bpy.data.objects.new(nm, me)
            write_stl(os.path.join(out, "stl", "parts", nm + ".stl"), [tmp])
            bpy.data.objects.remove(tmp)
            info["rods"][kind] = dict(length=L, count=cnt, file=nm + ".stl")
        report["kits"][kit.label] = info

    for name, coll, origin in plates:
        objs = [o for o in coll.objects if not o.get("bed")]
        write_stl(os.path.join(out, "stl", "plates", name + ".stl"), objs, origin)
        report.setdefault("plates", {})[name] = len(objs)

    report["dims_mm"] = dict(
        BCC=dict(edge=round(BCC_EDGE, 2), corner_d=round(BCC_CORNER_D, 2), center_d=round(BCC_CENTER_D, 2),
                 height=round(BCC_EDGE + BCC_CORNER_D, 2)),
        HCP=dict(a=round(HCP_A, 2), c=round(HCP_C, 2), atom_d=round(HCP_D, 2), height=round(HCP_C + HCP_D, 2)),
        rod_d=ROD_D, hole_d=ROD_D + HOLE_CLEAR, insert=INSERT)
    import json
    with open(os.path.join(out, "kit_report.json"), "w") as f:
        json.dump(report, f, indent=1, default=str)
    print(json.dumps(report, indent=1, default=str)[:4000])

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Crystal_Print_Kit.blend"))


if __name__ == "__main__":
    main()
