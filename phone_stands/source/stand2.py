"""Stand 2: black/white 'M' crown stand with front logo plaque.  Units: mm.
Plate and plaque are modelled in PRINT orientation (back on the bed, face up)."""
import math
import numpy as np
from shapely.geometry import Polygon
from lib import *
from manifold3d import Manifold
from stand1 import finish

TILT = 68.0
F = 6.0
HW = 47.0
YB = -10.0
TAB = 36.0           # half width of the insert tab
ZT = 40.0            # pedestal top
Y_FACE = -16.0
ZP, ZD = 6.0, 11.0   # plinth top, deck top
REST = F + 2.2       # highest relief the phone back touches
FONT = '/usr/share/fonts/opentype/inter/InterDisplay-Black.otf'
FONT_B = '/usr/share/fonts/opentype/inter/Inter-Bold.otf'


def m_glyph(h, sx=1.0):
    """Angular 'M' with pointed outer serifs; base at y=0, centred on x=0."""
    p = [(-0.52, 0.0), (-0.34, 0.0), (-0.32, 0.62), (0.0, 0.25), (0.32, 0.62), (0.34, 0.0), (0.52, 0.0),
         (0.50, 0.85), (0.62, 1.0), (0.36, 0.98), (0.0, 0.55), (-0.36, 0.98), (-0.62, 1.0), (-0.50, 0.85)]
    return ccw([(x * h * sx, y * h) for x, y in p])


def plate_outline():
    R = [(TAB, YB), (TAB, 0), (HW, 0), (HW, 84), (57, 114), (41, 105), (31, 106.5), (27, 117), (21, 110),
         (12, 106)]
    L = [(-x, y) for x, y in reversed(R)]
    return ccw([(0, YB)] + R + [(0, 104)] + L)


def plate():
    blacks, accents, cut_black, cut_all = [], [], [], []
    out = plate_outline()
    blacks.append(cprism(out, 0, 3.0, cb=0.4))
    blacks.append(cprism(offset_poly(out, -1.2), 2.9, F, ct=1.0))

    M = translate2(m_glyph(30), 0, 94)
    # crown spikes behind the M, M backing plate, the M itself
    for sgn in (1, -1):
        f = ccw if sgn == 1 else mirror_x
        blacks.append(cprism(f([(12, 104), (22, 100), (33, 121), (22, 117)]), 0, F + 0.3, ct=0.6, cb=0.4))
        blacks.append(cprism(f([(6, 112), (14, 110), (20, 132), (12, 127)]), 0, F + 0.3, ct=0.6, cb=0.4))
    blacks.append(cprism(offset_poly(M, 2.8), 0, F + 0.8, ct=0.6, cb=0.4))
    accents.append(cprism(M, F + 0.2, F + 2.2, ct=0.5))

    for sgn in (1, -1):
        f = ccw if sgn == 1 else mirror_x
        # light strips (white)
        accents.append(cprism(f(poly_line([(-31.5, 5), (-33.5, 88), (-49, 105.5)], 3.2)), F - 0.6, F + 1.2, ct=0.4))
        accents.append(cprism(f(poly_line([(-29.5, 98.5), (-21.5, 94)], 3.0)), F - 0.6, F + 1.2, ct=0.4))
        # raised armour panels
        blacks.append(cprism(f([(-44.5, 3), (-36.0, 3), (-37.6, 84), (-44.5, 82)]), F - 0.3, F + 1.0, ct=0.6))
        blacks.append(cprism(f([(-28.0, 3), (-8.0, 3), (-8.0, 70), (-13.0, 84), (-29.8, 88)]), F - 0.3, F + 1.0,
                             ct=0.6))
    # centre grille channel
    blacks.append(ring(rect(-6.2, 6, 6.2, 74, ch=1.5), rect(-4.4, 7.8, 4.4, 72.2, ch=0.8), F - 0.3, F + 0.8, ct=0.4))
    y = 11.0
    while y < 69:
        blacks.append(cprism(rect(-4.4, y, 4.4, y + 1.6), F - 0.3, F + 0.5, ct=0.3))
        y += 5.0
    blacks.append(cprism([(-7, 85), (0, 77), (7, 85), (7, 89), (0, 82.5), (-7, 89)], F - 0.3, F + 0.8, ct=0.4))

    # ledge (phone rest), profile (y, z) extruded along x
    arm = [(8, 5.5), (20, 5.5), (20, 21.9), (23.4, 25.8), (23.4, 26.6), (22.6, 27.4), (9.0, 27.4), (8, 26.4)]
    for x0, x1 in ((-45.8, -30.0), (30.0, 45.8)):
        blacks.append(axis_prism_x(arm, x0, x1, ce=0.8))
        accents.append(cprism(rect(x0 + 0.9, 14.5, x1 - 0.9, 22.0, ch=0.6), 26.8, 28.4, ct=0.4))
    bar = [(8, 5.5), (14, 5.5), (14, 15), (13, 16), (9, 16), (8, 15)]
    blacks.append(axis_prism_x(bar, -30.5, 30.5))
    cut_black.append(cprism(rect(-8, 7, 8, 15.5, ch=1.0), F, 17))
    # trim the plate below the pedestal top (outside the tab) so it sits flush on the pedestal
    Mp, _ = plate_matrix()
    M4 = np.eye(4)
    M4[:3] = Mp
    Minv = np.linalg.inv(M4)[:3]
    for sgn in (1, -1):
        xa, xb = (TAB + 0.3, 120) if sgn == 1 else (-120, -TAB - 0.3)
        box = cprism(rect(xa, -200, xb, 200), -100, ZT + 0.25)
        cut_all.append(apply(box, Minv))
    return finish(blacks, accents, cut_black, cut_all)


