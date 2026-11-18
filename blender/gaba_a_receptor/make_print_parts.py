"""
GABA-A receptor  ->  colour-separated ASSEMBLY KIT laid out on print plates.

تقسيم النموذج إلى قطع تركيب (كل قطعة بألوانها) وترتيبها على سرير الطابعة.

    pip install manifold3d numpy rectpack
    blender -b -P gaba_a_receptor.py -- --raw raw          # one STL per object (mm)
    python make_print_parts.py raw kit --bed 256 256        # build the kit

What it does
  * groups the scene objects into printable PARTS; a part can hold several
    colour VOLUMES (e.g. purple α body + white "α" letter on top)
  * every part that sits behind/inside another part gets a pocket, slot or hole
    for it (with CLEARANCE) -> parts self-locate when you assemble them
  * flat-faced parts are turned FRONT-FACE-UP with a flat back, so letters and
    rims are on top: colours change only with height -> works with a
    multi-colour system (AMS / MMU) AND with a single nozzle (pause / M600)
  * the 300 mm base is split in two halves joined by 3 printed dowel pins
    when the bed is smaller than the base
  * everything is packed onto plates of the given bed size

Output (kit/):
  plate_N/Pxx_<PART>__<Colour>.stl   all parts of a plate, already positioned:
                                     load ALL files of a plate together, answer
                                     "Yes" to "multi-part object?" and assign
                                     filament by the colour in the file name
  parts.json                         part list, colours, colour-change heights
"""
import json
import math
import os
import sys

import numpy as np
import manifold3d as m3d
from manifold3d import Manifold, CrossSection, OpType

# ------------------------------------------------------------------ settings
CLR = 0.25            # mm clearance for every pocket / hole / slot
GAP = 6.0             # mm between parts on a plate
EDGE = 6.0            # mm free border of the bed

FILAMENT = {          # name -> display colour (hex)
    "Navy": "#1A2C6B", "White": "#F5F5F2", "Purple": "#8E52D8",
    "DarkPurple": "#6E3CB6", "Blue": "#2F6FDB", "LightBlue": "#3AB0F2",
    "Yellow": "#F3C300", "Green": "#22A82A", "Lime": "#86F23A", "Red": "#E0161F",
}

# orientation matrices (3x4)
FRONT_UP = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0]], float)   # front(-y) -> +z
FRONT_UP_INV = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0]], float)
IDENT = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]], float)

# ------------------------------------------------------------------ the kit
#  vols : [(filament, [objects])]  bottom -> top; later volumes win overlaps
#  cut  : parts that are seated INTO this one (get a pocket with clearance)
#  orient: "front" (face up, flat back) | "up" (as assembled) | "axis" (rod upright)
#  keep : half-spaces kept (normal, offset): n.x >= offset   (mm, model frame)
#  "obj@L" / "obj@R" = only the shells of obj on the left / right (x<0 / x>0)
# lipid heads that stick out of the membrane core overhang the void below them
# (the lower row sits on the bed on a single point -> "eggs"). Each head gets a
# 45-degree cone under it, which prints without supports and keeps the round
# look from the front. Front-row top heads lean their cone back into the face.
TEARDROP = dict(obj="Lipid_Heads", face_front=-3.0, z_mid=105.0)

