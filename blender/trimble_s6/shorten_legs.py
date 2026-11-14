"""
Shorten the tripod legs of the converted Trimble S6 model, nothing else.
=======================================================================
Each leg is compressed along its own axis (fitted to the leg's vertices),
so the splay angle (~25 deg), the bar cross-sections and every part above
the hinge (tripod head, tribrach, instrument) stay exactly as they were.
The whole model is then lowered so the feet stand on z = 0 again.

Default target: tripod head at 0.95 m (legs ~37% shorter).  Full photo
proportions (--head 0.515) made the legs too stubby next to their unchanged
thickness, so the default keeps a leg length/width ratio close to the photo.

Usage
  python shorten_legs.py IN.blend OUT_DIR [--head 0.95] [--render]
  blender -b -P shorten_legs.py -- IN.blend OUT_DIR [--head 0.95] [--render]
"""

import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skp_to_blender as conv            # noqa: E402  (stage / export / render helpers)

Z_CUT = 1.28        # everything above stays untouched (hinges start at ~1.30 m)
HEAD_TOP = 1.42     # top of the tripod head plate in the converted model
DEFAULT_HEAD = 0.95  # m, top of the tripod head after shortening


def leg_vertices(co, axis_xy, z_cut):
    """Group vertices below z_cut into three legs by azimuth around the axis."""
    low = np.where(co[:, 2] < z_cut)[0]
    az = np.arctan2(co[low, 1] - axis_xy[1], co[low, 0] - axis_xy[0])
    # three leg azimuths = directions of the three lowest, well separated points
    order = low[np.argsort(co[low, 2])]
    feet = []
    for i in order:
        p = co[i, :2]
        if all(np.linalg.norm(p - f) > 0.1 for f in feet):
            feet.append(p)
        if len(feet) == 3:
            break
    fa = [math.atan2(f[1] - axis_xy[1], f[0] - axis_xy[0]) for f in feet]
    d = np.stack([np.abs(np.angle(np.exp(1j * (az - a)))) for a in fa])
    which = d.argmin(0)
    if (d.min(0) > 0.7).any():
        raise RuntimeError("found vertices below the hinges that belong to no leg")
    return [low[which == k] for k in range(3)]


def main(argv):
    src, out_dir = argv[0], argv[1]
    head = float(argv[argv.index("--head") + 1]) if "--head" in argv else None
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(src))
    ob = bpy.data.objects["Group#1"]
    me = ob.data
    Mw = np.array(ob.matrix_world)
    co = np.array([v.co for v in me.vertices]) @ Mw[:3, :3].T + Mw[:3, 3]

    top = co[:, 2].max()
    if head is None:
        head = DEFAULT_HEAD
    # instrument axis = centre of the three feet
    legs_guess = co[co[:, 2] < 0.002]
    axis_xy = legs_guess[:, :2].mean(0)
    legs = leg_vertices(co, axis_xy, Z_CUT)

    drop = HEAD_TOP - head                      # how much the head must come down
    k = (Z_CUT - drop) / Z_CUT                  # axial scale of the legs
    print(f"[legs] head {HEAD_TOP:.3f} -> {head:.3f} m, axial scale {k:.3f}", flush=True)

    new = co.copy()
    for idx in legs:
        P = co[idx]
        c = P.mean(0)
        u = np.linalg.svd(P - c)[2][0]
        if u[2] > 0:
            u = -u                              # pointing down the leg
        H = c + u * ((Z_CUT - c[2]) / u[2])     # axis point at the cut height
        s = (P - H) @ u
        perp = P - H - np.outer(s, u)
        new[idx] = H + np.outer(k * s, u) + perp
        print(f"[legs] leg: {len(idx)} verts, splay {math.degrees(math.acos(-u[2])):.1f} deg, "
              f"length {s.max():.3f} -> {k * s.max():.3f} m", flush=True)
    new[:, 2] -= new[:, 2].min()

    inv = np.linalg.inv(Mw)
    loc = new @ inv[:3, :3].T + inv[:3, 3]
    me.vertices.foreach_set("co", loc.ravel())
    me.update()

    # rebuild the stage (floor, lights, cameras) for the new height
    for o in list(bpy.data.objects):
        if o is not ob:
            bpy.data.objects.remove(o, do_unlink=True)
    size = Vector(new.max(0) - new.min(0))
    print(f"[legs] new size: {size.x:.3f} x {size.y:.3f} x {size.z:.3f} m "
          f"(was {top:.3f} m tall)", flush=True)
    _, cams = conv.stage(size.z)
    # close-up on the instrument + tripod head (its height changed)
    tgt = Vector((0, 0, head + 0.45 * (size.z - head)))
    cam = cams["Cam_Head"]
    cam.location = tgt + Vector((0.42, -0.62, 0.22))
    cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()
    os.makedirs(out_dir, exist_ok=True)
    base = "Trimble_S6_Tripod_short"
    if "--render" in argv:
        conv.render(os.path.join(out_dir, "renders_short"), cams,
                    int(os.environ.get("SKP_SAMPLES", "64")))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(os.path.join(out_dir, base + ".blend")))
    conv.export_all([ob], out_dir, base, size.z)
    print("[legs] wrote", out_dir, flush=True)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(args)