def plate_matrix():
    t = math.radians(TILT)
    O = (0.0, Y_FACE + F * math.sin(t), ZT - F * math.cos(t))
    return rot_x_matrix(TILT, O), O


# ------------------------------------------------------------------ plaque
PED_A = np.array([0, -46.0, 10.0])
PED_B = np.array([0, -20.0, ZT - 0.8])
BEV = 0.8


def plaque_frame():
    W = PED_B - PED_A
    W = W / np.linalg.norm(W)
    N = np.array([0, -W[2], W[1]])
    O = PED_A + N * BEV * max(abs(N[1]), abs(N[2]))
    return O, W, N


def plaque_outline():
    main = ccw([(-38, 37.8), (-35.5, 18.5), (-32, 15.5), (32, 15.5), (35.5, 18.5), (38, 37.8)])
    band = ccw([(-26, 6.5), (26, 6.5), (29, 9.75), (26, 13), (-26, 13), (-29, 9.75)])
    web = ccw(rect(-20, 11.5, 20, 16.5))
    return main, band, web


def fit_text(text, font, cap, max_w, tracking=0.0):
    cs, b = text_cs(text, font, cap, tracking)
    w = b[2] - b[0]
    sx = min(1.0, max_w / w)
    cs = cs.scale((sx, 1.0))
    b = cs.bounds()
    return cs, b


def plaque():
    blacks, accents, cut_black, cut_all = [], [], [], []
    main, band, web = plaque_outline()
    TB = 2.4
    blacks.append(cprism(main, 0, TB, ct=0.5, cb=0.3))
    blacks.append(cprism(band, 0, TB, ct=0.5, cb=0.3))
    blacks.append(cprism(web, 0, TB - 0.6))
    # raised border on the main shield
    blacks.append(ring(offset_poly(main, -0.7), offset_poly(main, -2.2), TB - 0.2, TB + 0.6, ct=0.3))
    # white outline on the band
    accents.append(ring(offset_poly(band, -0.6), offset_poly(band, -1.5), TB - 0.6, TB + 0.6, ct=0.2))

    # emblem M (narrow) on the left, spanning both text lines
    em_h = 17.0
    em = translate2(m_glyph(em_h, sx=0.72), -25.5, 18.5)
    accents.append(cprism(em, TB - 0.6, TB + 1.0, ct=0.3))
    x0 = -25.5 + 0.62 * 0.72 * em_h + 2.0
    cs1, b1 = fit_text('MOBILE', FONT, 7.4, 34.5 - x0)
    cs2, b2 = fit_text('LEGENDS', FONT, 7.4, 33.0 - x0)
    for cs, b, base_y in ((cs1, b1, 28.3), (cs2, b2, 18.7)):
        cs = cs.translate((x0 - b[0], base_y))
        accents.append(cs_prism(cs, TB - 0.6, TB + 1.0))
    cs3, b3 = fit_text('BANG BANG', FONT_B, 3.4, 40.0, tracking=1.3)
    cs3 = cs3.translate((-(b3[0] + b3[2]) / 2, 9.75 - 1.7))
    accents.append(cs_prism(cs3, TB - 0.6, TB + 0.9))
    return finish(blacks, accents, cut_black, cut_all)


def plaque_matrix():
    O, W, N = plaque_frame()
    O2 = O - N * 1.2
    return np.array([[1, 0, 0, O2[0]], [0, W[1], N[1], O2[1]], [0, W[2], N[2], O2[2]]], float)