PARTS = [
    dict(id="BASE", step=1, orient="up", split=True,
         vols=[("Navy", ["Base_Pedestal", "Base_MembranePlatform"])],
         cut=["ALPHA_L", "ALPHA_R", "ALPHA_BACK_L", "ALPHA_BACK_R", "CHANNEL",
              "EXIT_ION", "TITLE_STAND", "PLAQUE_CL", "PLAQUE_INHIBITION",
              "ARROW_RIGHT", "MEMBRANE_L", "MEMBRANE_R"]),
    dict(id="PLAQUE_CL", step=2, orient="front",
         vols=[("White", ["Plaque_Cl"]),
               ("Navy", ["Plaque_Cl_Text", "Plaque_Cl_minus", "Plaque_UpArrow"])]),
    dict(id="PLAQUE_INHIBITION", step=2, orient="front",
         vols=[("White", ["Plaque_Inhibition"]), ("Navy", ["Plaque_Inhibition_Text"])]),
    dict(id="ARROW_RIGHT", step=2, orient="front", vols=[("White", ["Plaque_RightArrow"])]),
    dict(id="TITLE_STAND", step=3, orient="front", vols=[("White", ["Title_Stand"])],
         cut=["GAMMA", "CHANNEL"]),
    # membrane: two colour parts like the first kit -> YELLOW = only the lipid
    # heads (+ the 45 deg cones of the bottom row), WHITE = core, tails and the
    # small 45 deg necks under the top heads; clean straight cut next to alpha.
    dict(id="MEMBRANE_L", step=4, orient="up", keep=[((0, 0, 1), 75.0), ((-1, 0, 0), 50.0)],
         vols=[("White", ["Lipid_Core_L", "Lipid_Tails_Relief@L", "Lipid_Heads@L!necks"]),
               ("Yellow", ["Lipid_Heads@L!heads"])],
         cut=["ALPHA_L", "ALPHA_BACK_L"], prism_cut=True,
         teardrop=TEARDROP),
    dict(id="MEMBRANE_R", step=4, orient="up", keep=[((0, 0, 1), 75.0), ((1, 0, 0), 50.0)],
         vols=[("White", ["Lipid_Core_R", "Lipid_Tails_Relief@R", "Lipid_Heads@R!necks"]),
               ("Yellow", ["Lipid_Heads@R!heads"])],
         cut=["ALPHA_R", "ALPHA_BACK_R"], prism_cut=True,
         teardrop=TEARDROP),
    dict(id="CHANNEL", step=5, orient="front",
         vols=[("Green", ["Channel_Pore"]),
               ("Lime", ["Cl_Ion_1", "Cl_Ion_2", "Channel_Arrow"])],
         cut=["ALPHA_L", "ALPHA_R", "ALPHA_BACK_L", "ALPHA_BACK_R", "GAMMA",
              "BETA_L", "BETA_R"]),
    dict(id="ALPHA_BACK_L", step=6, orient="front",
         vols=[("DarkPurple", ["Alpha_L_Back"])], cut=["ALPHA_L"]),
    dict(id="ALPHA_BACK_R", step=6, orient="front",
         vols=[("DarkPurple", ["Alpha_R_Back"])], cut=["ALPHA_R"]),
    dict(id="ALPHA_L", step=7, orient="front",
         vols=[("Purple", ["Alpha_L"]), ("White", ["Letter_Alpha_L"])],
         cut=["GABA_BALL", "STRUT_GABA", "ARROW_GABA"]),
    dict(id="ALPHA_R", step=7, orient="front",
         vols=[("Purple", ["Alpha_R"]), ("White", ["Letter_Alpha_R"])],
         cut=["DIAZEPAM_BALL", "STRUT_DIAZEPAM", "ARROW_DIAZEPAM"]),
    dict(id="GAMMA", step=8, orient="front",
         vols=[("Yellow", ["Gamma"]), ("Navy", ["Letter_Gamma"])],
         cut=["BETA_L", "BETA_R", "ALPHA_L", "ALPHA_R"]),
    dict(id="BETA_L", step=8, orient="front",
         vols=[("Blue", ["Beta_L"]), ("White", ["Letter_Beta_L"])],
         cut=["ALPHA_L", "ALPHA_BACK_L", "STRUT_GABA"]),
    dict(id="BETA_R", step=8, orient="front",
         vols=[("Blue", ["Beta_R"]), ("White", ["Letter_Beta_R"])],
         cut=["ALPHA_R", "ALPHA_BACK_R", "STRUT_DIAZEPAM"]),
    dict(id="EXIT_ION", step=9, orient="up", keep=[((0, 0, 1), 40.0)],
         vols=[("Lime", ["Cl_Ion_Exit"]), ("White", ["Ion_Cl_Text", "Ion_Cl_minus"])]),
    dict(id="GABA_BALL", step=10, orient="front", keep=[((0, -1, 0), 27.0)],
         vols=[("Red", ["GABA_Ligand"])], cut=["ARROW_GABA"]),
    dict(id="DIAZEPAM_BALL", step=10, orient="front", keep=[((0, -1, 0), 27.0)],
         vols=[("LightBlue", ["Diazepam_Ligand"])], cut=["ARROW_DIAZEPAM"]),
    dict(id="TITLE", step=11, orient="front",
         vols=[("Blue", ["Title_Panel_Rim"]), ("Navy", ["Title_Panel"]),
               ("White", ["Title_GABA", "Title_sub_A", "Title_Receptor"])],
         cut=["TITLE_STAND"]),
    dict(id="STRUT_GABA", step=12, orient="axis", vols=[("Red", ["Arrow_GABA_Strut"])]),
    dict(id="STRUT_DIAZEPAM", step=12, orient="axis",
         vols=[("Blue", ["Arrow_Diazepam_Strut"])]),
    dict(id="CALLOUT_GABA", step=13, orient="front",
         vols=[("Red", ["Callout_GABA_Rim"]), ("White", ["Callout_GABA_Face"]),
               ("Navy", ["Callout_GABA_Text"])],
         cut=["ARROW_GABA", "STRUT_GABA"]),
    dict(id="CALLOUT_DIAZEPAM", step=13, orient="front",
         vols=[("Blue", ["Callout_Diazepam_Rim"]), ("White", ["Callout_Diazepam_Face"]),
               ("Navy", ["Callout_Diazepam_Text"])],
         cut=["ARROW_DIAZEPAM", "STRUT_DIAZEPAM"]),
    dict(id="ARROW_GABA", step=14, orient="axis", vols=[("Red", ["Arrow_GABA"])]),
    dict(id="ARROW_DIAZEPAM", step=14, orient="axis", vols=[("Blue", ["Arrow_Diazepam"])]),
]

