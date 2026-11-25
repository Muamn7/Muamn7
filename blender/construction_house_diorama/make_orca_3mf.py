# -*- coding: utf-8 -*-
"""
يحوّل ملفات STL إلى ملف مشروع 3MF لبرنامج OrcaSlicer مرتّب على صفائح (Plates)
لطابعة Creality K1 (سرير 220 × 220 مم).

Build an OrcaSlicer project 3MF (Bambu/Orca plate format) from output/stl/*.stl
  python3 make_orca_3mf.py            -> output/construction_house_K1.3mf

Pure Python (no Blender needed).
"""
import math
import os
import struct
import uuid
import zipfile
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
STL_DIR = os.path.join(HERE, "output", "stl")
OUT = os.path.join(HERE, "output", "construction_house_K1.3mf")

BED = 220.0            # Creality K1 printable area 220 x 220 (Z 250)
SCALE = 0.88           # house 242 mm -> 213 mm so it fits the K1 bed
PLATE_GAP = 1.0 / 5.0  # Orca: LOGICAL_PART_PLATE_GAP
APP = "OrcaSlicer-2.2.0"


# ---------------------------------------------------------------------------
def read_stl(path):
    with open(path, "rb") as fh:
        data = fh.read()
    n = struct.unpack_from("<I", data, 80)[0]
    tris = []
    off = 84
    for _ in range(n):
        v = struct.unpack_from("<12f", data, off)
        tris.append((v[3:6], v[6:9], v[9:12]))
        off += 50
    return tris


def index_mesh(tris):
    """dedupe vertices -> (verts, faces); drop degenerate triangles"""
    lut, verts, faces = {}, [], []
    for tri in tris:
        idx = []
        for p in tri:
            key = (round(p[0], 4), round(p[1], 4), round(p[2], 4))
            i = lut.get(key)
            if i is None:
                i = lut[key] = len(verts)
                verts.append(key)
            idx.append(i)
        if len(set(idx)) == 3:
            faces.append(tuple(idx))
    return verts, faces


