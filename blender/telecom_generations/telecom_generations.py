# -*- coding: utf-8 -*-
"""
"Generations of Communication" display model - 1G to 5G
========================================================

Blender script that builds the whole display at real-world scale:
  * Total height = exactly 60 cm (bottom of the base to the top of the 5G disc)
  * Width = 70 cm, depth = 22 cm
  * Scene unit: metre, displayed in centimetres

How to use inside Blender (3.6 / 4.x / 5.x):
  1. Open the Scripting workspace
  2. Text > Open this file and press Run Script
  3. Keep DejaVuSans-Bold.ttf next to this file (shipped with it);
     otherwise the script falls back to Tahoma / Arial Bold automatically.

Or from the command line:
  blender -b -P telecom_generations.py -- --save model.blend --render front.png

Every generation lives in its own collection and is parented to one Empty
(1G_Root ... 5G_Root) so it can be moved as a unit.
All label text is in the TEXT dictionary below - edit it and re-run.
"""

import bpy
import bmesh
import math
import os
import sys
from mathutils import Matrix, Vector

# ---------------------------------------------------------------------------
# General settings
# ---------------------------------------------------------------------------
TOTAL_HEIGHT_CM = 60.0      # required total height
CLEAR_SCENE = True          # delete the current scene content first
BUILD_ENVIRONMENT = True    # wooden table + wall + lights + cameras

# All text that appears on the model
TEXT = {
    "title": "Generations of Communication",
    "subtitle": "From the First Generation ... to the Fifth Generation",
    "g1a": "Voice Calls Only", "g1b": "Analog Network",
    "g2a": "Voice & Text (SMS)", "g2b": "Digital Network",
    "g3a": "Web on Your Phone", "g3b": "Photos & Video",
    "g4a": "High-Speed Internet", "g4b": "Live Streaming",
    "g5a": "Ultra-Fast Speeds", "g5b": "Smart Connectivity",
}

GENERATIONS = [
    # label, years, description line 1, line 2, tag line, column color, icon colors
    dict(g="1G", years="(1980s)", a="g1a", b="g1b", en="(Analog)",
         color="#353537", ring="#353537", icon_bg="#e6e6e6", icon_fg="#5a5a5a"),
    dict(g="2G", years="(1990s)", a="g2a", b="g2b", en="(Digital)",
         color="#1452c4", ring="#1452c4", icon_bg="#1452c4", icon_fg="#ffffff"),
    dict(g="3G", years="(2000s)", a="g3a", b="g3b", en="(Mobile Internet)",
         color="#138a3a", ring="#138a3a", icon_bg="#138a3a", icon_fg="#ffffff"),
    dict(g="4G", years="(2010s)", a="g4a", b="g4b", en="(HD Video)",
         color="#ea6410", ring="#ea6410", icon_bg="#ea6410", icon_fg="#ffffff"),
    dict(g="5G", years="(2020s \u2192)", a="g5a", b="g5b", en="(IoT - AI)",
         color="#6a2fb8", ring="#6a2fb8", icon_bg="#6a2fb8", icon_fg="#ffffff"),
]

# Every dimension in this file is in cm and converted to metres here
S = TOTAL_HEIGHT_CM / 60.0 * 0.01


def V(x, y, z):
    return Vector((x * S, y * S, z * S))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def srgb(hexstr, alpha=1.0):
    h = hexstr.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (out[0], out[1], out[2], alpha)


def set_input(node, names, value):
    for n in names:
        if n in node.inputs:
            try:
                node.inputs[n].default_value = value
                return True
            except Exception:
                pass
    return False


_MATS = {}


def mat(name, color, rough=0.5, metal=0.0, emit=0.0, coat=0.0, emit_color=None):
    key = name
    if key in _MATS:
        return _MATS[key]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = None
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            bsdf = n
    col = srgb(color) if isinstance(color, str) else color
    set_input(bsdf, ["Base Color"], col)
    set_input(bsdf, ["Roughness"], rough)
    set_input(bsdf, ["Metallic"], metal)
    if coat:
        set_input(bsdf, ["Coat Weight", "Clearcoat"], coat)
        set_input(bsdf, ["Coat Roughness", "Clearcoat Roughness"], 0.05)
    if emit:
        ec = emit_color if emit_color is not None else col
        ec = srgb(ec) if isinstance(ec, str) else ec
        set_input(bsdf, ["Emission Color", "Emission"], ec)
        set_input(bsdf, ["Emission Strength"], emit)
    m.diffuse_color = col
    _MATS[key] = m
    return m


def get_coll(name, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


class Ctx:
    """Current collection and parent for every new object"""
    coll = None
    parent = None


def _finish(ob, material, parent):
    Ctx.coll.objects.link(ob)
    if material is not None:
        ob.data.materials.append(material)
    p = parent if parent is not None else Ctx.parent
    if p is not None:
        ob.parent = p
    return ob


def empty(name, loc=(0, 0, 0), parent=None):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_type = "PLAIN_AXES"
    ob.empty_display_size = 5 * S
    ob.location = V(*loc)
    return _finish(ob, None, parent)


def _smooth_bevel(ob, me, bevel, seg, angle=None):
    if bevel <= 0:
        return
    mod = ob.modifiers.new("Bevel", "BEVEL")
    mod.width = bevel * S
    mod.segments = seg
    mod.use_clamp_overlap = True
    if angle is not None:
        mod.limit_method = "ANGLE"
        mod.angle_limit = math.radians(angle)
    try:
        mod.harden_normals = True
    except Exception:
        pass
    if hasattr(me, "use_auto_smooth"):
        me.use_auto_smooth = True
    for p in me.polygons:
        p.use_smooth = True


def box(name, center, size, material, bevel=0.0, seg=3, parent=None):
    """Box with real dimensions (cm) and optional bevelled edges"""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size) * S, verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = V(*center)
    _finish(ob, material, parent)
    _smooth_bevel(ob, me, bevel, seg)
    return ob