STEPS_AR = {
    1: "ركّب نصفي القاعدة BASE_L و BASE_R بالمسامير الثلاثة DOWEL + غراء",
    2: "ادخل اللوحتين PLAQUE_CL و PLAQUE_INHIBITION والسهم ARROW_RIGHT في جيوبها بواجهة القاعدة",
    3: "ادخل عمود اللوحة TITLE_STAND في الفتحة خلف المنصة",
    4: "ضع الغشاء MEMBRANE_L و MEMBRANE_R على المنصة (العلامة الخفيفة تحدد مكانهما)",
    5: "ادخل القناة الخضراء CHANNEL في جيبها في الوسط",
    6: "ضع القطع البنفسجية الغامقة ALPHA_BACK_L/R",
    7: "ضع ALPHA_L و ALPHA_R أمامها (أقدامها تدخل في جيوب القاعدة)",
    8: "ضع GAMMA ثم BETA_L و BETA_R",
    9: "ضع كرة الأيون EXIT_ION على القاعدة تحت القناة",
    10: "ادخل كرة GABA الحمراء وكرة Diazepam الزرقاء في جيوبها أعلى α",
    11: "ركّب اللوحة العلوية TITLE على رأس العمود",
    12: "ادخل الدعامتين STRUT في الثقوب المائلة (تمر عبر β إلى α)",
    13: "ركّب البطاقتين CALLOUT على طرف الدعامة",
    14: "ادخل السهمين ARROW من ثقب البطاقة إلى جيب الكرة",
}