# ------------------------------------------------------------------ base
def frustum(Q, z0, z1, s, shift):
    Q = np.asarray(ccw(Q), float)
    c = Q.mean(axis=0)
    T = c + s * (Q - c) + np.asarray(shift, float)
    B3 = [(x, y, z0) for x, y in Q]
    T3 = [(x, y, z1) for x, y in T]
    return hull_pts(B3 + T3), B3, T3


def shard(Q, z0, z1, s, shift, strip_face, width=3.0, t0=1.6, bev=0.6):
    m, B, T = frustum(Q, z0, z1, s, shift)
    i = strip_face
    j = (i + 1) % len(B)
    cen = np.mean(np.array(B + T), axis=0)
    return m, (T[i], B[i], T[j], B[j], width, cen, t0, 2.0)


def strip_and_pocket(spec, flat_list, pockets):
    R0, R1, F0, F1, w, cen, t0, shrink = spec
    st, n, d = face_strip(R0, R1, F0, F1, w, cen, out=0.7, inn=0.8, t0=t0, shrink=shrink, with_normal=True)
    pk = face_strip(R0, R1, F0, F1, w + 0.4, cen, out=1.6, inn=0.95, t0=t0 - 0.2, shrink=shrink - 0.2)
    flat_list.append((st, n, d))
    pockets.append(pk)
    return st