def rrect(w, h, r, seg=8):
    """Rounded-rectangle outline points (counter-clockwise)"""
    r = max(0.0, min(r, w / 2 - 1e-4, h / 2 - 1e-4))
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90.0 * i / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def circle(r, n=64, cx=0.0, cy=0.0, rx=None):
    rx = r if rx is None else rx
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def prism(name, pts, depth, center, material, plane="XZ", bevel=0.0, seg=2,
          bevel_angle=30, parent=None):
    """Extruded 2D outline.
    plane='XZ' : outline on the front plane, thickness along -Y (towards the viewer)
    plane='XY' : horizontal outline, thickness along +Z
    """
    area = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        area += x1 * y2 - x2 * y1
    if area < 0:
        pts = list(reversed(pts))

    def mp(u, v, d):
        if plane == "XZ":
            return Vector((u * S, -d * S, v * S))
        return Vector((u * S, v * S, d * S))

    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    lo = [bm.verts.new(mp(u, v, -depth / 2)) for u, v in pts]
    hi = [bm.verts.new(mp(u, v, depth / 2)) for u, v in pts]
    n = len(pts)
    bm.faces.new(hi)
    bm.faces.new(list(reversed(lo)))
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = V(*center)
    _finish(ob, material, parent)
    _smooth_bevel(ob, me, bevel, seg, angle=bevel_angle)
    return ob


def tube(name, pts, thick, center, material, cyclic=False, plane="XZ", parent=None):
    """Round tube along a polyline / arc"""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = thick / 2 * S
    cu.bevel_resolution = 4
    try:
        cu.use_fill_caps = True
    except Exception:
        pass
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, (u, v) in enumerate(pts):
        if plane == "XZ":
            sp.points[i].co = (u * S, 0.0, v * S, 1.0)
        else:
            sp.points[i].co = (u * S, v * S, 0.0, 1.0)
    sp.use_cyclic_u = cyclic
    ob = bpy.data.objects.new(name, cu)
    ob.location = V(*center)
    return _finish(ob, material, parent)


def arc_pts(r, a0, a1, n=24, cx=0.0, cy=0.0):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


FONT = None


