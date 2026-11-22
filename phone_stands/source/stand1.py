"""Stand 1: black/yellow 'S' octagon stand.  Units: mm.
Plate is modelled in its PRINT orientation (back on the bed, face up, +Y = up the plate)."""
import math
import numpy as np
from manifold3d import CrossSection, FillRule
from lib import *

TILT = 68.0          # plate angle from horizontal
F = 6.0              # plate face level (plate thickness)
HW = 46.0            # plate half width
TOP = 140.0          # plate visible height above the deck
YB = -6.0            # insert tab bottom (goes into the base slot)
REST = F + 1.8       # highest relief the phone back touches
ZD = 13.0            # deck top height of the base
Y_FACE = -16.0       # where the plate face meets the deck


# ------------------------------------------------------------------ the S glyph
def s_glyph(scale=0.95):
    body = [(-23, -22), (17, -22), (18.5, -20.5), (18.5, -14.2), (-7.5, 14.2), (18.5, 14.2), (23, 18.7),
            (23, 22), (-17, 22), (-18.5, 20.5), (-18.5, 14.2), (7.5, -14.2), (-18.5, -14.2), (-23, -18.7)]
    stub = rect(2.0, 21.5, 8.3, 28.7, ch=0.8)
    side = [(16.5, -6.0), (22.0, -0.5), (22.0, 15.0), (16.5, 9.5)]
    pieces = [body, stub, rot180(stub), side, rot180(side)]
    return [ccw(scale2(p, scale)) for p in pieces]


def plate():
    blacks, accents, cut_black, cut_all = [], [], [], []
    back = ccw([(-HW, YB), (HW, YB), (HW, TOP - 6), (HW - 6, TOP), (-HW + 6, TOP), (-HW, TOP - 6)])
    front = ccw([(-HW + 1.2, YB), (HW - 1.2, YB), (HW - 1.2, TOP - 6.5), (HW - 6.5, TOP - 1.2),
                 (-HW + 6.5, TOP - 1.2), (-HW + 1.2, TOP - 6.5)])
    body = cprism(back, 0, 3.0, cb=0.4) + cprism(front, 2.9, F, ct=1.0)

    # panel seams (grooves) cut into the face only
    seams = [
        [(-26, 122), (-12, 113.5), (12, 113.5), (26, 122)],
        [(-27.0, 109.0), (-17.5, 107.0)], [(27.0, 109.0), (17.5, 107.0)],
        [(-16.0, 31.0), (-22.0, 27.5)], [(16.0, 31.0), (22.0, 27.5)],
        [(-43.8, 62.0), (-40.5, 62.0)], [(43.8, 62.0), (40.5, 62.0)],
    ]
    for s in seams:
        body = body - cprism(poly_line(s, 0.9), F - 0.5, F + 2)
    blacks.append(body)

    cx, cy = 0.0, 70.0
    # raised black octagon platform + recessed inner panel
    blacks.append(cprism(octagon(77, cx, cy), F - 0.3, F + 0.8, ct=0.6))
    cut_black.append(cut_prism(octagon(63, cx, cy), F + 0.4, F + 4, flare=0.3))
    # lower trapezoid frame above the ledge centre
    blacks.append(cprism([(-21, 12), (21, 12), (16, 25.5), (-16, 25.5)], F - 0.3, F + 0.8, ct=0.5))
    cut_black.append(cut_prism([(-16, 15), (16, 15), (12.5, 22.5), (-12.5, 22.5)], F, F + 4, flare=0.3))

    # ---- yellow
    accents.append(ring(octagon(72, cx, cy), octagon(66, cx, cy), F + 0.2, F + 1.8, ct=0.4))
    for p in s_glyph():
        accents.append(cprism(translate2(p, cx, cy), F - 0.2, F + 1.8, ct=0.4))

    shield = ccw([(-42.5, 127), (-28.5, 110.5), (-26.5, 114), (-26, 134.5), (-42.5, 134.5)])
    hexhole = [(-40, 129.5), (-38.2, 126.9), (-32.8, 126.9), (-31, 129.5), (-32.8, 132.1), (-38.2, 132.1)]
    upbar = [(-43.3, 99), (-39.8, 102.5), (-39.8, 119.5), (-43.3, 116)]
    upline = [(-37.9, 97), (-36.5, 97), (-36.5, 115), (-37.2, 117), (-37.9, 115)]
    lowline = rect(-43.5, 30, -42.3, 55.5)
    arrow = [(-39.5, 27.5), (-37.7, 33), (-38.8, 33), (-38.8, 51), (-40.2, 51), (-40.2, 33), (-41.3, 33)]
    for side in (1, -1):
        f = (lambda p: ccw(p)) if side == 1 else mirror_x
        accents.append(cprism(f(shield), F - 0.6, F + 1.0, ct=0.4))
        cut_all.append(cut_prism(f(hexhole), F - 1.0, F + 4, flare=0.3))
        accents.append(cprism(f(upbar), F - 0.6, F + 1.0, ct=0.3))
        accents.append(cprism(f(upline), F - 0.6, F + 1.0, ct=0.25))
        accents.append(cprism(f(lowline), F - 0.6, F + 1.0, ct=0.25))
        accents.append(cprism(f(arrow), F - 0.6, F + 1.0, ct=0.25))

    # ---- ledge (phone rest).  profile in (y, z); extruded along x
    arm = [(8, 5.5), (20, 5.5), (20, 21.5), (23.4, 25.4), (23.4, 26.2), (22.6, 27.0), (9.0, 27.0), (8, 26.0)]
    for x0, x1 in ((-44.8, -29.0), (29.0, 44.8)):
        blacks.append(axis_prism_x(arm, x0, x1, ce=0.8))
        accents.append(cprism(rect(x0 + 0.9, 14.5, x1 - 0.9, 22.0, ch=0.6), 26.4, 28.0, ct=0.4))
    bar = [(8, 5.5), (14, 5.5), (14, 15), (13, 16), (9, 16), (8, 15)]
    blacks.append(axis_prism_x(bar, -29.5, 29.5, ce=0.0))
    cut_black.append(cprism(rect(-8, 7, 8, 15.5, ch=1.0), F, 17))   # charging cable notch

    return finish(blacks, accents, cut_black, cut_all)