def base():
    blacks, accents, cut_black, cut_all = [], [], [], []
    flat, pockets = [], []
    plinth = ccw([(-92, -22), (-80, -48), (-40, -57), (40, -57), (80, -48), (92, -22), (92, 38), (78, 56),
                  (-78, 56), (-92, 38)])
    blacks.append(cprism(plinth, 0, ZP, ct=1.2, cb=0.4))
    deck = offset_poly(plinth, -4.0)
    blacks.append(cprism(deck, ZP - 0.2, ZD, ct=1.2))

    # pedestal carrying the plaque (front) and the plate slot (top)
    ped = [(-38, -46, 10), (38, -46, 10), (50, 6, 10), (-50, 6, 10),
           (-40, -20, ZT - BEV), (40, -20, ZT - BEV), (50, 6, ZT - BEV), (-50, 6, ZT - BEV)]
    blacks.append(bevel_hull(ped, BEV))

    # crystal shards (left)
    for Q, z1, s, sh, face in (
            ([(-90, -34), (-74, -44), (-66, -34), (-82, -20)], 52, 0.35, (-7, 1), 1),
            ([(-80, -50), (-63, -55), (-55, -45), (-70, -37)], 36, 0.40, (-5, -1), 1)):
        m, spec = shard(Q, 0.0, z1, s, sh, face)
        blacks.append(m)
        accents.append(strip_and_pocket(spec, flat, pockets))

    # V chevron in front of the plaque
    zb = 0.0
    v1 = [(-47, -56.5, zb), (-21, -56.5, zb), (-21, -47.5, zb), (-46, -46.5, zb),
          (-46, -54.5, 16), (-23, -55.0, 11.5), (-23, -50.0, 11.5), (-45, -49.0, 16)]
    v2 = [(-23, -56.5, zb), (3, -56.5, zb), (2, -46.5, zb), (-23, -47.5, zb),
          (-21, -55.0, 11.5), (1, -54.5, 16), (0, -49.0, 16), (-21, -50.0, 11.5)]
    for pts, (a, b, c, d) in ((v1, (4, 5, 7, 6)), (v2, (4, 5, 7, 6))):
        blacks.append(hull_pts(pts))
        cen = np.mean(np.array(pts), axis=0)
        accents.append(strip_and_pocket((pts[a], pts[b], pts[c], pts[d], 2.6, cen, 0.4, 0.8), flat, pockets))

    # rising blades (right front)
    r1 = [(36, -55, zb), (84, -46, zb), (86, -36, zb), (38, -46, zb),
          (40, -52, 16), (84, -43, 30), (84, -37, 30), (40, -46, 16)]
    r2 = [(44, -46, 0.0), (88, -36, 0.0), (88, -24, 0.0), (46, -34, 0.0),
          (48, -42, 26), (86, -31, 42), (86, -25, 42), (48, -36, 26)]
    for pts in (r1, r2):
        blacks.append(hull_pts(pts))
        cen = np.mean(np.array(pts), axis=0)
        accents.append(strip_and_pocket((pts[4], pts[5], pts[7], pts[6], 2.8, cen, 0.5, 1.5), flat, pockets))

    # stepped rear platforms (both sides) with grooves and light strips
    dpoly = Polygon(offset_poly(deck, -1.6))
    for sgn in (1, -1):
        def cl(r):
            g = Polygon(r if sgn == 1 else [(-x, y) for x, y in r]).intersection(dpoly)
            return ccw(list(g.exterior.coords)[:-1])
        s1 = cl(rect(56, -18, 90, 50))
        s2 = cl(rect(62, -10, 90, 50))
        g2 = Polygon(s2).intersection(Polygon(s1).buffer(-1.0, join_style='mitre'))
        s2 = ccw(list(g2.exterior.coords)[:-1])
        step1 = cprism(s1, ZD - 0.5, 17.0, ct=0.8)
        step2 = cprism(s2, 16.5, 23.0, ct=0.8)
        for gy in (2.0, 12.0, 22.0, 32.0):
            step2 = step2 - cprism(cl(rect(64, gy, 90, gy + 1.0)), 22.4, 25)
        blacks += [step1, step2]
        s1i = Polygon(s1).buffer(-1.3, join_style='mitre')
        s2i = Polygon(s2).buffer(-1.3, join_style='mitre')
        for strip, inner, z0 in ((rect(50, -16.5, 95, -14.0), s1i, 16.4), (rect(50, -8.5, 95, -6.0), s2i, 22.4)):
            g = Polygon(strip if sgn == 1 else [(-x, y) for x, y in strip]).intersection(inner)
            sp = ccw(list(g.exterior.coords)[:-1])
            accents.append(cprism(sp, z0, z0 + 1.6, ct=0.4))
            flat.append((cprism(sp, z0, z0 + 1.6, ct=0.4), (0, 0, 1), (1, 0, 0)))
            pockets.append(cprism(offset_poly(sp, 0.2), z0 - 0.1, z0 + 3))

    # rear support fins
    M, O = plate_matrix()
    t = math.radians(TILT)
    clr = 0.3 / math.sin(t)

    def back_Y(z):
        return O[1] + (z - O[2]) / math.sin(t) * math.cos(t)

    fin = ccw([(back_Y(ZT - 1) + clr, ZT - 1), (back_Y(ZT + 64) + clr, ZT + 64), (46.0, ZD - 0.5),
               (6.0, ZD - 0.5), (6.0, ZT - 1)])
    win = offset_poly(fin, -7.0)
    for xc in (-38.0, 38.0):
        f = axis_prism_x(fin, xc - 3, xc + 3, ce=0.8)
        f = f - axis_prism_x(win, xc - 4, xc + 4)
        blacks.append(f)

    # plate slot
    slot = cprism(rect(-TAB - 0.3, YB - 0.3, TAB + 0.3, 6.0), -0.25, F + 0.25)
    cut_all.append(apply(slot, M))
    # plaque pocket
    main, band, web = plaque_outline()
    P = plaque_matrix()
    for p in (main, band, web):
        o = ccw(offset_poly(p, 0.25))
        pocket = loft([(o, 0.0), (inset(o, -0.9), 1.2), (inset(o, -2.4), 3.2)])
        cut_all.append(apply(pocket, P))
    black_ams, white_ams = finish(blacks, accents, cut_black, cut_all)
    # single-colour variant: black base with grooves + white strips printed flat (glue-in)
    black_solo, _ = finish(blacks, [], cut_black, cut_all + pockets)
    strips_flat = lay_flat(flat)
    return black_ams, white_ams, black_solo, strips_flat


def build():
    pb, pw = plate()
    bb, bw, bsolo, strips = base()
    qb, qw = plaque()
    M, _ = plate_matrix()
    return {
        'name': 'ML_Stand',
        'parts': {
            'Plate': {'black': pb, 'accent': pw, 'assembly': M},
            'Base': {'black': bb, 'accent': bw, 'assembly': None},
            'Plaque': {'black': qb, 'accent': qw, 'assembly': plaque_matrix()},
            # alternative (recommended for AMS): black-only base + flat white glue-in strips
            'Base_BlackOnly': {'black': bsolo, 'accent': Manifold(), 'assembly': None, 'show': False},
            'Base_WhiteStrips': {'black': Manifold(), 'accent': strips, 'assembly': None, 'show': False},
        },
        'accent_name': 'white',
    }


if __name__ == '__main__':
    d = build()
    for k, v in d['parts'].items():
        print(k, 'black %.1f cm3' % (v['black'].volume() / 1000), 'white %.2f cm3' % (v['accent'].volume() / 1000),
              'bbox', [round(a, 1) for a in v['black'].bounding_box()])
