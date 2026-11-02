# -*- coding: utf-8 -*-
"""
نموذجا بلورتين في Blender (4.2+ / 5.x):
  1) BCC  — مكعب مركزي الجسم: 8 ذرات زوايا + ذرة مركزية، قضبان زجاجية
  2) HCP  — سداسي متراص: سداسيان (علوي/سفلي) + 3 ذرات في الطبقة الوسطى،
            قضبان فولاذية، وخلية الوحدة باللون الأصفر

طريقة الاستخدام داخل Blender:
  Scripting  ->  Open  ->  crystal_models.py  ->  Run Script
  يُنشئ مشهدين: "BCC_Cube" و "HCP_Hexagonal" (بدّل بينهما من أعلى يمين النافذة).

من سطر الأوامر (حفظ ملفات .blend وإخراج صور):
  blender -b -P crystal_models.py -- --out ./output --render

كل المقاسات بالأمتار الحقيقية (0.20 = 20 سم) وتظهر في Blender بالسنتيمتر.
"""
import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector

CM = 0.01  # 1 سم

# ---------------------------------------------------------------- المقاسات
# جدول المقاسات المقترحة (BCC)
BCC = dict(
    edge=20.0 * CM,       # طول/عرض/ارتفاع ضلع المكعب
    corner_d=3.0 * CM,    # قطر ذرة الزاوية
    center_d=3.5 * CM,    # قطر الذرة المركزية
    rod_d=0.8 * CM,       # قطر قضبان الربط
)
# HCP: c/a = 1.633 (النسبة المثالية للتراص السداسي)
HCP = dict(
    a=10.0 * CM,          # ضلع السداسي (المسافة بين ذرتين متجاورتين)
    c=16.33 * CM,         # الارتفاع بين الطبقة السفلية والعلوية
    atom_d=3.0 * CM,      # قطر الذرة
    rod_d=0.45 * CM,      # قطر القضبان (رفيعة كما في المجسم الحقيقي)
)

SPHERE_SEG, SPHERE_RINGS = 96, 48   # دقة الكرات
ROD_SEG = 48                        # دقة القضبان
ROD_SINK = 0.25 * CM                # كم يدخل القضيب داخل الكرة


# ---------------------------------------------------------------- أدوات
def link(obj, coll):
    coll.objects.link(obj)
    return obj


def new_collection(name, parent):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


def sphere_mesh(name, r):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=SPHERE_SEG, v_segments=SPHERE_RINGS, radius=r)
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(me)
    bm.free()
    return me


def rod_mesh(name, r, length):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=ROD_SEG,
                          radius1=r, radius2=r, depth=length)
    for f in bm.faces:
        f.smooth = abs(f.normal.z) < 0.5   # الجوانب ناعمة، الأطراف مسطحة
    bm.to_mesh(me)
    bm.free()
    return me


def add_atom(name, mesh, pos, mat, coll):
    ob = bpy.data.objects.new(name, mesh)
    ob.location = pos
    if not mesh.materials:
        mesh.materials.append(mat)
    return link(ob, coll)


def add_rod(name, p1, r1, p2, r2, rod_r, mat, coll):
    """قضيب من سطح الذرة الأولى إلى سطح الثانية (يغوص قليلاً داخل كل منهما)."""
    p1, p2 = Vector(p1), Vector(p2)
    d = p2 - p1
    dist = d.length
    d.normalize()
    a = p1 + d * (r1 - ROD_SINK)
    b = p2 - d * (r2 - ROD_SINK)
    length = (b - a).length
    me = rod_mesh(name, rod_r, length)
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.location = (a + b) / 2
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d)
    return link(ob, coll)


