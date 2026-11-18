"""
Pipe Clip (mushroom shape) - Blender script
===========================================
Clip that holds two 17.5 mm pipes (one on each side). Snap-fit.

How to use in Blender:
  1. Open Blender -> "Scripting" tab -> New
  2. Paste this file (or Open it) -> Run Script (Alt+P)
  3. The object "PipeClip" is created. Units are millimetres (1 BU = 1 mm).
  4. File -> Export -> STL  (Scale 1.0)

Change the numbers in PARAMS and run again; the old object is replaced.
All sizes are in millimetres.
"""
import math

PARAMS = {
    "pipe_d":    17.5,  # pipe diameter (1.75 cm)
    "clearance": 0.0,   # added to hole diameter. 0 = tight. -0.2 tighter, +0.2 looser
    "base_w":    10.0,  # flat bottom width (1 cm)
    "neck_w":    7.0,   # narrowest stem width between the two pipes
    "wall":      3.0,   # wall thickness of the outer lip around each pipe
    "hook_deg":  32.0,  # how far the outer lip (hook) wraps UNDER the pipe, in degrees below the pipe centre.
                        # bigger = stronger hook but harder to snap in (opening gets smaller)
    "depth":     50.0,  # length of the part (side view 5 cm)
    "segments":  96,    # arc resolution (per full circle)
}


def build_profile(p=PARAMS):
    """Return the closed 2D outline [(x, z), ...] counter-clockwise, in mm."""
    r = (p["pipe_d"] + p["clearance"]) / 2.0
    t = p["wall"]
    seg = p["segments"]
    base_half = p["base_w"] / 2.0
    neck_half = p["neck_w"] / 2.0

    cx = neck_half + r                  # pipe centre x (right side)
    dx = cx - base_half
    if not (0 < dx < r):
        raise ValueError("neck_w / base_w combination is impossible")
    cz = math.sqrt(r * r - dx * dx)     # pipe centre height: hole passes through base corner
    Rw = r + t                          # outer lip radius
    R = cx + Rw                         # dome radius, centre (0, cz)

    a_in = math.atan2(-cz, -dx)                         # foot point angle (around pipe centre)
    a_tip = -math.radians(p["hook_deg"])                # hook tip angle
    phi = a_tip - a_in                                  # exposed arc (the snap opening)
    if not (0 < phi < math.pi):
        raise ValueError("hook_deg out of range")
    opening = 2 * r * math.sin(phi / 2)

    def arc(ccx, ccz, rad, a0, a1):
        n = max(2, int(abs(a1 - a0) / (2 * math.pi) * seg) + 1)
        return [(ccx + rad * math.cos(a0 + (a1 - a0) * i / n),
                 ccz + rad * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]

    right = []
    # 1) hole arc: from the foot point, over the top of the pipe, down to the lip tip
    right += arc(cx, cz, r, a_in, a_tip - 2 * math.pi)
    # 2) rounded tip (half circle) - acts as a lead-in for snapping the pipe
    ux, uz = math.cos(a_tip), math.sin(a_tip)           # radial
    wx, wz = math.sin(a_tip), -math.cos(a_tip)          # toward the opening
    mx, mz = cx + (r + t / 2) * ux, cz + (r + t / 2) * uz
    n = seg // 4
    for i in range(1, n):
        s = math.pi * i / n
        right.append((mx + t / 2 * (-math.cos(s) * ux + math.sin(s) * wx),
                      mz + t / 2 * (-math.cos(s) * uz + math.sin(s) * wz)))
    # 3) outer lip arc up to the side of the dome
    right += arc(cx, cz, Rw, a_tip, 0.0)

    dome = arc(0.0, cz, R, 0.0, math.pi)[1:-1]
    left = [(-x, z) for x, z in reversed(right)]
    pts = right + dome + left

    # remove consecutive duplicates
    out = []
    for q in pts:
        if not out or math.dist(q, out[-1]) > 1e-6:
            out.append(q)
    if math.dist(out[0], out[-1]) < 1e-6:
        out.pop()
    info = dict(pipe_center=(cx, cz), dome_radius=R, width=2 * R, height=cz + R,
                wrap_deg=360 - math.degrees(phi), opening=opening)
    return out, info


def build_in_blender(p=PARAMS, name="PipeClip"):
    import bpy
    import bmesh

    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 0.001
    scene.unit_settings.length_unit = 'MILLIMETERS'

    old = bpy.data.objects.get(name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)

    pts, info = build_profile(p)
    d = p["depth"]

    bm = bmesh.new()
    front = [bm.verts.new((x, -d / 2, z)) for x, z in pts]
    face = bm.faces.new(front)
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    new_verts = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=new_verts, vec=(0, d, 0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    # triangulate the two ngon caps so the STL is clean
    caps = [f for f in bm.faces if len(f.verts) > 4]
    bmesh.ops.triangulate(bm, faces=caps)

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    for f in me.polygons:
        f.use_smooth = False
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Auto Smooth look for the round surfaces (Blender 4.1+)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(30))
    except Exception:
        pass

    print("PipeClip:", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in info.items()})
    return obj


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
        build_in_blender()
    except ImportError:
        pts, info = build_profile()
        print(len(pts), "points", info)