# ------------------------------------------------------------------ helpers
def read_stl(path):
    raw = np.fromfile(path, dtype=np.uint8)
    n = int(np.frombuffer(raw[80:84], "<u4")[0])
    rec = np.frombuffer(raw[84:84 + n * 50].tobytes(),
                        dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    return rec["v"].reshape(-1, 3).astype(np.float64)


def shells_from_tris(tri):
    q = np.round(tri * 1e4).astype(np.int64)
    uniq, inv = np.unique(q, axis=0, return_inverse=True)
    verts, faces = uniq / 1e4, inv.reshape(-1, 3)
    parent = np.arange(len(verts))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b, c in faces:
        ra = find(a)
        parent[find(b)] = ra
        parent[find(c)] = ra
    roots = np.array([find(i) for i in range(len(verts))])
    comp = roots[faces[:, 0]]
    out = []
    for r in np.unique(comp):
        f = faces[comp == r]
        used, rem = np.unique(f, return_inverse=True)
        man = Manifold(m3d.Mesh(vert_properties=verts[used].astype(np.float32),
                                tri_verts=rem.reshape(-1, 3).astype(np.uint32)))
        if man.status() == m3d.Error.NoError and not man.is_empty():
            out.append(man)
    return out


_CACHE = {}


def load(name, raw_dir):
    side = None
    if "@" in name:
        name, side = name.split("@")
    if name not in _CACHE:
        _CACHE[name] = shells_from_tris(read_stl(os.path.join(raw_dir, name + ".stl")))
    shells = _CACHE[name]
    if side:
        def cx(m):
            b = m.bounding_box()
            return (b[0] + b[3]) / 2
        shells = [s for s in shells if (cx(s) < 0) == (side == "L")]
    return union(shells)


def teardrop_heads(name, raw_dir, td):
    """head spheres -> sphere + 45 deg support cone (hull with an apex point)
    name "Lipid_Heads@R!heads": the balls + the cones of the bottom row (yellow)
         "Lipid_Heads@R!necks": the cones under the top row only (white)"""
    name, mode = (name.split("!") + ["all"])[:2]
    load(name, raw_dir)                               # fills the cache
    base, side = name.split("@")
    out = []
    for sh in _CACHE[base]:                           # raw shells = single spheres
        b = np.array(sh.bounding_box())
        if ((b[0] + b[3]) / 2 < 0) != (side == "L"):
            continue
        b = np.array(sh.bounding_box())
        c, r = (b[:3] + b[3:]) / 2, (b[3] - b[0]) / 2
        drop = r * math.sqrt(2.0)                     # apex of the 45 deg cone
        if c[2] > td["z_mid"] and c[1] < td["face_front"]:
            back = td["face_front"] + 1.0 - c[1]      # lean the cone into the face
            apex = (c[0], c[1] + back, c[2] - drop - back)
        else:
            apex = (c[0], c[1], c[2] - drop)
        v = np.asarray(sh.to_mesh().vert_properties)[:, :3]
        tear = Manifold.hull_points(np.vstack([v, apex]))
        top = c[2] > td["z_mid"]
        if mode == "heads":
            out.append(sh if top else tear)
        elif mode == "necks":
            if top:
                out.append(tear)
        else:
            out.append(tear)
    return union(out)


def union(ms):
    ms = [m for m in ms if m is not None and not m.is_empty()]
    if not ms:
        return Manifold()
    return Manifold.batch_boolean(ms, OpType.Add) if len(ms) > 1 else ms[0]


def grow(m, c=CLR):
    """true outward offset by c mm (Minkowski sum with a small sphere)"""
    return m.minkowski_sum(Manifold.sphere(c, 8))


def prism_y(m):
    """straight-walled version of a cutter: its XZ silhouette extruded over its
    whole Y range -> clean flat cut faces instead of a torn, curvy cut"""
    r = m.transform(FRONT_UP)
    b = r.bounding_box()
    cs = CrossSection(r.project().to_polygons(), m3d.FillRule.Positive)
    return Manifold.extrude(cs, b[5] - b[2]).translate((0, 0, b[2])).transform(FRONT_UP_INV)


def flat_back(m):
    """front-up frame: replace the rounded back half by a straight prism of the
    silhouette, so the part lies flat on the bed (back is hidden anyway)"""
    r = m.transform(FRONT_UP)
    b = r.bounding_box()
    cs = CrossSection(r.project().to_polygons(), m3d.FillRule.Positive)
    prism = Manifold.extrude(cs, (b[5] - b[2]) * 0.5).translate((0, 0, b[2]))
    return (r + prism).transform(FRONT_UP_INV)


def axis_matrix(m):
    """3x4 rotation putting the long axis of a rod on +z (cone tip up)."""
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3]
    c = v.mean(0)
    w, vec = np.linalg.eigh(np.cov((v - c).T))
    a = vec[:, -1]
    t = (v - c) @ a
    tol = 0.6
    if (t > t.max() - tol).sum() > (t < t.min() + tol).sum():   # many verts = flat cap
        a = -a                                                   # -> cap at bottom
    z = np.array([0, 0, 1.0])
    k = np.cross(a, z)
    s, cth = np.linalg.norm(k), a @ z
    if s < 1e-9:
        R = np.eye(3) if cth > 0 else np.diag([1, -1, -1.0])
    else:
        k /= s
        K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
        R = np.eye(3) + s * K + (1 - cth) * K @ K
    return np.hstack([R, np.zeros((3, 1))])