def load_font():
    here = ""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        pass
    cands = []
    for t in bpy.data.texts:
        if t.filepath:
            cands.append(os.path.join(os.path.dirname(bpy.path.abspath(t.filepath)),
                                      "DejaVuSans-Bold.ttf"))
    cands += [
        os.environ.get("TELECOM_FONT", ""),
        os.path.join(here, "DejaVuSans-Bold.ttf"),
        os.path.join(os.path.dirname(bpy.data.filepath or ""), "DejaVuSans-Bold.ttf"),
        "C:/Windows/Fonts/tahomabd.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in cands:
        if p and os.path.isfile(p):
            print("[telecom] font:", p)
            return bpy.data.fonts.load(p, check_existing=True)
    print("[telecom] WARNING: DejaVuSans-Bold.ttf not found, using Blender's built-in font")
    return bpy.data.fonts.get("Bfont") or bpy.data.fonts.load("<builtin>")


def text(name, body, size, center, material, maxw=None, depth=0.06, plane="XZ",
         flip=False, parent=None, bold=0.0):
    """3D text on the front plane, auto-shrunk to fit width maxw (cm)"""
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = FONT
    cu.size = size * S
    cu.extrude = depth / 2 * S
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    ob = bpy.data.objects.new(name, cu)
    ob.location = V(*center)
    if plane == "XZ":
        ob.rotation_euler = (math.radians(90), 0, math.radians(180) if flip else 0)
    _finish(ob, material, parent)
    if maxw:
        bpy.context.view_layer.update()
        w = ob.dimensions.x / S
        if w > maxw:
            cu.size *= maxw / w
    return ob


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
def materials():
    M = {}
    M["base"] = mat("Base_Black", "#0b0c0e", rough=0.38, coat=0.15)
    M["white"] = mat("Card_White", "#f4f4f2", rough=0.55)
    M["ink"] = mat("Ink_Black", "#0a0a0a", rough=0.45)
    M["border"] = mat("Card_Border", "#111111", rough=0.5)
    M["led"] = mat("LED_Blue", "#2a7bff", rough=0.3, emit=18.0, emit_color="#2f86ff")
    M["led_diff"] = mat("LED_Diffuser", "#9cc6ff", rough=0.15, emit=6.0,
                        emit_color="#3d8cff")
    M["glass"] = mat("Screen_Glass", "#020304", rough=0.04, coat=1.0)
    M["frame"] = mat("Phone_Frame", "#2a2c30", rough=0.28, metal=0.85)
    M["frame_light"] = mat("Phone_Frame_Silver", "#b9bec6", rough=0.25, metal=0.9)
    M["lens"] = mat("Camera_Lens", "#050608", rough=0.05, coat=1.0)
    M["sign_white"] = mat("Sign_White", "#f7f7f5", rough=0.45)
    return M


# ---------------------------------------------------------------------------
# Phones
# ---------------------------------------------------------------------------
def phone_brick(M):
    """1G brick phone with antenna"""
    body = mat("1G_Phone_Body", "#232325", rough=0.42)
    face = mat("1G_Phone_Face", "#303033", rough=0.5)
    key = mat("1G_Key", "#c3c4c6", rough=0.45)
    key_g = mat("1G_Key_Green", "#2fa84f", rough=0.4)
    key_r = mat("1G_Key_Red", "#cf2b2b", rough=0.4)
    lcd = mat("1G_LCD", "#140504", rough=0.08, coat=1.0)
    led = mat("1G_LED_Red", "#ff2a1a", rough=0.3, emit=6.0)
    ink = mat("1G_Key_Ink", "#1b1b1b", rough=0.5)

    W, T, H = 4.4, 2.6, 11.0
    fy = -T / 2
    box("1G_Body", (0, 0, H / 2), (W, T, H), body, bevel=0.45, seg=4)
    prism("1G_FacePlate", rrect(W - 0.5, H - 0.6, 0.35), 0.1, (0, fy - 0.02, H / 2), face,
          bevel=0.03)
    # earpiece
    for i in range(4):
        prism(f"1G_Speaker_{i}", rrect(1.8, 0.14, 0.07), 0.1,
              (0, fy - 0.08, H - 0.75 - i * 0.28), M["ink"])
    # display
    prism("1G_LCD_Frame", rrect(3.3, 1.55, 0.2), 0.12, (0, fy - 0.08, 8.85), M["ink"],
          bevel=0.03)
    prism("1G_LCD", rrect(2.95, 1.2, 0.12), 0.06, (0, fy - 0.14, 8.85), lcd)
    # screen content: network type with handset and signal icons
    icon_handset("1G_LCD", led, fy - 0.18, 8.7, x=-1.05, k=0.32, d=0.01)
    text("1G_LCD_Text", "1G", 0.9, (0.1, fy - 0.19, 8.85), led, depth=0.02)
    signal_bars("1G_LCD", fy - 0.18, 8.45, 0.72, led, w=0.12, h0=0.22, dh=0.15, gap=0.06)
    # function keys
    for x, m in ((-1.25, key_g), (0, key), (1.25, key_r)):
        box(f"1G_FnKey_{x:+.0f}", (x, fy - 0.2, 7.35), (1.05, 0.4, 0.5), m, bevel=0.12, seg=3)
    labels = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"]
    for r in range(4):
        for c in range(3):
            x = (c - 1) * 1.25
            z = 6.3 - r * 1.1
            box(f"1G_Key_{labels[r * 3 + c]}", (x, fy - 0.22, z), (1.05, 0.44, 0.78), key,
                bevel=0.14, seg=3)
            text(f"1G_KeyTxt_{labels[r * 3 + c]}", labels[r * 3 + c], 0.5,
                 (x, fy - 0.45, z), ink, depth=0.02)
    # microphone
    for i in range(3):
        prism(f"1G_Mic_{i}", circle(0.1, 16), 0.1, ((i - 1) * 0.4, fy - 0.06, 1.15), M["ink"])
    # antenna
    prism("1G_Antenna_Base", circle(0.48, 32), 0.9, (1.15, 0, H + 0.4), body, plane="XY",
          bevel=0.08)
    prism("1G_Antenna", circle(0.2, 24), 4.6, (1.15, 0, H + 2.9), M["ink"], plane="XY",
          bevel=0.05)
    prism("1G_Antenna_Tip", circle(0.32, 32), 0.6, (1.15, 0, H + 5.3), M["ink"], plane="XY",
          bevel=0.2, seg=4)
    return H, T


def phone_candybar(M):
    """2G candybar phone with keypad and small LCD"""
    shell = mat("2G_Back_Shell", "#2b2f38", rough=0.38)
    cover = mat("2G_Front_Cover", "#2c4f8f", rough=0.3, coat=0.4)
    bezel = mat("2G_Screen_Bezel", "#aab3c0", rough=0.35, metal=0.3)
    lcd = mat("2G_LCD", "#a9bd96", rough=0.2, emit=0.6, emit_color="#a9c58c")
    pix = mat("2G_LCD_Pixels", "#1d2b16", rough=0.6)
    key = mat("2G_Key", "#d3d9e2", rough=0.4)
    nav = mat("2G_Nav_Key", "#9aa4b3", rough=0.3, metal=0.4)
    ink = mat("2G_Key_Ink", "#1c2333", rough=0.5)

    W, T, H = 4.8, 2.1, 11.0
    fy = -T / 2
    prism("2G_Shell", rrect(W, H, 1.7, 10), T, (0, 0, H / 2), shell, bevel=0.55, seg=4)
    prism("2G_Cover", rrect(W - 0.25, H - 0.25, 1.6, 10), 0.5, (0, fy + 0.1, H / 2), cover,
          bevel=0.2, seg=3)
    prism("2G_Bezel", rrect(3.7, 3.6, 0.7), 0.12, (0, fy - 0.2, 7.95), bezel, bevel=0.05)
    prism("2G_LCD", rrect(2.85, 2.35, 0.18), 0.06, (0, fy - 0.27, 8.05), lcd)
    # screen content: network type with envelope (SMS) and signal icons
    text("2G_LCD_Text", "2G", 1.35, (0, fy - 0.31, 8.55), pix, maxw=2.4, depth=0.01)
    icon_envelope("2G_LCD", pix, lcd, fy - 0.305, 7.35, x=-0.6, k=0.3, d=0.01)
    signal_bars("2G_LCD", fy - 0.305, 7.05, 0.25, pix, w=0.16, h0=0.22, dh=0.13, gap=0.08)
    # navigation key
    prism("2G_Nav", rrect(2.7, 0.95, 0.47), 0.3, (0, fy - 0.2, 5.55), nav, bevel=0.1, seg=3)
    prism("2G_Nav_C", circle(0.33, 32), 0.3, (-1.75, fy - 0.15, 5.55), key, bevel=0.1)
    prism("2G_Nav_Up", circle(0.33, 32), 0.3, (1.75, fy - 0.15, 5.55), key, bevel=0.1)
    labels = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"]
    for r in range(4):
        for c in range(3):
            x = (c - 1) * 1.28
            z = 4.35 - r * 0.88
            prism(f"2G_Key_{labels[r * 3 + c]}", rrect(1.05, 0.62, 0.31), 0.3,
                  (x, fy - 0.15, z), key, bevel=0.1, seg=3)
            text(f"2G_KeyTxt_{labels[r * 3 + c]}", labels[r * 3 + c], 0.38,
                 (x, fy - 0.31, z), ink, depth=0.015)
    for i in range(5):
        prism(f"2G_Speaker_{i}", circle(0.07, 12), 0.1, ((i - 2) * 0.28, fy - 0.12, 10.25),
              M["ink"])
    return H, T


def smartphone_shell(M, tag, screen_color):
    W, T, H = 6.0, 0.8, 11.8
    fy = -T / 2
    prism(f"{tag}_Body", rrect(W, H, 0.85, 12), T, (0, 0, H / 2), M["frame"], bevel=0.16,
          seg=4)
    prism(f"{tag}_Glass", rrect(W - 0.14, H - 0.14, 0.8, 12), 0.04, (0, fy - 0.01, H / 2),
          M["glass"], bevel=0.015, seg=2)
    scr = mat(f"{tag}_Screen_BG", screen_color, rough=0.2, emit=1.4)
    prism(f"{tag}_Display", rrect(W - 0.55, H - 0.75, 0.55, 12), 0.01,
          (0, fy - 0.035, H / 2), scr)
    prism(f"{tag}_FrontCam", circle(0.13, 24), 0.01, (0, fy - 0.045, H - 0.62), M["lens"])
    # side buttons
    for i, (z, ln) in enumerate(((8.6, 1.4), (6.9, 0.9))):
        box(f"{tag}_SideBtn_{i}", (W / 2 + 0.03, 0, z), (0.12, 0.35, ln), M["frame"],
            bevel=0.05, seg=2)
    # rear camera
    by = T / 2
    prism(f"{tag}_CamBump", rrect(1.9, 1.9, 0.5), 0.14, (-1.6, by + 0.07, H - 1.5),
          M["glass"], bevel=0.05)
    for i, (dx, dz) in enumerate(((-0.42, 0.42), (-0.42, -0.42), (0.42, 0))):
        prism(f"{tag}_CamLens_{i}", circle(0.32, 32), 0.16, (-1.6 + dx, by + 0.16, H - 1.5 + dz),
              M["frame"], bevel=0.04)
        prism(f"{tag}_CamGlass_{i}", circle(0.22, 32), 0.17, (-1.6 + dx, by + 0.17, H - 1.5 + dz),
              M["lens"])
    return H, T, fy - 0.045   # height, thickness, screen surface


def smartphone(M, tag, screen_color, accent, icon):
    """Smartphone screen: only the network type, its icon and signal bars"""
    H, T, sy = smartphone_shell(M, tag, screen_color)
    fy = sy - 0.006
    white = mat(f"{tag}_UI_White", "#ffffff", rough=0.3, emit=2.4)
    halo = mat(f"{tag}_UI_Halo", accent, rough=0.3, emit=1.8)
    # generation icon inside a glowing disc
    prism(f"{tag}_Icon_Disc", circle(1.75, 64), 0.01, (0, fy, 8.55), halo)
    if icon == "globe":
        icon_globe(f"{tag}_Screen_Icon", white, fy - 0.03, 8.55, k=0.85)
    elif icon == "play":
        icon_play(f"{tag}_Screen_Icon", white, halo, fy - 0.01, 8.55, k=0.85, d=0.01)
    else:
        icon_network(f"{tag}_Screen_Icon", white, fy - 0.01, 8.55, k=0.95, d=0.01)
    # network type
    text(f"{tag}_Screen_Text", tag, 2.7, (0, fy - 0.01, 5.0), white, maxw=4.6, depth=0.01)
    # signal bars
    signal_bars(f"{tag}_Screen", fy - 0.004, 1.55, -1.5, white, w=0.55, h0=0.45, dh=0.4,
                gap=0.3)


def phone_3g(M):
    smartphone(M, "3G", "#0f3d22", "#1f9a48", "globe")


def phone_4g(M):
    smartphone(M, "4G", "#5a240a", "#f2751b", "play")


def phone_5g(M):
    smartphone(M, "5G", "#24104a", "#7b3fc4", "network")


# ---------------------------------------------------------------------------
# Base icons
# ---------------------------------------------------------------------------
def _detail(y, d):
    """y position and depth for the details drawn on top of an icon"""
    return y - (d / 2 + 0.02), min(0.04, d)


def icon_handset(pre, fg, y, z, x=0.0, k=1.0, d=0.12):
    pts_out, pts_in = [], []
    n = 40
    for i in range(n + 1):
        t = i / n
        th = math.radians(200 + 140 * t)
        pad = max(0.0, 1 - t / 0.22) ** 0.6 + max(0.0, 1 - (1 - t) / 0.22) ** 0.6
        ro = 1.2 + 0.32 * pad
        ri = 0.78 - 0.06 * pad
        pts_out.append((ro * math.cos(th), ro * math.sin(th)))
        pts_in.append((ri * math.cos(th), ri * math.sin(th)))
    pts = pts_out + list(reversed(pts_in))
    rot = math.radians(-30)
    pts = [(k * (u * math.cos(rot) - v * math.sin(rot)),
            k * (u * math.sin(rot) + v * math.cos(rot) + 0.55)) for u, v in pts]
    prism(f"{pre}_Handset", pts, d, (x, y, z), fg, bevel=0.03 if d > 0.05 else 0)


def icon_envelope(pre, fg, bg, y, z, x=0.0, k=1.0, d=0.12):
    prism(f"{pre}_Envelope", rrect(2.9 * k, 2.0 * k, 0.18 * k), d, (x, y, z), fg,
          bevel=0.03 if d > 0.05 else 0)
    yd, _ = _detail(y, d)
    tube(f"{pre}_Flap", [(-1.3 * k, 0.85 * k), (0, -0.15 * k), (1.3 * k, 0.85 * k)], 0.16 * k,
         (x, yd, z), bg)


def icon_globe(pre, fg, y, z, x=0.0, k=1.0):
    r = 1.4 * k
    tube(f"{pre}_Ring", circle(r, 64), 0.17 * k, (x, y, z), fg, cyclic=True)
    tube(f"{pre}_Meridian", circle(r, 64, rx=0.6 * k), 0.14 * k, (x, y, z), fg, cyclic=True)
    tube(f"{pre}_Axis", [(0, -r), (0, r)], 0.14 * k, (x, y, z), fg)
    tube(f"{pre}_Equator", [(-r, 0), (r, 0)], 0.14 * k, (x, y, z), fg)
    for zz in (-0.72 * k, 0.72 * k):
        hw = math.sqrt(r * r - zz * zz)
        tube(f"{pre}_Lat_{zz / k:+.1f}", [(-hw, zz), (hw, zz)], 0.14 * k, (x, y, z), fg)


def rounded_poly(centers, rr, seg=8):
    """Outline of a convex CCW polygon whose corners are rounded with radius rr
    (centers = the corner-circle centres)"""
    n = len(centers)
    out = []
    for i in range(n):
        px, py = centers[i - 1]
        cx, cy = centers[i]
        nx, ny = centers[(i + 1) % n]
        a0 = math.atan2(-(cx - px), cy - py)      # outward normal of incoming edge
        a1 = math.atan2(-(nx - cx), ny - cy)      # outward normal of outgoing edge
        while a1 < a0:
            a1 += 2 * math.pi
        for t in range(seg + 1):
            a = a0 + (a1 - a0) * t / seg
            out.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return out


def icon_play(pre, fg, bg, y, z, x=0.0, k=1.0, d=0.12):
    """4G: video player - rounded screen with a big play triangle"""
    prism(f"{pre}_Screen", rrect(3.0 * k, 2.15 * k, 0.5 * k), d, (x, y, z), fg,
          bevel=0.03 if d > 0.05 else 0)
    yd, dd = _detail(y, d)
    tri = rounded_poly([(-0.36 * k, -0.52 * k), (0.6 * k, 0.0), (-0.36 * k, 0.52 * k)],
                       0.11 * k)
    prism(f"{pre}_Play", tri, max(dd, 0.01), (x, yd, z), bg)


def icon_network(pre, fg, y, z, x=0.0, k=1.0, d=0.12):
    """5G: smart network - a hub linked to six connected devices"""
    R = 1.3 * k
    nodes = [(R * math.cos(math.radians(90 + 60 * i)), R * math.sin(math.radians(90 + 60 * i)))
             for i in range(6)]
    yt = y - 0.01 if d <= 0.05 else y
    for i, (nx, nz) in enumerate(nodes):
        tube(f"{pre}_Link_{i}", [(0, 0), (nx, nz)], 0.15 * k, (x, yt, z), fg)
        mx, mz = nodes[(i + 1) % 6]
        tube(f"{pre}_Ring_{i}", [(nx, nz), (mx, mz)], 0.09 * k, (x, yt, z), fg)
        prism(f"{pre}_Node_{i}", circle(0.3 * k, 32), d, (x + nx, y, z + nz), fg,
              bevel=0.03 if d > 0.05 else 0)
    prism(f"{pre}_Hub", circle(0.55 * k, 48), d, (x, y, z), fg,
          bevel=0.03 if d > 0.05 else 0)


def signal_bars(pre, y, z, x, mat_, n=4, w=0.5, h0=0.5, dh=0.4, gap=0.25, d=0.01):
    """Signal-strength icon: n rising bars, (x, z) = bottom-left corner"""
    for i in range(n):
        h = h0 + i * dh
        prism(f"{pre}_Bar_{i}", rrect(w, h, min(w, h) * 0.2, 2), d,
              (x + w / 2 + i * (w + gap), y, z + h / 2), mat_)


# ---------------------------------------------------------------------------
# Model construction
# ---------------------------------------------------------------------------
PITCH = 13.4          # distance between column centres
COL_W = 12.0          # column width
BASE_TOP = 19.0       # top of the black base
PED_TOP = 32.6        # top of the coloured pedestal (phone stands here)
PANEL_TOP = 49.5      # top of the back panel
SIGN_R = 5.0          # radius of the generation disc
SIGN_Z = 60.0 - SIGN_R   # disc centre = 55 cm, disc top = 60 cm
PED_Y0, PED_Y1 = -8.0, 1.5
PANEL_Y0, PANEL_Y1 = 1.5, 4.5


def build_base(M, root):
    Ctx.coll = get_coll("Base", root)
    Ctx.parent = empty("Base_Root")
    # front step
    box("Base_Lower", (0, -5.0, 5.5), (70.0, 22.0, 11.0), M["base"], bevel=0.35, seg=3)
    # rear step (columns stand on it)
    box("Base_Upper", (0, -1.5, 15.0), (68.0, 15.0, 8.0), M["base"], bevel=0.3, seg=3)
    # blue LED strip
    box("LED_Strip_Housing", (0, -16.05, 10.45), (69.0, 0.3, 0.8), M["ink"], bevel=0.05)
    box("LED_Strip", (0, -16.25, 10.45), (68.6, 0.15, 0.42), M["led"], bevel=0.05)
    box("LED_Strip_Top", (0, -1.5 - 7.6, 19.02), (66.0, 0.25, 0.06), M["led_diff"])

    # front title sign
    sy = -16.0
    prism("Sign_Border", rrect(54.0, 9.6, 1.4), 0.25, (0, sy - 0.12, 5.6), M["border"],
          bevel=0.06)
    prism("Sign_Panel", rrect(52.8, 8.4, 1.0), 0.12, (0, sy - 0.3, 5.6), M["sign_white"],
          bevel=0.03)
    prism("Sign_InnerLine_Outer", rrect(51.6, 7.3, 0.8), 0.02, (0, sy - 0.37, 5.6), M["ink"])
    prism("Sign_InnerLine_Inner", rrect(51.3, 7.0, 0.7), 0.02, (0, sy - 0.38, 5.6),
          M["sign_white"])
    text("Sign_Title", TEXT["title"], 3.0, (0, sy - 0.42, 6.85), M["ink"], maxw=38.0, depth=0.08,
         bold=0.03)
    text("Sign_Subtitle", TEXT["subtitle"], 1.6, (0, sy - 0.42, 3.5), M["ink"], maxw=36.0,
         depth=0.06, bold=0.02)
    for side in (-1, 1):
        for k, r in enumerate((0.9, 1.6, 2.3)):
            a0, a1 = (-48, 48) if side > 0 else (132, 228)
            tube(f"Sign_Wave_{'R' if side > 0 else 'L'}_{k}", arc_pts(r, a0, a1, 20), 0.32,
                 (side * 22.6, sy - 0.45, 5.6), M["ink"])

    # icons and arrows on the rear step
    fy = -9.0
    iz = 15.0
    builders = [
        lambda fg, bg, y: icon_handset("Icon_1G", fg, y, iz),
        lambda fg, bg, y: icon_envelope("Icon_2G", fg, bg, y, iz),
        lambda fg, bg, y: icon_globe("Icon_3G", fg, y, iz),
        lambda fg, bg, y: icon_play("Icon_4G", fg, bg, y, iz),
        lambda fg, bg, y: icon_network("Icon_5G", fg, y, iz),
    ]
    for i, g in enumerate(GENERATIONS):
        x = (i - 2) * PITCH
        holder = empty(f"Icon_{g['g']}", (x, 0, 0))
        Ctx.parent = holder
        prism(f"Icon_{g['g']}_Ring", circle(2.65, 72), 0.4, (0, fy - 0.2, iz), M["white"],
              bevel=0.08, seg=3)
        bg = mat(f"Icon_{g['g']}_BG", g["icon_bg"], rough=0.35)
        fg = mat(f"Icon_{g['g']}_FG", g["icon_fg"], rough=0.35)
        prism(f"Icon_{g['g']}_Disk", circle(2.2, 72), 0.12, (0, fy - 0.42, iz), bg,
              bevel=0.03)
        builders[i](fg, bg, fy - 0.55)
        Ctx.parent = bpy.data.objects["Base_Root"]
    arrow = [(-1.9, -0.32), (0.55, -0.32), (0.55, -0.9), (1.9, 0.0), (0.55, 0.9),
             (0.55, 0.32), (-1.9, 0.32)]
    for i in range(4):
        x = (i - 1.5) * PITCH
        prism(f"Arrow_{i + 1}", arrow, 0.3, (x, fy - 0.15, iz), M["white"], bevel=0.04)


def build_column(M, root, i, g):
    x = (i - 2) * PITCH
    Ctx.coll = get_coll(g["g"], root)
    Ctx.parent = None
    col_root = empty(f"{g['g']}_Root", (x, 0, 0))
    Ctx.parent = col_root
    paint = mat(f"{g['g']}_Paint", g["color"], rough=0.55)

    # coloured pedestal and back panel
    box(f"{g['g']}_Pedestal", (0, (PED_Y0 + PED_Y1) / 2, (BASE_TOP + PED_TOP) / 2),
        (COL_W, PED_Y1 - PED_Y0, PED_TOP - BASE_TOP), paint, bevel=0.18, seg=2)
    box(f"{g['g']}_Panel", (0, (PANEL_Y0 + PANEL_Y1) / 2, (BASE_TOP + PANEL_TOP) / 2),
        (COL_W - 0.6, PANEL_Y1 - PANEL_Y0, PANEL_TOP - BASE_TOP), paint, bevel=0.18, seg=2)

    # white label cards
    cy = PED_Y0
    prism(f"{g['g']}_YearCard_Border", rrect(10.6, 4.4, 0.35), 0.1, (0, cy - 0.05, 29.85),
          M["border"])
    prism(f"{g['g']}_YearCard", rrect(10.3, 4.1, 0.25), 0.1, (0, cy - 0.12, 29.85), M["white"],
          bevel=0.02)
    text(f"{g['g']}_YearCard_G", g["g"], 2.2, (0, cy - 0.2, 30.85), M["ink"], depth=0.05,
         bold=0.03)
    text(f"{g['g']}_YearCard_Years", g["years"], 1.45, (0, cy - 0.2, 28.75), M["ink"],
         maxw=9.2, depth=0.04, bold=0.02)

    prism(f"{g['g']}_DescCard_Border", rrect(10.6, 7.1, 0.35), 0.1, (0, cy - 0.05, 23.75),
          M["border"])
    prism(f"{g['g']}_DescCard", rrect(10.3, 6.8, 0.25), 0.1, (0, cy - 0.12, 23.75), M["white"],
          bevel=0.02)
    text(f"{g['g']}_Desc_1", TEXT[g["a"]], 1.55, (0, cy - 0.2, 25.95), M["ink"], maxw=9.5,
         depth=0.04, bold=0.025)
    text(f"{g['g']}_Desc_2", TEXT[g["b"]], 1.55, (0, cy - 0.2, 23.85), M["ink"], maxw=9.5,
         depth=0.04, bold=0.025)
    text(f"{g['g']}_Desc_EN", g["en"], 1.2, (0, cy - 0.2, 21.65), M["ink"], maxw=9.5,
         depth=0.04, bold=0.02)

    # signal symbol on the back panel ((  ))
    white = M["white"]
    wz = 46.3
    for side in (-1, 1):
        for k, r in enumerate((1.25, 2.1)):
            a0, a1 = (-42, 42) if side > 0 else (138, 222)
            tube(f"{g['g']}_Signal_{'R' if side > 0 else 'L'}_{k}", arc_pts(r, a0, a1, 18), 0.38,
                 (side * 0.9, PANEL_Y0 - 0.2, wz), white)

    # top disc sign
    py = (PANEL_Y0 + PANEL_Y1) / 2
    prism(f"{g['g']}_Sign_Post", circle(0.55, 32), SIGN_Z - SIGN_R - PANEL_TOP + 0.8,
          (0, py, (PANEL_TOP + SIGN_Z - SIGN_R) / 2), paint, plane="XY", bevel=0.05)
    ring = mat(f"{g['g']}_Sign_Ring", g["ring"], rough=0.45)
    prism(f"{g['g']}_Sign_Ring", circle(SIGN_R, 96), 1.0, (0, py, SIGN_Z), ring, bevel=0.15,
          seg=3)
    prism(f"{g['g']}_Sign_Face", circle(SIGN_R - 0.95, 96), 1.12, (0, py, SIGN_Z),
          M["sign_white"], bevel=0.05, seg=2)
    text(f"{g['g']}_Sign_Text", g["g"], 4.1, (0, py - 0.6, SIGN_Z), M["ink"], depth=0.1,
         bold=0.035)
    text(f"{g['g']}_Sign_Text_Back", g["g"], 4.1, (0, py + 0.6, SIGN_Z), M["ink"], depth=0.1,
         flip=True, bold=0.035)

    # phone - stands on the pedestal, leaning slightly against the back panel
    tilt = math.radians(6.0)
    ph = empty(f"{g['g']}_Phone", (0, 0, PED_TOP))
    Ctx.parent = ph
    if i == 0:
        H, T = phone_brick(M)
    elif i == 1:
        H, T = phone_candybar(M)
    else:
        (phone_3g, phone_4g, phone_5g)[i - 2](M)
        H, T = 11.8, 0.8
    ph.location = V(0, PANEL_Y0 - H * math.sin(tilt) - T / 2 * math.cos(tilt) - 0.08, PED_TOP)
    ph.rotation_euler = (-tilt, 0, 0)
    Ctx.parent = col_root


def build_environment(root):
    Ctx.coll = get_coll("Environment", root)
    Ctx.parent = None
    wood = bpy.data.materials.new("Table_Wood")
    wood.use_nodes = True
    nt = wood.node_tree
    bsdf = [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"][0]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    try:
        mp.inputs["Scale"].default_value = (1.0, 9.0, 1.0)
    except Exception:
        pass
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    try:
        wave.bands_direction = "Y"
    except Exception:
        pass
    set_input(wave, ["Scale"], 6.0)
    set_input(wave, ["Distortion"], 9.0)
    set_input(wave, ["Detail"], 6.0)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = srgb("#8d5a2f")
    ramp.color_ramp.elements[1].color = srgb("#c99566")
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    set_input(bsdf, ["Roughness"], 0.35)
    set_input(bsdf, ["Coat Weight", "Clearcoat"], 0.25)

    me = bpy.data.meshes.new("Table")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector((2.0, 1.6, 0.04)), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector((0, -0.2, -0.02)), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    t = bpy.data.objects.new("Table", me)
    _finish(t, wood, None)

    wall = mat("Wall", "#e3d9c8", rough=0.9)
    me = bpy.data.meshes.new("Wall")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(90), 3, "X"), verts=bm.verts)
    bmesh.ops.scale(bm, vec=Vector((2.0, 1.0, 1.2)), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector((0, 0.6, 0.6)), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    w = bpy.data.objects.new("Wall", me)
    _finish(w, wall, None)

    # lighting
    Ctx.coll = get_coll("Lights_Camera", root)

    def area(name, loc, power, size, target=(0, 0, 0.3), color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = power
        ld.size = size
        ld.color = color
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        d = Vector(target) - Vector(loc)
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        Ctx.coll.objects.link(ob)
        return ob

    area("Key_Light", (-0.75, -1.1, 1.15), 120, 0.9, color=(1.0, 0.96, 0.9))
    area("Fill_Light", (0.95, -0.9, 0.7), 45, 0.8, color=(0.92, 0.95, 1.0))
    area("Top_Light", (0.0, -0.15, 1.4), 40, 1.0)
    area("Rim_Light", (0.0, 0.45, 1.0), 30, 0.6, target=(0, 0, 0.45))

    def camera(name, loc, target, lens):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        ob = bpy.data.objects.new(name, cd)
        ob.location = loc
        d = Vector(target) - Vector(loc)
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        Ctx.coll.objects.link(ob)
        return ob

    cam = camera("Camera_Front", (0.0, -1.36, 0.62), (0.0, -0.02, 0.285), 50)
    camera("Camera_3-4", (0.88, -1.02, 0.6), (0.0, 0.0, 0.29), 50)
    bpy.context.scene.camera = cam


def setup_scene():
    sc = bpy.context.scene
    us = sc.unit_settings
    us.system = "METRIC"
    us.scale_length = 1.0
    try:
        us.length_unit = "CENTIMETERS"
    except Exception:
        pass
    sc.render.engine = "CYCLES"
    try:
        sc.cycles.samples = 256
        sc.cycles.use_denoising = True
    except Exception:
        pass
    sc.render.resolution_x = 1400
    sc.render.resolution_y = 1250
    for vt in ("AgX", "Filmic"):
        try:
            sc.view_settings.view_transform = vt
            break
        except Exception:
            pass
    for look in ("AgX - Punchy", "Punchy", "Filmic - Medium High Contrast"):
        try:
            sc.view_settings.look = look
            break
        except Exception:
            pass
    sc.view_settings.exposure = -0.6
    if sc.world is None:
        sc.world = bpy.data.worlds.new("World")
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.75, 0.74, 0.72, 1)
        bg.inputs[1].default_value = 0.18


def clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for blk in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.lights,
                bpy.data.cameras):
        for d in list(blk):
            if d.users == 0:
                blk.remove(d)