def split_parts(verts, faces):
    """split a mesh into connected components"""
    parent = list(range(len(verts)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b, c in faces:
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra
        parent[find(rc)] = ra
    groups = {}
    for f in faces:
        groups.setdefault(find(f[0]), []).append(f)
    parts = []
    for fs in groups.values():
        remap, nv, nf = {}, [], []
        for f in fs:
            t = []
            for i in f:
                if i not in remap:
                    remap[i] = len(nv)
                    nv.append(verts[i])
                t.append(remap[i])
            nf.append(tuple(t))
        parts.append((nv, nf))
    return parts


def transform(verts, rx=0.0, rz=0.0, s=SCALE):
    """scale, rotate about X then Z, and centre on the bbox (z centre too)"""
    ax, az = math.radians(rx), math.radians(rz)
    cx_, sx_ = math.cos(ax), math.sin(ax)
    cz_, sz_ = math.cos(az), math.sin(az)
    out = []
    for x, y, z in verts:
        x, y, z = x * s, y * s, z * s
        y, z = y * cx_ - z * sx_, y * sx_ + z * cx_
        x, y = x * cz_ - y * sz_, x * sz_ + y * cz_
        out.append((x, y, z))
    mn = [min(p[i] for p in out) for i in range(3)]
    mx = [max(p[i] for p in out) for i in range(3)]
    c = [(mn[i] + mx[i]) / 2 for i in range(3)]
    out = [(p[0] - c[0], p[1] - c[1], p[2] - c[2]) for p in out]
    size = [mx[i] - mn[i] for i in range(3)]
    return out, size


def plate_origin(index, count):
    """same grid OrcaSlicer uses for its plates"""
    value = math.sqrt(count)
    cols = int(round(value)) + (1 if value > round(value) else 0)
    row, col = divmod(index, cols)
    stride = BED * (1.0 + PLATE_GAP)
    return col * stride, -row * stride


# ---------------------------------------------------------------------------
# plate layout:  (plate name, [(stl file, display name, rx, rz, x, y, supports), ...])
PLATES = [
    ("الطابق الأرضي", [("05_GroundFloor.stl", "الطابق الأرضي GroundFloor", 0, 0, 110, 110, False)]),
    ("الطابق الثاني", [("06_FirstFloor.stl", "الطابق الثاني FirstFloor", 0, 0, 110, 110, False)]),
    ("السطح", [("07_Roof.stl", "السطح Roof", 0, 0, 110, 110, False)]),
    ("المعدات", [
        ("09_CementBags_Pallet.stl", "أكياس السمنت CementBags", 0, 0, 36, 182, False),
        ("10_MortarBoard.stl", "طبلية السمنت MortarBoard", 0, -12, 108, 182, False),
        ("14_SandPile.stl", "كومة الرمل SandPile", 0, -25, 182, 184, False),
        ("08_Wheelbarrow.stl", "العربانة Wheelbarrow", 0, 30, 62, 112, True),
        ("11_Shovel.stl", "الكرك Shovel", -78, 90, 158, 120, True),
        ("12_Bucket.stl", "السطل Bucket", 0, 0, 196, 64, True),
        ("13_LooseBricks.stl", "طابوق LooseBricks", 0, 0, None, None, False),
    ]),
    ("القاعدة 1", [("01_Base_1.stl", "القاعدة Base_1", 0, 0, 110, 110, False)]),
    ("القاعدة 2", [("02_Base_2.stl", "القاعدة Base_2", 0, 0, 110, 110, False)]),
    ("القاعدة 3", [("03_Base_3.stl", "القاعدة Base_3", 0, 0, 110, 110, False)]),
    ("القاعدة 4", [("04_Base_4.stl", "القاعدة Base_4", 0, 0, 110, 110, False)]),
]
# the loose bricks file holds several separate bricks: lay them out in a row
BRICK_SLOTS = [(28, 40), (58, 40), (86, 40), (114, 40), (142, 40), (170, 40), (28, 70), (58, 70)]


def build_objects():
    objects = []   # dicts: name, verts, faces, plate, pos, size, support
    for pi, (pname, items) in enumerate(PLATES):
        for fname, name, rx, rz, x, y, sup in items:
            verts, faces = index_mesh(read_stl(os.path.join(STL_DIR, fname)))
            if x is None:
                parts = sorted(split_parts(verts, faces), key=lambda p: -len(p[1]))
                for k, (pv, pf) in enumerate(parts):
                    v, size = transform(pv, rx, 0)
                    bx, by = BRICK_SLOTS[k]
                    objects.append(dict(name=f"{name} {k + 1}", verts=v, faces=pf, plate=pi,
                                        pos=(bx, by), size=size, support=sup))
                continue
            v, size = transform(verts, rx, rz)
            objects.append(dict(name=name, verts=v, faces=faces, plate=pi, pos=(x, y),
                                size=size, support=sup))
    return objects


def check_layout(objects):
    for o in objects:
        x, y = o["pos"]
        sx, sy, sz = o["size"]
        assert 1 <= x - sx / 2 and x + sx / 2 <= BED - 1, (o["name"], "x", x, sx)
        assert 1 <= y - sy / 2 and y + sy / 2 <= BED - 1, (o["name"], "y", y, sy)
        assert sz <= 250, o["name"]
    # no overlaps between footprints on the same plate
    for i, a in enumerate(objects):
        for b in objects[i + 1:]:
            if a["plate"] != b["plate"]:
                continue
            ox = abs(a["pos"][0] - b["pos"][0]) < (a["size"][0] + b["size"][0]) / 2 + 2
            oy = abs(a["pos"][1] - b["pos"][1]) < (a["size"][1] + b["size"][1]) / 2 + 2
            assert not (ox and oy), ("overlap", a["name"], b["name"])


# ---------------------------------------------------------------------------
NS = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
      'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
      'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
      'requiredextensions="p"')


def uid():
    return str(uuid.uuid4())


def mesh_model(obj_id, verts, faces):
    out = ['<?xml version="1.0" encoding="UTF-8"?>\n',
           f'<model unit="millimeter" xml:lang="en-US" {NS}>\n',
           ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n',
           ' <resources>\n',
           f'  <object id="{obj_id}" p:UUID="{uid()}" type="model">\n   <mesh>\n    <vertices>\n']
    out += [f'     <vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>\n' for x, y, z in verts]
    out.append('    </vertices>\n    <triangles>\n')
    out += [f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>\n' for a, b, c in faces]
    out.append('    </triangles>\n   </mesh>\n  </object>\n </resources>\n <build/>\n</model>\n')
    return "".join(out)


def write_3mf(objects, path):
    n_plates = len(PLATES)
    main_res, build, rels, settings_obj, assemble = [], [], [], [], []
    plates = {i: [] for i in range(n_plates)}
    files = {}
    for k, o in enumerate(objects):
        mesh_id, outer_id = 2 * k + 1, 2 * k + 2
        fpath = f"3D/Objects/object_{mesh_id}.model"
        files[fpath] = mesh_model(mesh_id, o["verts"], o["faces"])
        rels.append(f' <Relationship Target="/{fpath}" Id="rel-{k + 1}" '
                    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n')
        main_res.append(
            f'  <object id="{outer_id}" p:UUID="{uid()}" type="model">\n'
            f'   <components>\n'
            f'    <component p:path="/{fpath}" objectid="{mesh_id}" p:UUID="{uid()}" '
            f'transform="1 0 0 0 1 0 0 0 1 0 0 0"/>\n'
            f'   </components>\n  </object>\n')
        px, py = plate_origin(o["plate"], n_plates)
        tx, ty, tz = px + o["pos"][0], py + o["pos"][1], o["size"][2] / 2
        tr = f"1 0 0 0 1 0 0 0 1 {tx:.4f} {ty:.4f} {tz:.4f}"
        build.append(f'  <item objectid="{outer_id}" p:UUID="{uid()}" transform="{tr}" printable="1"/>\n')
        name = escape(o["name"], {'"': "&quot;"})
        extra = ""
        if o["support"]:
            extra = ('    <metadata key="enable_support" value="1"/>\n'
                     '    <metadata key="support_type" value="tree(auto)"/>\n')
        settings_obj.append(
            f'  <object id="{outer_id}">\n'
            f'    <metadata key="name" value="{name}"/>\n'
            f'    <metadata key="extruder" value="1"/>\n{extra}'
            f'    <part id="{mesh_id}" subtype="normal_part">\n'
            f'      <metadata key="name" value="{name}"/>\n'
            f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
            f'      <mesh_stat edges_fixed="0" degenerate_facets="0" facets_removed="0" '
            f'facets_reversed="0" backwards_edges="0"/>\n'
            f'    </part>\n  </object>\n')
        plates[o["plate"]].append(outer_id)
        assemble.append(f'   <assemble_item object_id="{outer_id}" instance_id="0" '
                        f'transform="{tr}" offset="0 0 0" />\n')

    plate_xml = []
    for i in range(n_plates):
        inst = "".join(
            f'    <model_instance>\n'
            f'      <metadata key="object_id" value="{oid}"/>\n'
            f'      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{1000 + oid}"/>\n'
            f'    </model_instance>\n' for oid in plates[i])
        plate_xml.append(
            f'  <plate>\n'
            f'    <metadata key="plater_id" value="{i + 1}"/>\n'
            f'    <metadata key="plater_name" value="{escape(PLATES[i][0])}"/>\n'
            f'    <metadata key="locked" value="false"/>\n{inst}  </plate>\n')

    files["3D/3dmodel.model"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<model unit="millimeter" xml:lang="en-US" {NS}>\n'
        f' <metadata name="Application">{APP}</metadata>\n'
        ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
        ' <metadata name="Title">Construction House Diorama - Creality K1</metadata>\n'
        ' <resources>\n' + "".join(main_res) + ' </resources>\n'
        f' <build p:UUID="{uid()}">\n' + "".join(build) + ' </build>\n</model>\n')
    files["3D/_rels/3dmodel.model.rels"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        + "".join(rels) + '</Relationships>\n')
    files["Metadata/model_settings.config"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + "".join(settings_obj)
        + "".join(plate_xml) + '  <assemble>\n' + "".join(assemble) + '  </assemble>\n</config>\n')
    files["[Content_Types].xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        ' <Default Extension="png" ContentType="image/png"/>\n'
        ' <Default Extension="gcode" ContentType="text/x.gcode"/>\n'
        '</Types>\n')
    files["_rels/.rels"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        '</Relationships>\n')

    order = ["[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model", "3D/_rels/3dmodel.model.rels"]
    order += sorted(k for k in files if k.startswith("3D/Objects/")) + ["Metadata/model_settings.config"]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in order:
            z.writestr(name, files[name].encode("utf-8"))


def main():
    objects = build_objects()
    check_layout(objects)
    write_3mf(objects, OUT)
    for o in objects:
        sx, sy, sz = o["size"]
        print(f"plate {o['plate'] + 1}: {o['name']:32s} {sx:6.1f} x {sy:6.1f} x {sz:6.1f} mm")
    print("written", OUT, os.path.getsize(OUT) // 1024, "KB")


if __name__ == "__main__":
    main()