def finish(blacks, accents, cut_black, cut_all, post=()):
    black = union(blacks)
    acc = union(accents)
    for c in cut_all:
        black = black - c
        acc = acc - c
    for c in cut_black:
        black = black - c
    if post:
        black = black + union(list(post))
    black = black - acc
    return black.simplify(0.002), acc.simplify(0.002)


def plate_matrix(y_face=Y_FACE, zd=ZD, tilt=TILT, f=F):
    t = math.radians(tilt)
    O = (0.0, y_face + f * math.sin(t), zd - f * math.cos(t))
    return rot_x_matrix(tilt, O), O


def honeycomb(poly, z0, h, size=4.6, gap=1.0, margin=0.9):
    """Raised honeycomb tiles clipped to a polygon."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    r_in = size / 2.0
    pitch_x = size + gap
    pitch_y = pitch_x * math.sqrt(3) / 2
    tiles = []
    j = 0
    y = min(ys) - pitch_y
    while y < max(ys) + pitch_y:
        off = (pitch_x / 2) if j % 2 else 0.0
        x = min(xs) - pitch_x + off
        while x < max(xs) + pitch_x:
            tiles.append(np.asarray(regular_poly(6, r_in, x, y, rot=0.0), float))
            x += pitch_x
        y += pitch_y
        j += 1
    cs = CrossSection(tiles, FillRule.NonZero)
    clip = offset_poly(poly, -margin)
    cs = cs ^ CrossSection([np.asarray(clip, float)], FillRule.NonZero)
    return cs_prism(cs, z0, z0 + h)


def base():
    blacks, accents, cut_black, cut_all, post = [], [], [], [], []
    ZP = 8.0
    core = rect(-62.5, -59.5, 62.5, 59.5, ch=11)
    blacks.append(cprism(core, 0, ZP, ct=0.8, cb=0.4))
    segs_x = [(-50, -24), (-18, 18), (24, 50)]
    segs_y = [(-46, -18), (-12, 12), (18, 46)]
    for a, b in segs_x:
        blacks.append(cprism(rect(a, -62, b, -58), 0, ZP, ct=0.8, cb=0.4))
        blacks.append(cprism(rect(a, 58, b, 62), 0, ZP, ct=0.8, cb=0.4))
    for a, b in segs_y:
        blacks.append(cprism(rect(-65, a, -61, b), 0, ZP, ct=0.8, cb=0.4))
        blacks.append(cprism(rect(61, a, 65, b), 0, ZP, ct=0.8, cb=0.4))
    deck = rect(-60, -57, 60, 57, ch=13)
    blacks.append(cprism(deck, ZP - 0.2, ZD, ct=1.0))

    # yellow perimeter band
    accents.append(ring(inset(ccw(deck), 1.6), inset(ccw(deck), 4.2), ZD - 0.6, ZD + 1.0, ct=0.4))

    panels = [long_hex(-36, -38, 20, 14, 8), long_hex(36, -38, 20, 14, 8),
              ccw(rect(-12, -45.5, 12, -28.5, ch=2.5)),
              long_hex(-43, 30, 14, 15, 6), long_hex(43, 30, 14, 15, 6),
              ccw(rect(-14.5, 22, 14.5, 46, ch=3))]
    borders = [2.4, 2.4, 1.8, 2.4, 2.4, 1.8]
    from shapely.geometry import Polygon as _P
    inner_band = _P(inset(ccw(deck), 4.2)).buffer(-0.6, join_style='mitre')
    for p, bw in zip(panels, borders):
        pe = _P(p).intersection(inner_band)
        pe = ccw(list(pe.simplify(0.01).exterior.coords)[:-1])
        accents.append(ring(offset_poly(p, bw), pe, ZD - 0.6, ZD + 1.0, ct=0.4))
        cut_black.append(cprism(pe, ZD - 0.9, ZD + 3))
        post.append(honeycomb(pe, ZD - 1.0, 0.8, size=6.0, gap=1.3))
    # front centre yellow bar
    accents.append(cprism(rect(-13, -54.5, 13, -48.5, ch=1.0), ZD - 0.6, ZD + 1.0, ct=0.4))

    # rear support fins (part of the base)
    M, O = plate_matrix()
    t = math.radians(TILT)
    cl = 0.3 / math.sin(t)

    def back_Y(z):  # plate back plane Y at height z
        yloc = (z - O[2]) / math.sin(t)
        return O[1] + yloc * math.cos(t)

    zb = ZD - 0.5
    ztop = ZD + 88
    fin = ccw([(back_Y(zb) + cl, zb), (back_Y(ztop) + cl, ztop), (48.0, zb)])
    win = inset(fin, 7.5)
    for xc in (-22.0, 22.0):
        f = axis_prism_x(fin, xc - 3, xc + 3, ce=0.8)
        f = f - axis_prism_x(win, xc - 4, xc + 4) if win else f
        blacks.append(f)

    # slot for the plate tab
    slot = cprism(rect(-HW - 0.3, YB - 0.3, HW + 0.3, 6.0), -0.25, F + 0.25)
    cut_all.append(apply(slot, M))
    return finish(blacks, accents, cut_black, cut_all, post)


def build():
    pb, py = plate()
    bb, by = base()
    M, _ = plate_matrix()
    return {
        'name': 'S_Stand',
        'parts': {
            'Plate': {'black': pb, 'accent': py, 'assembly': M},
            'Base': {'black': bb, 'accent': by, 'assembly': None},
        },
        'accent_name': 'yellow',
    }


if __name__ == '__main__':
    import time
    t0 = time.time()
    d = build()
    for k, v in d['parts'].items():
        print(k, 'black vol %.1f cm3' % (v['black'].volume() / 1000), 'accent vol %.2f cm3' % (v['accent'].volume() / 1000),
              'bbox', [round(a, 1) for a in v['black'].bounding_box()], 'genus', v['black'].genus())
    print('time %.1fs' % (time.time() - t0))