def build():
    global FONT
    if CLEAR_SCENE:
        clear()
    _MATS.clear()
    FONT = load_font()
    setup_scene()
    root = get_coll("Telecom_Generations_60cm")
    M = materials()
    build_base(M, root)
    for i, g in enumerate(GENERATIONS):
        build_column(M, root, i, g)
    if BUILD_ENVIRONMENT:
        build_environment(root)
    Ctx.parent = None
    bpy.context.view_layer.update()

    # verify total height
    zmax = 0.0
    for ob in get_coll("Telecom_Generations_60cm").all_objects:
        if ob.type in {"MESH", "CURVE", "FONT"} and ob.users_collection[0].name != "Environment":
            for c in ob.bound_box:
                zmax = max(zmax, (ob.matrix_world @ Vector(c)).z)
    print("[telecom] model height = %.2f cm" % (zmax * 100))


def _cli():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    save = render = None
    cam = None
    samples = None
    for k, v in zip(argv[::2], argv[1::2]):
        if k == "--save":
            save = os.path.abspath(v)
        elif k == "--render":
            render = os.path.abspath(v)
        elif k == "--camera":
            cam = v
        elif k == "--samples":
            samples = int(v)
    return save, render, cam, samples


if __name__ == "__main__":
    build()
    save, render, cam, samples = _cli()
    if save:
        for f in bpy.data.fonts:
            if f.filepath and f.filepath != "<builtin>" and f.packed_file is None:
                f.pack()
        bpy.ops.wm.save_as_mainfile(filepath=save, compress=True)
        print("[telecom] saved", save)
    if render:
        sc = bpy.context.scene
        if cam:
            sc.camera = bpy.data.objects[cam]
        if samples:
            sc.cycles.samples = samples
        sc.render.filepath = render
        bpy.ops.render.render(write_still=True)
        print("[telecom] rendered", render)