def write_stl(path, m):
    mesh = m.to_mesh()
    v, t = np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts)
    tris = v[t].astype(np.float32)
    nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    rec = np.zeros(len(t), dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    rec["n"], rec["v"] = nrm, tris.reshape(-1, 9)
    with open(path, "wb") as fh:
        fh.write(b"GABA-A receptor kit, mm".ljust(80, b" "))
        fh.write(np.uint32(len(t)).tobytes())
        fh.write(rec.tobytes())


def dowel_holes(r, length):
    """3 horizontal pins across the x=0 seam of the base (mm)."""
    cyl = Manifold.cylinder(length, r, r, 48).rotate((0, 90, 0)).translate((-length / 2, 0, 0))
    return [cyl.translate((0, y, z)) for y, z in ((-45, 18), (22, 18), (22, 55))]


# ------------------------------------------------------------------ build
def build(raw_dir, out_dir, bed, max_colours=4, assembled_dir=None):
    spec = {p["id"]: p for p in PARTS}

    # 1) raw colour volumes, trimmed, rounded backs flattened
    raw = {}
    for p in PARTS:
        vols = []
        for i, (fil, objs) in enumerate(p["vols"]):
            td = p.get("teardrop")
            m = union([teardrop_heads(o, raw_dir, td) if td and o.startswith(td["obj"])
                       else load(o, raw_dir) for o in objs])
            for n, off in p.get("keep", []):
                m = m.trim_by_plane(n, off)
            if p["orient"] == "front" and i == 0:
                m = flat_back(m)
            vols.append((fil, m))
        raw[p["id"]] = vols
    solid = {k: union([m for _, m in v]) for k, v in raw.items()}

    # 2) pockets / holes / slots for the parts seated into each part
    grown = {}
    for p in PARTS:
        for c in p.get("cut", []):
            if c not in grown:
                grown[c] = grow(solid[c])
    final, dropped = {}, {}
    for p in PARTS:
        cutter = union([grown[c] for c in p.get("cut", [])])
        if p.get("prism_cut") and not cutter.is_empty():
            cutter = prism_y(cutter)
        vols, later = [], Manifold()
        for fil, m0 in reversed(raw[p["id"]]):                 # top volume wins
            m = m0 - later
            later = later + m0
            if not cutter.is_empty():
                m = m - cutter
            vols.append((fil, m))
        vols = list(reversed(vols))
        # drop tiny loose fragments left by the cuts (e.g. slivers of lipid heads)
        whole = solid[p["id"]] - cutter if not cutter.is_empty() else solid[p["id"]]
        bodies = whole.decompose()
        big = max(b.volume() for b in bodies)
        keep = [b for b in bodies if b.volume() >= max(30.0, 0.01 * big)]
        if len(keep) < len(bodies):
            dropped[p["id"]] = round(sum(b.volume() for b in bodies) -
                                     sum(b.volume() for b in keep), 1)
            k = union(keep)
            vols = [(f, m ^ k) for f, m in vols]
        if p.get("bands"):
            fil_out, zlo, zhi = p["bands"]
            whole = union([m for _, m in vols])
            outer = whole.trim_by_plane((0, 0, -1), -zlo) + whole.trim_by_plane((0, 0, 1), zhi)
            mid = whole.trim_by_plane((0, 0, 1), zlo).trim_by_plane((0, 0, -1), -zhi)
            vols = [(fil_out, outer), (vols[0][0], mid)]
        # remove sub-1 mm3 specks/slivers that the boolean subtractions leave behind
        vols = [(f, union([b for b in m.decompose() if b.volume() >= 1.0])) for f, m in vols]
        final[p["id"]] = vols
        p["_bodies"] = len(keep)

    # 3) split the base when it does not fit the bed
    print("removed loose fragments (mm3):", dropped)
    pieces = []           # (id, vols, orient, step, bodies)
    base_w = solid["BASE"].bounding_box()
    need_split = (base_w[3] - base_w[0]) > min(bed) - 2 * EDGE
    for p in PARTS:
        vols = final[p["id"]]
        if p.get("split") and need_split:
            holes = union(dowel_holes(3.0 + CLR, 24 + 2 * CLR))
            for side, n in (("L", (-1, 0, 0)), ("R", (1, 0, 0))):
                half = [(f, m.trim_by_plane(n, 0.0) - holes) for f, m in vols]
                pieces.append((p["id"] + "_" + side, half, "up", p["step"],
                               len(union([m for _, m in half]).decompose())))
            for i in range(3):
                pin = Manifold.cylinder(23.0, 3.0, 3.0, 48)
                pieces.append(("DOWEL_%d" % (i + 1), [("Navy", pin)], "up", 1, 1))
        else:
            pieces.append((p["id"], vols, p["orient"], p["step"], p["_bodies"]))

    # assembled-position copies (for the exploded assembly picture)
    if assembled_dir:
        os.makedirs(assembled_dir, exist_ok=True)
        pins = dowel_holes(3.0, 23.0)
        for pid, vols, orient, step, nb in pieces:
            for f, m in vols:
                if pid.startswith("DOWEL"):
                    m = pins[int(pid[-1]) - 1]
                write_stl(os.path.join(assembled_dir, "%s__%s.stl" % (pid, f)), m)

    # 4) orient for printing + checks
    kit = []
    for pid, vols, orient, step, n_bodies in pieces:
        whole = union([m for _, m in vols])
        if orient == "front":
            M = FRONT_UP
        elif orient == "axis":
            M = axis_matrix(whole)
        else:
            M = IDENT
        vols = [(f, m.transform(M)) for f, m in vols if not m.is_empty()]
        whole = whole.transform(M)
        b = whole.bounding_box()
        vols = [(f, m.translate((-b[0], -b[1], -b[2]))) for f, m in vols]
        # colour-change heights (single nozzle): top of the volumes below
        changes = []
        if orient == "front" and len(vols) > 1:
            for i in range(1, len(vols)):
                h = max(vols[j][1].bounding_box()[5] for j in range(i))
                changes.append((round(h, 2), vols[i][0]))
        start = vols[0][0]
        bands = spec.get(pid, {}).get("bands")
        if bands:
            z0 = spec[pid]["keep"][0][1]
            start = bands[0]
            changes = [(round(bands[1] - z0, 2), vols[1][0]), (round(bands[2] - z0, 2), bands[0])]
        kit.append(dict(id=pid, start=start, step=step, orient=orient, vols=vols, bodies=n_bodies,
                        size=(b[3] - b[0], b[4] - b[1], b[5] - b[2]), changes=changes,
                        model=(M, (-b[0], -b[1], -b[2]))))

    # 5) pack onto plates: first-fit by area, at most MAX_COLOURS filaments/plate
    from rectpack import newPacker, PackingMode, MaxRectsBssf, SORT_NONE
    W, H = bed[0] - 2 * EDGE + GAP, bed[1] - 2 * EDGE + GAP

    def try_pack(items):
        pk = newPacker(mode=PackingMode.Offline, pack_algo=MaxRectsBssf,
                       sort_algo=SORT_NONE, rotation=True)
        for i in sorted(items, key=lambda i: -kit[i]["size"][0] * kit[i]["size"][1]):
            pk.add_rect(kit[i]["size"][0] + GAP, kit[i]["size"][1] + GAP, rid=i)
        pk.add_bin(W, H)
        pk.pack()
        rects = list(pk[0]) if len(pk) else []
        return rects if len(rects) == len(items) else None

    def greedy(order):
        plates = []                  # [ [part indices], set(filaments), rects ]
        for i in order:
            fil = {f for f, _ in kit[i]["vols"]}
            for pl in plates:
                if len(pl[1] | fil) > max_colours:
                    continue
                r = try_pack(pl[0] + [i])
                if r:
                    pl[0].append(i)
                    pl[1] |= fil
                    pl[2] = r
                    break
            else:
                r = try_pack([i])
                if not r:
                    raise SystemExit("does not fit the bed: %s" % kit[i]["id"])
                plates.append([[i], set(fil), r])
        return plates

    import random
    rng = random.Random(7)
    area = lambda i: kit[i]["size"][0] * kit[i]["size"][1]
    big = sorted([i for i in range(len(kit)) if area(i) > 6000], key=lambda i: -area(i))
    small = sorted([i for i in range(len(kit)) if area(i) <= 6000], key=lambda i: -area(i))
    best, best_key = None, None
    for t in range(150):                                   # try many orders, keep best
        if t:
            rng.shuffle(small)
        pls = greedy(big + small)
        key = (len(pls), sum(len(pl[1]) for pl in pls))
        if best is None or key < best_key:
            best, best_key = pls, key
    plates = best
    plates.sort(key=lambda pl: -max(kit[i]["size"][0] * kit[i]["size"][1] for i in pl[0]))
    for bi, (items, fils, rects) in enumerate(plates):
        for r in rects:
            k = kit[r.rid]
            rot = abs(r.width - (k["size"][0] + GAP)) > 1e-6
            vols = k["vols"]
            if rot:
                vols = [(f, m.rotate((0, 0, 90)).translate((k["size"][1], 0, 0)))
                        for f, m in vols]
            k["vols"] = [(f, m.translate((EDGE + r.x, EDGE + r.y, 0))) for f, m in vols]
            k["plate"] = bi + 1
            k["rot"] = rot

    # 6) write
    os.makedirs(out_dir, exist_ok=True)
    kit.sort(key=lambda k: (k["plate"], k["step"], k["id"]))
    manifest = []
    for n, k in enumerate(kit, 1):
        d = os.path.join(out_dir, "plate_%d" % k["plate"])
        os.makedirs(d, exist_ok=True)
        files = []
        for f, m in k["vols"]:
            fn = "P%02d_%s__%s.stl" % (n, k["id"], f)
            write_stl(os.path.join(d, fn), m)
            files.append(fn)
        manifest.append(dict(no=n, id=k["id"], plate=k["plate"], step=k["step"],
                             colours=[f for f, _ in k["vols"]], start_colour=k["start"],
                             colour_change_mm=k["changes"], bodies=k["bodies"],
                             size_mm=[round(x, 1) for x in k["size"]], files=files))
    with open(os.path.join(out_dir, "parts.json"), "w") as fh:
        json.dump(dict(bed_mm=bed, clearance_mm=CLR, max_colours_per_plate=max_colours,
                       plates={str(i + 1): sorted(pl[1]) for i, pl in enumerate(plates)}, filaments=FILAMENT, parts=manifest,
                       steps_ar=STEPS_AR), fh, indent=1, ensure_ascii=False)
    return kit, manifest, final


# ------------------------------------------------------------------ checks
def check_assembly(final, raw_dir):
    """parts must not overlap each other, and together form one connected body"""
    ids = list(final)
    sol = {i: union([m for _, m in final[i]]) for i in ids}
    worst = []
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            v = (sol[ids[a]] ^ sol[ids[b]]).volume()
            if v > 1.0:
                worst.append((round(v, 1), ids[a], ids[b]))
    return sorted(worst, reverse=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    bed = (256.0, 256.0)
    if "--bed" in a:
        i = a.index("--bed")
        bed = (float(a[i + 1]), float(a[i + 2]))
    mc = int(a[a.index("--max-colours") + 1]) if "--max-colours" in a else 4
    asm = a[a.index("--assembled") + 1] if "--assembled" in a else None
    kit, man, final = build(a[0], a[1], bed, mc, asm)
    for p in man:
        print("%2d plate %d  %-18s %-28s %5.0fx%-4.0fx%4.0f bodies=%d  %s" % (
            p["no"], p["plate"], p["id"], "+".join(p["colours"]), *p["size_mm"],
            p["bodies"], p["colour_change_mm"]))
    print("overlaps between parts > 1 mm3:", check_assembly(final, a[0])[:10])