def principled(name, color, metallic=0.0, rough=0.5, transmission=0.0, ior=1.45,
               coat=0.0, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    b.inputs["IOR"].default_value = ior
    for key in ("Transmission Weight", "Transmission"):
        if key in b.inputs:
            b.inputs[key].default_value = transmission
            break
    for key in ("Coat Weight", "Clearcoat"):
        if key in b.inputs:
            b.inputs[key].default_value = coat
            break
    for key in ("Specular IOR Level", "Specular"):
        if key in b.inputs:
            b.inputs[key].default_value = spec
            break
    m.diffuse_color = (*color, 1.0)
    return m


# ---------------------------------------------------------------- الاستوديو
def backdrop(coll, mat, width=4.0, depth=2.5, height=2.5, radius=0.8, steps=24):
    """خلفية استوديو منحنية (أرضية + جدار بانحناء ناعم) بدون حواف ظاهرة."""
    # المقطع الجانبي (y, z): أرضية مستوية ثم ربع دائرة ثم جدار عمودي
    prof = [(-depth, 0.0), (1.0 - radius, 0.0)]
    for i in range(1, steps):
        t = (math.pi / 2) * i / steps
        prof.append((1.0 - radius + radius * math.sin(t), radius - radius * math.cos(t)))
    prof += [(1.0, radius), (1.0, height)]
    me = bpy.data.meshes.new("Backdrop")
    bm = bmesh.new()
    left = [bm.verts.new((-width / 2, y, z)) for y, z in prof]
    right = [bm.verts.new((width / 2, y, z)) for y, z in prof]
    for i in range(len(prof) - 1):
        f = bm.faces.new((left[i], right[i], right[i + 1], left[i + 1]))
        f.smooth = True
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new("Studio_Backdrop", me)
    # Subdivision لتنعيم الانحناء
    mod = ob.modifiers.new("Smooth", 'SUBSURF')
    mod.levels = 1
    mod.render_levels = 2
    return link(ob, coll)


def area_light(name, coll, loc, target, power, size, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = power
    ld.shape = 'DISK'
    ld.size = size
    ld.color = color
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    direction = Vector(target) - Vector(loc)
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = direction.to_track_quat('-Z', 'Y')
    return link(ob, coll)


def camera(scene, coll, loc, target, lens):
    cd = bpy.data.cameras.new("Camera")
    cd.lens = lens
    cd.clip_start = 0.01
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = 11.0
    ob = bpy.data.objects.new("Camera", cd)
    ob.location = loc
    link(ob, coll)
    tgt = bpy.data.objects.new("Camera_Target", None)
    tgt.empty_display_type = 'SPHERE'
    tgt.empty_display_size = 0.02
    tgt.location = target
    link(tgt, coll)
    con = ob.constraints.new('TRACK_TO')
    con.target = tgt
    con.track_axis = 'TRACK_NEGATIVE_Z'
    con.up_axis = 'UP_Y'
    cd.dof.focus_object = tgt
    scene.camera = ob
    return ob


def world(scene, color, strength):
    w = bpy.data.worlds.new(scene.name + "_World")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (*color, 1.0)
    bg.inputs["Strength"].default_value = strength
    scene.world = w


def setup_scene(name):
    sc = bpy.data.scenes.new(name)
    us = sc.unit_settings
    us.system = 'METRIC'
    us.scale_length = 1.0
    us.length_unit = 'CENTIMETERS'
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 256
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 16
    sc.cycles.transmission_bounces = 16
    sc.cycles.glossy_bounces = 8
    sc.cycles.transparent_max_bounces = 16
    sc.render.resolution_x = 1600
    sc.render.resolution_y = 1600
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'AgX'
    try:
        sc.view_settings.look = 'AgX - Medium High Contrast'
    except TypeError:
        pass
    sc.render.image_settings.file_format = 'PNG'
    return sc


# ---------------------------------------------------------------- 1) BCC
def build_bcc():
    sc = setup_scene("BCC_Cube")
    root = new_collection("BCC_Crystal", sc.collection)
    c_atoms = new_collection("Atoms", root)
    c_bonds = new_collection("Bonds", root)
    c_studio = new_collection("Studio", sc.collection)

    e = BCC["edge"]
    rc, rz, rr = BCC["corner_d"] / 2, BCC["center_d"] / 2, BCC["rod_d"] / 2
    z0 = e / 2 + rc                          # المكعب يجلس على الأرض
    center = Vector((0, 0, z0))

    # مواد مطابقة للصورة: ذرات معدنية داكنة لامعة + قضبان زجاجية شفافة
    m_atom = principled("BCC_Atom_DarkChrome", (0.10, 0.105, 0.115), metallic=1.0, rough=0.12)
    m_center = principled("BCC_Atom_Center", (0.10, 0.105, 0.115), metallic=1.0, rough=0.12)
    m_glass = principled("BCC_Bond_Glass", (0.62, 0.66, 0.70), metallic=0.0, rough=0.06,
                         transmission=1.0, ior=1.5)

    me_corner = sphere_mesh("Atom_Corner_Mesh", rc)
    me_center = sphere_mesh("Atom_Center_Mesh", rz)

    corners = {}
    for ix in (-1, 1):
        for iy in (-1, 1):
            for iz in (-1, 1):
                p = center + Vector((ix, iy, iz)) * (e / 2)
                key = (ix, iy, iz)
                corners[key] = p
                add_atom("Atom_Corner_%s%s%s" % tuple("+" if v > 0 else "-" for v in key),
                         me_corner, p, m_atom, c_atoms)
    add_atom("Atom_Center", me_center, center, m_center, c_atoms)

    # 12 ضلعاً للمكعب
    keys = list(corners)
    n = 0
    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1:]:
            if sum(a != b for a, b in zip(k1, k2)) == 1:
                n += 1
                add_rod("Bond_Edge_%02d" % n, corners[k1], rc, corners[k2], rc, rr, m_glass, c_bonds)
    # 8 قضبان من المركز إلى الزوايا (طول 17.32 سم مركز-مركز)
    for i, k in enumerate(keys, 1):
        add_rod("Bond_Diagonal_%02d" % i, center, rz, corners[k], rc, rr, m_glass, c_bonds)

    # استوديو أبيض مثل الصورة
    m_bg = principled("Studio_White", (0.9, 0.9, 0.9), rough=0.6)
    backdrop(c_studio, m_bg, depth=2.0, height=2.5, radius=0.7)
    world(sc, (0.5, 0.52, 0.56), 0.03)
    area_light("Key_Light", c_studio, (-0.7, -0.9, 1.1), center, 55, 0.6)
    area_light("Fill_Light", c_studio, (1.0, -0.6, 0.5), center, 14, 1.0)
    area_light("Top_Light", c_studio, (0.1, 0.2, 1.4), center, 30, 0.8)
    area_light("Rim_Light", c_studio, (0.5, 0.8, 0.6), center, 18, 0.4)
    camera(sc, c_studio, (0.26, -0.45, 0.33), center + Vector((0, 0, -0.005)), 40)
    sc["dimensions_cm"] = {
        "edge": 20, "corner_atom_d": 3, "center_atom_d": 3.5, "rod_d": 0.8,
        "space_diagonal": round(e * math.sqrt(3) / CM, 2),
        "center_to_corner": round(e * math.sqrt(3) / 2 / CM, 2),
    }
    return sc


# ---------------------------------------------------------------- 2) HCP
def build_hcp():
    sc = setup_scene("HCP_Hexagonal")
    root = new_collection("HCP_Crystal", sc.collection)
    c_atoms = new_collection("Atoms", root)
    c_bonds = new_collection("Bonds_Steel", root)
    c_cell = new_collection("Bonds_UnitCell_Yellow", root)
    c_studio = new_collection("Studio", sc.collection)

    a, c = HCP["a"], HCP["c"]
    r, rr = HCP["atom_d"] / 2, HCP["rod_d"] / 2
    zb, zt, zm = r, r + c, r + c / 2
    mid_center = Vector((0, 0, zm))

    # مواد مطابقة للمجسم: ذرات رصاصية ساتان + أسلاك فولاذ + قضبان صفراء
    m_atom = principled("HCP_Atom_Pewter", (0.22, 0.23, 0.24), metallic=1.0, rough=0.3)
    m_steel = principled("HCP_Bond_Steel", (0.55, 0.56, 0.58), metallic=1.0, rough=0.25)
    m_yellow = principled("HCP_Bond_Yellow", (0.75, 0.40, 0.02), metallic=0.0, rough=0.4, coat=0.3)

    me_atom = sphere_mesh("Atom_Mesh", r)

    # زوايا السداسي: 0=يمين, 60=خلف-يمين, 120=خلف-يسار, 180=يسار, 240=أمام-يسار, 300=أمام-يمين
    names = {0: "R", 60: "BR", 120: "BL", 180: "L", 240: "FL", 300: "FR"}

    def hex_pt(deg, z):
        t = math.radians(deg)
        return Vector((a * math.cos(t), a * math.sin(t), z))

    layers = {}
    for tag, z in (("Top", zt), ("Bot", zb)):
        pts = {"C": Vector((0, 0, z))}
        for deg, nm in names.items():
            pts[nm] = hex_pt(deg, z)
        layers[tag] = pts
        for nm, p in pts.items():
            add_atom("Atom_%s_%s" % (tag, nm), me_atom, p, m_atom, c_atoms)

    # الطبقة الوسطى: 3 ذرات في مراكز المثلثات المتناوبة (خلف، أمام-يسار، أمام-يمين)
    mids = {}
    for deg, nm in ((90, "B"), (210, "FL"), (330, "FR")):
        t = math.radians(deg)
        p = Vector((a / math.sqrt(3) * math.cos(t), a / math.sqrt(3) * math.sin(t), zm))
        mids[nm] = p
        add_atom("Atom_Mid_%s" % nm, me_atom, p, m_atom, c_atoms)

    # خلية الوحدة (معيّن): المركز + أمام-يسار + أمام-يمين + يمين  => أصفر
    cell_edges = {("C", "FL"), ("FL", "FR"), ("FR", "R"), ("R", "C")}
    cell_verts = {"C", "FL", "FR", "R"}
    order = ["R", "BR", "BL", "L", "FL", "FR"]

    def is_cell(e1, e2):
        return (e1, e2) in cell_edges or (e2, e1) in cell_edges

    for tag in ("Top", "Bot"):
        P = layers[tag]
        for i, nm in enumerate(order):                      # أضلاع السداسي
            nx = order[(i + 1) % 6]
            y = is_cell(nm, nx)
            add_rod("Bond_%s_Edge_%s-%s" % (tag, nm, nx), P[nm], r, P[nx], r, rr,
                    m_yellow if y else m_steel, c_cell if y else c_bonds)
        for nm in order:                                    # من المركز للرؤوس
            y = is_cell("C", nm)
            add_rod("Bond_%s_Spoke_%s" % (tag, nm), P["C"], r, P[nm], r, rr,
                    m_yellow if y else m_steel, c_cell if y else c_bonds)

    for nm in ["C"] + order:                                # القوائم العمودية
        y = nm in cell_verts
        add_rod("Bond_Vertical_%s" % nm, layers["Bot"][nm], r, layers["Top"][nm], r, rr,
                m_yellow if y else m_steel, c_cell if y else c_bonds)

    mk = list(mids)
    for i in range(3):                                      # مثلث الطبقة الوسطى
        k1, k2 = mk[i], mk[(i + 1) % 3]
        add_rod("Bond_Mid_%s-%s" % (k1, k2), mids[k1], r, mids[k2], r, rr, m_steel, c_bonds)
    for k, p in mids.items():                               # الوسط إلى مركزي السداسيين
        add_rod("Bond_Mid_%s-TopC" % k, p, r, layers["Top"]["C"], r, rr, m_steel, c_bonds)
        add_rod("Bond_Mid_%s-BotC" % k, p, r, layers["Bot"]["C"], r, rr, m_steel, c_bonds)

    m_bg = principled("Studio_Grey", (0.82, 0.82, 0.84), rough=0.7)
    backdrop(c_studio, m_bg, depth=2.0, height=2.5, radius=0.7)
    world(sc, (0.6, 0.62, 0.66), 0.1)
    area_light("Key_Light", c_studio, (-0.8, -0.8, 1.0), mid_center, 50, 0.6)
    area_light("Fill_Light", c_studio, (0.9, -0.7, 0.45), mid_center, 14, 1.0)
    area_light("Top_Light", c_studio, (0.0, 0.1, 1.3), mid_center, 25, 0.8)
    area_light("Rim_Light", c_studio, (0.4, 0.8, 0.5), mid_center, 15, 0.4)
    camera(sc, c_studio, (0.0, -0.62, 0.30), mid_center + Vector((0, 0, -0.005)), 60)
    sc["dimensions_cm"] = {"a": 10, "c": 16.33, "c_over_a": 1.633, "atom_d": 3, "rod_d": 0.45}
    return sc


# ---------------------------------------------------------------- التشغيل
def build_all():
    s1 = build_bcc()
    s2 = build_hcp()
    if bpy.context.window is not None:
        bpy.context.window.scene = s1
    return s1, s2


def cli_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else argv[1:]
    out = None
    render = "--render" in argv
    samples = None
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    if "--samples" in argv:
        samples = int(argv[argv.index("--samples") + 1])
    pct = int(argv[argv.index("--percent") + 1]) if "--percent" in argv else 100
    return out, render, samples, pct


def reset_file():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def export(builder, out, render, samples, fname, pct=100):
    reset_file()
    sc = builder()
    for s in list(bpy.data.scenes):
        if s != sc:
            bpy.data.scenes.remove(s)
    if samples:
        sc.cycles.samples = samples
    sc.render.resolution_percentage = pct
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, fname + ".blend"))
    if render:
        sc.render.filepath = os.path.join(out, fname + ".png")
        bpy.ops.render.render(write_still=True, scene=sc.name)


if __name__ == "__main__":
    out, render, samples, pct = cli_args()
    if out:
        out = os.path.abspath(out)
        os.makedirs(out, exist_ok=True)
        export(build_bcc, out, render, samples, "BCC_Cube", pct)
        export(build_hcp, out, render, samples, "HCP_Hexagonal", pct)
    else:
        build_all()
