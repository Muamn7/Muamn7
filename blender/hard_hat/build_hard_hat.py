"""
build_hard_hat.py  --  خوذة أمان صفراء عالية الدقة (Blender 4.x / 5.x)

التشغيل داخل بلندر:  Scripting  ->  Open  ->  build_hard_hat.py  ->  Run Script
أو من الطرفية:        blender --python build_hard_hat.py

كل القياسات بالمليمتر في القاموس P بالأسفل، والمشهد يُبنى بالمتر (مقياس حقيقي).
الخوذة مصمَّمة لمحيط رأس 58 سم: فتحة الخوذة الداخلية = محيط الرأس + خلوص 12 مم
من كل جهة (المسافة القياسية بين الرأس وجدار خوذة الأمان).

الشكل كله معرَّف بدوال رياضية تُعيَّن على شبكة رباعية كثيفة (بدون قطب في القمة):
  - القبة: سطح بيضوي فائق  ((f/A)^2 + (s/B)^2)^(n/2) + (z/H)^n = 1
  - العُرف الأوسط + الحزام الجانبي + الضلع العلوي + كسرات اللوحة الأمامية: إزاحة على
    طول العمود على السطح
  - الحافة السفلية والواقية الأمامية (الرفرف): مقطع يُكنس حول محيط القاعدة
  - الشريط الجانبي: صناديق مدوّرة الحواف مثنية على محيط القاعدة
"""
import math

import numpy as np

# --------------------------------------------------------------------------- #
#  القياسات (مم)
# --------------------------------------------------------------------------- #
P = dict(
    head_circumference=580.0,   # محيط الرأس المطلوب
    head_ratio=0.80,            # عرض الرأس / طوله
    clearance=12.0,             # الخلوص بين الرأس والجدار الداخلي
    t_shell=3.0,                # سماكة الجدار

    # القبة (السطح الخارجي الأساسي). A و B تُحسبان من محيط الرأس في derive()
    A=None, B=None,
    H=119.5,                    # ارتفاع القبة فوق مستوى الحافة
    n=2.2,                      # أسّ المقطع الرأسي (2 = بيضوي، أكبر = جوانب أكثر استقامة)
    shear=0.0,                  # إزاحة القمة للأمام (+) أو للخلف (-)
    z_dip=-9.85, dip_t0=20.0, dip_t1=85.0,   # انخفاض حافة القاعدة عند الأمام

    # العُرف الأوسط (الشريط العريض من الخلف للأمام)
    w_top=18.0,                 # نصف عرضه فوق القمة (عند الحافة العلوية للدرجة)
    w_front=41.0,               # نصف عرضه عند القاعدة من الأمام
    w_back=37.0,                # نصف عرضه عند القاعدة من الخلف
    flare_p=0.8,
    hc_hi=5.5, hc_lo=2.6,       # ارتفاع الدرجة: فوق / عند القاعدة
    ramp_c=9.0,                 # عرض الدرجة المقعّرة (للخارج)

    # الحزام الأوسط (درجة ثانية أخفض، تتلاشى نزولًا)
    s_band=54.0, h_band=3.2, ramp_b=3.2,   # حافته الخارجية عند |s| = s_band
    band_z0=0.58, band_z1=0.78,

    # الضلع العلوي الصغير على خط المنتصف
    rib_f0=-46.0, rib_f1=25.0, rib_r=8.5, h_rib=2.6, ramp_r=5.0,

    # كسرات اللوحة الأمامية (خطّان عرضيان على العُرف)
    c1=0.89, c2=0.745, c3=0.10, sag1=1.0, sag2=4.2,
    h_crease=0.45, w_crease=1.3,   # خرزة رفيعة على خط الكسرة العلوي

    # الحافة السفلية + الرفرف الأمامي
    w_lip=9.5, w_lip_back=7.6,    # عرض الحافة الصغيرة (+ زيادة في الخلف)
    lip_t0=77.0, lip_t1=133.5,    # مجال τ الذي تتّسع فيه الحافة الخلفية
    W_brim=46.2,                  # بروز الرفرف الأمامي
    brim_tau=77.9, brim_gamma=1.0,
    a_lip=9.0, a_lip_back=36.0, a_brim=24.6,   # زاوية الميل للأسفل (درجة): جانب / خلف / رفرف
    brim_curve=0.35,
    t_brim=2.8, h_bead=0.7,       # سماكة الرفرف + الشفة المرفوعة على حافته
    c_fillet=1.2, c_fillet_brim=3.2, c_inner=1.5,

    # دقة الشبكة
    N=176, M=112,
)

# الشريط الجانبي: (بداية τ°، نهاية τ°، z0، z1، البروز، نصف قطر التدوير، يُعكس؟)
# τ هو وسيط القطع الناقص للقاعدة: 0 = الأمام، 90 = الجانب، 180 = الخلف
# الارتفاعات z منسوبة إلى حافة القاعدة عند نفس الزاوية؛ (a, b) = القيمة عند البداية والنهاية
#   (τ0, τ1, z0a, z0b, z1a, z1b, البروز, نصف قطر التدوير, يُعكس؟)
RAILS = [
    (30.5, 76.5, -6.0, -3.2, 16.5, 15.0, 7.0, 1.5, True),     # القطعة الأمامية الطويلة
    (77.5, 108.0, -3.2, -3.2, 7.4, 7.4, 8.5, 1.0, True),      # القطعة الخلفية (نصف سفلي)
    (77.5, 108.0, 7.5, 7.5, 18.5, 18.5, 8.5, 1.0, True),      # القطعة الخلفية (نصف علوي) -> أخدود بينهما
    (109.0, 251.0, -3.2, -3.2, 19.6, 19.6, 8.5, 1.5, False),  # قطعة الظهر
]
RAIL_BURY = 2.0


def ellipse_perimeter(a, b, m=4000):
    t = np.linspace(0.0, 2.0 * np.pi, m + 1)
    x, y = a * np.cos(t), b * np.sin(t)
    return float(np.sum(np.hypot(np.diff(x), np.diff(y))))


def derive(p):
    """يحسب أبعاد الرأس والقبة من محيط الرأس."""
    p = dict(p)
    unit = ellipse_perimeter(1.0, p['head_ratio'])
    p['head_a'] = p['head_circumference'] / unit          # نصف طول الرأس
    p['head_b'] = p['head_a'] * p['head_ratio']           # نصف عرض الرأس
    if p['A'] is None:
        p['A'] = p['head_a'] + p['clearance'] + p['t_shell']
    if p['B'] is None:
        p['B'] = p['head_b'] + p['clearance'] + p['t_shell']
    return p


# --------------------------------------------------------------------------- #
#  دوال مساعدة
# --------------------------------------------------------------------------- #
def smoother(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * x * (x * (6.0 * x - 15.0) + 10.0)


def sstep(a, b, x):
    return smoother((x - a) / (b - a))


def step_in(x, w):
    """1 حيث x سالب (داخل)، 0 حيث x موجب (خارج)، بانحدار عرضه w حول الصفر."""
    return smoother(0.5 - x / w)


def cove(e, w, eps=0.07):
    """درجة بمقطع مقعّر: 1 داخل الحافة (e<0) ثم تهبط إلى 0 عند e=w بحافة علوية حادّة."""
    x = e / w
    soft = np.where(x <= -eps, 0.0, np.where(x >= eps, x, (x + eps) ** 2 / (4.0 * eps)))
    return (1.0 - np.clip(soft, 0.0, 1.0)) ** 2


def normalize(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


# --------------------------------------------------------------------------- #
#  السطح الأساسي + الإزاحة.  الإحداثيات (f, s, z) = (أمام، جانب، أعلى) بالمم
# --------------------------------------------------------------------------- #
def profile_g(zn, p):
    """نصف قطر المقطع الأفقي النسبي عند الارتفاع zn (1 عند القاعدة، 0 عند القمة)."""
    return np.sqrt(np.maximum(1.0 - np.clip(zn, 0.0, 1.0) ** p['n'], 0.0))


def base_point(d, p):
    """يعيّن اتجاهًا (f,s,u) من نصف الكرة العلوي إلى نقطة على السطح الأساسي."""
    hx = np.hypot(d[..., 0], d[..., 1])
    ok = hx > 1e-12
    cs = np.where(ok, d[..., 0] / np.maximum(hx, 1e-12), 1.0)
    sn = np.where(ok, d[..., 1] / np.maximum(hx, 1e-12), 0.0)
    re = 1.0 / np.sqrt((cs / p['A']) ** 2 + (sn / p['B']) ** 2)
    up = np.maximum(d[..., 2], 0.0) * re
    zn = up / np.sqrt((p['H'] * hx) ** 2 + up ** 2)
    tau = np.abs(np.arctan2(re * sn / p['B'], re * cs / p['A']))
    z = p['H'] * zn + rim_z(tau, p) * (1.0 - zn) ** 3      # الحلقة السفلية تتبع حافة القاعدة
    zc = np.clip(z / p['H'], 0.0, 1.0)
    g = profile_g(zc, p)                                   # تحت z=0 جدار رأسي
    return np.stack([g * re * cs + p['shear'] * zc * zc, g * re * sn, z], axis=-1)


def rim_z(tau_abs, p):
    """ارتفاع حافة القاعدة: صفر في الجوانب والخلف، وينخفض عند الأمام."""
    t = np.clip((tau_abs - math.radians(p['dip_t0'])) / math.radians(p['dip_t1'] - p['dip_t0']), 0.0, 1.0)
    return p['z_dip'] * (0.5 + 0.5 * np.cos(np.pi * t))


def base_normal(pt, p):
    zn = np.clip(pt[..., 2] / p['H'], 0.0, 1.0)
    f, s = pt[..., 0] - p['shear'] * zn * zn, pt[..., 1]
    gf, gs = 2.0 * f / p['A'] ** 2, 2.0 * s / p['B'] ** 2
    gz = (p['n'] * zn ** (p['n'] - 1.0) - gf * 2.0 * p['shear'] * zn) / p['H']
    return normalize(np.stack([gf, gs, gz], axis=-1))


def displacement(pt, p):
    f, s, z = pt[..., 0], pt[..., 1], pt[..., 2]
    zn = np.clip(z / p['H'], 0.0, 1.0)
    a = np.abs(s)

    # العُرف الأوسط
    flare = (1.0 - zn) ** p['flare_p']
    wb = p['w_back'] + (p['w_front'] - p['w_back']) * sstep(-25.0, 25.0, f)
    s_edge = p['w_top'] + (wb - p['w_top']) * flare
    e = a - s_edge
    hc = p['hc_lo'] + (p['hc_hi'] - p['hc_lo']) * sstep(0.12, 0.60, zn)
    crest = cove(e, p['ramp_c'])
    d = hc * crest

    # الحزام الأوسط
    fade = sstep(p['band_z0'], p['band_z1'], zn)
    d = d + p['h_band'] * fade * cove(a - p['s_band'], p['ramp_b'])

    # الضلع العلوي
    fc = np.clip(f, p['rib_f0'], p['rib_f1'])
    sd = np.hypot(f - fc, s) - p['rib_r']
    d = d + p['h_rib'] * step_in(sd, p['ramp_r'])

    # كسرات اللوحة الأمامية
    inside = crest * sstep(15.0, 45.0, f)
    t1 = (zn - p['c2']) / (p['c1'] - p['c2'])
    t2 = (zn - p['c3']) / (p['c2'] - p['c3'])
    sag = np.where((t1 > 0) & (t1 < 1), p['sag1'] * 4.0 * t1 * (1.0 - t1), 0.0)
    sag = sag + np.where((t2 > 0) & (t2 < 1), p['sag2'] * 6.75 * t2 * t2 * (1.0 - t2), 0.0)
    bead = p['h_crease'] * np.exp(-0.5 * ((zn - p['c1']) * p['H'] / p['w_crease']) ** 2)
    return d - inside * (sag - bead)


def shell_points(d, p, inner=False):
    p0 = base_point(d, p)
    off = displacement(p0, p)
    if inner:
        off = off - p['t_shell']
    return p0 + base_normal(p0, p) * off[..., None]


# --------------------------------------------------------------------------- #
#  شبكة "مكعب-كرة" لنصف الكرة العلوي: وجه علوي N×N + حلقات جانبية (بدون قطب)
# --------------------------------------------------------------------------- #
def cap_dirs(N, M):
    al = np.tan(np.pi / 4.0 * np.linspace(-1.0, 1.0, N + 1))
    a, b = np.meshgrid(al, al, indexing='ij')
    top = normalize(np.stack([a, b, np.ones_like(a)], axis=-1))      # (N+1, N+1, 3)
    li = np.concatenate([np.full(N, N), N - np.arange(N), np.zeros(N, int), np.arange(N)])
    lj = np.concatenate([np.arange(N), np.full(N, N), N - np.arange(N), np.zeros(N, int)])
    la, lb = al[li], al[lj]
    rings = []
    for m in range(1, M + 1):
        zc = math.tan(math.pi / 4.0 * (1.0 - m / M))
        rings.append(normalize(np.stack([la, lb, np.full_like(la, zc)], axis=-1)))
    return top, li * (N + 1) + lj, np.array(rings)                    # rings: (M, 4N, 3)


# --------------------------------------------------------------------------- #
#  مقطع الحافة السفلية / الرفرف، يُكنس حول محيط القاعدة
# --------------------------------------------------------------------------- #
STRIP_ROWS = dict(fillet=6, top=46, edge=12, under=38, corner=5, wall=4)


def rim_strip(rim_dirs, p):
    """rim_dirs: اتجاهات الحلقة السفلية (4N,3) عند z=0. يرجع (K-1, 4N, 3) صفوف وسيطة."""
    w0 = base_point(rim_dirs, p)                                     # على القطع الناقص للقاعدة
    nh = normalize(np.stack([w0[:, 0] / p['A'] ** 2, w0[:, 1] / p['B'] ** 2,
                             np.zeros(len(w0))], axis=-1))
    D = displacement(w0, p)
    tau = np.abs(np.arctan2(w0[:, 1] / p['B'], w0[:, 0] / p['A']))
    bump = np.cos(0.5 * np.pi * np.clip(tau / math.radians(p['brim_tau']), 0, 1)) ** (2 * p['brim_gamma'])
    back = sstep(math.radians(p['lip_t0']), math.radians(p['lip_t1']), tau)
    w_lip = p['w_lip'] + p['w_lip_back'] * back
    W = w_lip + (p['W_brim'] - w_lip) * bump
    al = np.radians(p['a_lip'] + (p['a_brim'] - p['a_lip']) * bump)
    droop = back * (math.tan(math.radians(p['a_lip_back'])) - math.tan(math.radians(p['a_lip'])))
    ta, ca, sa = np.tan(al), np.cos(al), np.sin(al)

    c0 = p['c_fillet'] + (p['c_fillet_brim'] - p['c_fillet']) * bump
    c1, tb, hb, ts = p['c_inner'], p['t_brim'], p['h_bead'], p['t_shell']
    re = 0.5 * (tb + hb)
    qE, zE = D + c0 * ca, -c0 - c0 * sa
    Wt = W - re

    def top0(q):                       # سطح الرفرف العلوي بدون الشفة
        x = q - qE
        lin = zE - ta * x
        cur = zE - ta * (x - p['brim_curve'] * x * x / (2.0 * (W - qE)))
        y = np.clip(q - (p['w_lip'] - 1.0), 0.0, None)          # الحافة الخلفية: رفّ مستوٍ ثم تنحني للأسفل
        return np.where(x < 0, lin, cur) - droop * np.where(y < 3.0, y * y / 6.0, y - 1.5)

    def bead(q):
        return hb * sstep(Wt - 4.5, Wt - 1.5, q)

    rows = []
    R = STRIP_ROWS
    # 1) تقويس التقاء الجدار بالحافة
    for i in range(1, R['fillet'] + 1):
        t = i / R['fillet']
        q = (1 - t) ** 2 * D + 2 * t * (1 - t) * D + t * t * qE
        z = 2 * t * (1 - t) * (-c0) + t * t * zE
        rows.append((q, z))
    # 2) السطح العلوي
    for i in range(1, R['top'] + 1):
        q = qE + (Wt - qE) * (i / R['top'])
        rows.append((q, top0(q) + bead(q)))
    # 3) الحافة المدوّرة
    zc = top0(Wt) + hb - re
    for i in range(1, R['edge'] + 1):
        ph = 0.5 * np.pi - np.pi * i / R['edge']
        rows.append((Wt + re * np.cos(ph), zc + re * np.sin(ph)))
    # 4) السطح السفلي
    q_in = D - ts
    qU = q_in + c1
    for i in range(1, R['under'] + 1):
        q = Wt + (qU - Wt) * (i / R['under'])
        rows.append((q, top0(q) - tb))
    # 5) الزاوية الداخلية
    zU, zK = top0(qU) - tb, top0(q_in) - tb
    for i in range(1, R['corner'] + 1):
        t = i / R['corner']
        q = (1 - t) ** 2 * qU + 2 * t * (1 - t) * q_in + t * t * q_in
        z = (1 - t) ** 2 * zU + 2 * t * (1 - t) * zK + t * t * (zK + c1)
        rows.append((q, z))
    # 6) الجدار الداخلي صعودًا إلى z=0 (الصف الأخير هو حلقة السطح الداخلي نفسها)
    for i in range(1, R['wall']):
        t = i / R['wall']
        rows.append((np.broadcast_to(q_in, D.shape), (zK + c1) * (1 - t)))

    out = []
    for q, z in rows:
        pt = w0 + nh * np.asarray(q)[:, None]
        pt[:, 2] = w0[:, 2] + z
        out.append(pt)
    return np.array(out)


# --------------------------------------------------------------------------- #
#  جسم الخوذة: مجسّم مغلق (سطح خارجي + حافة + سطح داخلي)
# --------------------------------------------------------------------------- #
def build_shell(p):
    N, M = p['N'], p['M']
    top_d, loop_idx, ring_d = cap_dirs(N, M)
    n_top, L = (N + 1) ** 2, 4 * N

    o_top = shell_points(top_d.reshape(-1, 3), p)
    o_rings = shell_points(ring_d, p)                         # (M, L, 3)
    strip = rim_strip(ring_d[-1], p)                          # (K-1, L, 3)
    i_rings = shell_points(ring_d, p, inner=True)[::-1]       # من الحافة صعودًا
    i_top = shell_points(top_d.reshape(-1, 3), p, inner=True)

    verts = np.concatenate([o_top, o_rings.reshape(-1, 3), strip.reshape(-1, 3),
                            i_rings.reshape(-1, 3), i_top])

    # فهارس الحلقات بالتتابع: حافة الوجه العلوي الخارجي ... حافة الوجه العلوي الداخلي
    ring_ids = [loop_idx]
    base = n_top
    for _ in range(M + len(strip) + M - 1):
        ring_ids.append(base + np.arange(L))
        base += L
    # آخر حلقة داخلية (m=1) ثم حافة الوجه العلوي الداخلي
    ring_ids.append(base + np.arange(L))
    base += L
    ring_ids.append(base + loop_idx)
    # ملاحظة: i_rings فيه M حلقة: m=M..1 ؛ أضفنا M-1 ثم واحدة = M
    ring_ids = np.array(ring_ids)

    k = np.arange(L)
    k1 = (k + 1) % L
    quads = []
    for r in range(len(ring_ids) - 1):
        a, b = ring_ids[r], ring_ids[r + 1]
        quads.append(np.stack([a[k], b[k], b[k1], a[k1]], axis=-1))

    ii, jj = np.meshgrid(np.arange(N), np.arange(N), indexing='ij')
    g = (ii * (N + 1) + jj).reshape(-1)
    grid = np.stack([g, g + (N + 1), g + (N + 1) + 1, g + 1], axis=-1)
    quads.append(grid)                                        # الوجه العلوي الخارجي
    quads.append(base + grid[:, ::-1])                        # الوجه العلوي الداخلي (معكوس)
    return verts, np.concatenate(quads)


# --------------------------------------------------------------------------- #
#  الشريط الجانبي: صندوق مدوّر الحواف مثني على محيط القاعدة
# --------------------------------------------------------------------------- #
def rounded_box(size, r, seg=1.2, nr=4):
    """شبكة صندوق مدوّر الحواف متمركز عند الأصل. يرجع (verts, quads)."""
    axes = []
    for h in (0.5 * size[0], 0.5 * size[1], 0.5 * size[2]):
        flat = max(1, int(round(2.0 * (h - r) / seg)))
        c = np.concatenate([-h + r * np.linspace(0, 1, nr + 1)[:-1],
                            np.linspace(-(h - r), h - r, flat + 1),
                            (h - r) + r * np.linspace(0, 1, nr + 1)[1:]])
        axes.append(c)
    nx, ny, nz = (len(a) - 1 for a in axes)
    index, verts, quads = {}, [], []

    def vid(i, j, k):
        key = (i, j, k)
        if key not in index:
            index[key] = len(verts)
            verts.append((axes[0][i], axes[1][j], axes[2][k]))
        return index[key]

    for k in (0, nz):
        for i in range(nx):
            for j in range(ny):
                q = [vid(i, j, k), vid(i + 1, j, k), vid(i + 1, j + 1, k), vid(i, j + 1, k)]
                quads.append(q if k else q[::-1])
    for j in (0, ny):
        for i in range(nx):
            for k in range(nz):
                q = [vid(i, j, k), vid(i, j, k + 1), vid(i + 1, j, k + 1), vid(i + 1, j, k)]
                quads.append(q if j else q[::-1])
    for i in (0, nx):
        for j in range(ny):
            for k in range(nz):
                q = [vid(i, j, k), vid(i, j + 1, k), vid(i, j + 1, k + 1), vid(i, j, k + 1)]
                quads.append(q if i else q[::-1])

    v = np.array(verts)
    half = 0.5 * np.array(size)
    core = np.clip(v, -(half - r), half - r)
    dv = v - core
    ln = np.linalg.norm(dv, axis=1, keepdims=True)
    v = core + np.where(ln > 1e-9, dv / np.maximum(ln, 1e-9) * r, 0.0)
    return v, np.array(quads)


def build_rails(p):
    A, B, H, n = p['A'], p['B'], p['H'], p['n']
    tt = np.linspace(0.0, 2.0 * np.pi, 40001)
    arc = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(A * np.cos(tt)), np.diff(B * np.sin(tt))))])

    all_v, all_q, base = [], [], 0
    for t0, t1, z0a, z0b, z1a, z1b, prot, r, mirror in RAILS:
        s0, s1 = np.interp(np.radians([t0, t1]), tt, arc)
        hgt = max(z1a - z0a, z1b - z0b)
        size = (s1 - s0, prot + RAIL_BURY, hgt)
        v, q = rounded_box(size, r)
        tau = np.interp(0.5 * (s0 + s1) + v[:, 0], arc, tt)
        dep = v[:, 1] + 0.5 * (prot - RAIL_BURY)
        along = v[:, 0] / size[0] + 0.5
        top = z1a + (z1b - z1a) * along
        bot = z0a + (z0b - z0a) * along
        z = bot + (v[:, 2] / hgt + 0.5) * (top - bot) + rim_z(np.abs(tau), p)
        zn = np.clip(z, 0, H) / H
        g = profile_g(zn, p)
        nh = normalize(np.stack([np.cos(tau) / A, np.sin(tau) / B], axis=-1))
        pts = np.stack([g * A * np.cos(tau) + p['shear'] * zn * zn + nh[:, 0] * dep,
                        g * B * np.sin(tau) + nh[:, 1] * dep, z], axis=-1)
        all_v.append(pts)
        all_q.append(q[:, ::-1] + base)
        base += len(pts)
        if mirror:
            all_v.append(pts * np.array([1.0, -1.0, 1.0]))
            all_q.append(q + base)
            base += len(pts)
    return np.concatenate(all_v), np.concatenate(all_q)


def build_head(p, n_u=96, n_v=40):
    """مجسّم مرجعي لرأس محيطه 58 سم (للتأكد من المقاس فقط، لا يظهر في الرندر)."""
    a, b = p['head_a'], p['head_b']
    z_band, c_top, neck = -6.0, 96.0, 60.0
    th = np.linspace(0, 2 * np.pi, n_u, endpoint=False)
    rows = []
    for i in range(n_v + 1):                       # من الأسفل إلى القمة
        t = i / n_v
        if t < 0.4:
            z = z_band - neck * (1 - t / 0.4)
            k = 1.0 - 0.10 * (1 - t / 0.4) ** 2
        else:
            ph = (t - 0.4) / 0.6 * (np.pi / 2) * 0.985
            z = z_band + c_top * np.sin(ph)
            k = np.cos(ph)
        rows.append(np.stack([k * a * np.cos(th), k * b * np.sin(th), np.full(n_u, z)], -1))
    v = np.array(rows).reshape(-1, 3)
    quads = []
    for i in range(n_v):
        for j in range(n_u):
            j1 = (j + 1) % n_u
            quads.append([i * n_u + j, i * n_u + j1, (i + 1) * n_u + j1, (i + 1) * n_u + j])
    return v, np.array(quads), z_band


def to_blender(v):
    """(f, s, z) مم  ->  (x, y, z) متر : الأمام = -Y ، الأعلى = +Z"""
    return np.stack([v[:, 1], -v[:, 0], v[:, 2]], axis=-1) * 0.001


# --------------------------------------------------------------------------- #
#  بلندر: الكائنات، المادة، الإضاءة، الكاميرا
# --------------------------------------------------------------------------- #
# الكاميرا المطابقة للصورة المرجعية (استُخرجت بمطابقة ظلّ الخوذة مع الصورة)
CAMERA = dict(az=-129.49, el=14.27, dist=1.67, scale=1.21, cx=166.47, cy=116.63, ref_size=360.0,
              target=(0.0, 0.0, 0.07))


def make_object(bpy, name, verts, quads, collection, smooth=True):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set('co', np.asarray(verts, dtype=np.float32).ravel())
    me.loops.add(quads.size)
    me.loops.foreach_set('vertex_index', np.asarray(quads, dtype=np.int32).ravel())
    me.polygons.add(len(quads))
    me.polygons.foreach_set('loop_start', np.arange(0, quads.size, 4, dtype=np.int32))
    me.polygons.foreach_set('loop_total', np.full(len(quads), 4, dtype=np.int32))
    me.update(calc_edges=True)
    me.validate()
    if smooth:
        me.polygons.foreach_set('use_smooth', np.ones(len(quads), dtype=bool))
    ob = bpy.data.objects.new(name, me)
    collection.objects.link(ob)
    return ob


def make_plastic(bpy):
    mat = bpy.data.materials.new('HardHat_Yellow_Plastic')
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')

    def setv(names, value):
        for nm in names:
            if nm in bsdf.inputs:
                bsdf.inputs[nm].default_value = value
                return

    setv(['Base Color'], (1.0, 0.58, 0.0, 1.0))
    setv(['Roughness'], 0.16)
    setv(['IOR'], 1.50)
    setv(['Specular IOR Level', 'Specular'], 0.5)
    setv(['Coat Weight', 'Clearcoat'], 0.6)
    setv(['Coat Roughness', 'Clearcoat Roughness'], 0.04)
    return mat


def look_at(bpy, ob, target):
    from mathutils import Vector
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def add_area(bpy, coll, name, loc, target, size, power, color=(1, 1, 1), spec=1.0, diff=1.0):
    li = bpy.data.lights.new(name, 'AREA')
    li.shape = 'RECTANGLE'
    li.size, li.size_y = size
    li.energy = power
    li.color = color
    li.specular_factor = spec
    li.diffuse_factor = diff
    ob = bpy.data.objects.new(name, li)
    ob.location = loc
    coll.objects.link(ob)
    look_at(bpy, ob, target)
    return ob


def setup_camera(bpy, coll, cam=CAMERA):
    az, el = math.radians(cam['az']), math.radians(cam['el'])
    t = cam['target']
    c = (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
    data = bpy.data.cameras.new('Camera_Reference')
    ob = bpy.data.objects.new('Camera_Reference', data)
    ob.location = tuple(t[i] + cam['dist'] * c[i] for i in range(3))
    coll.objects.link(ob)
    look_at(bpy, ob, t)
    s = cam['ref_size']
    data.sensor_fit = 'HORIZONTAL'
    data.sensor_width = 36.0
    data.lens = cam['scale'] * cam['dist'] * 1000.0 * 36.0 / s
    data.shift_x = (0.5 * s - cam['cx']) / s
    data.shift_y = (cam['cy'] - 0.5 * s) / s
    data.clip_start, data.clip_end = 0.05, 20.0
    return ob


def build_scene(bpy, p=None, with_head=True):
    p = derive(p or P)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for b in list(block):
            if b.users == 0:
                block.remove(b)
    scene = bpy.context.scene
    for c in list(scene.collection.children):
        scene.collection.children.unlink(c)

    def coll(name):
        c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
        if c.name not in scene.collection.children:
            scene.collection.children.link(c)
        return c

    c_hat, c_ref, c_studio = coll('HardHat'), coll('Reference'), coll('Studio')

    sv, sq = build_shell(p)
    rv, rq = build_rails(p)
    verts = np.concatenate([sv, rv])
    quads = np.concatenate([sq, rq + len(sv)])
    hat = make_object(bpy, 'HardHat', to_blender(verts), quads, c_hat)
    hat.data.materials.append(make_plastic(bpy))

    if with_head:
        hv, hq, _ = build_head(p)
        head = make_object(bpy, 'Head_58cm_reference', to_blender(hv), hq, c_ref)
        head.hide_render = True
        head.display_type = 'WIRE'
        c_ref.hide_render = True
        c_ref.hide_viewport = True          # أظهر مجموعة Reference من الـ Outliner لرؤية الرأس المرجعي

    # الاستوديو
    tgt = (0.0, 0.0, 0.07)
    # صناديق إضاءة كبيرة موضوعة بحيث تنعكس في نفس أماكن اللمعات في الصورة المرجعية
    add_area(bpy, c_studio, 'Softbox_Left', (-0.62, 0.48, 0.70), (-0.07, -0.02, 0.08), (0.80, 0.55), 8.5, spec=3.6, diff=1.0)
    add_area(bpy, c_studio, 'Softbox_Front', (0.56, -0.66, 0.60), (0.0, -0.10, 0.07), (0.85, 0.95), 7.5, spec=4.0, diff=0.9)
    add_area(bpy, c_studio, 'Softbox_Top', (0.02, 0.42, 0.98), (-0.04, -0.02, 0.10), (0.45, 0.95), 5.5, spec=3.6, diff=1.0)
    add_area(bpy, c_studio, 'Softbox_Right', (0.66, 0.20, 0.78), (0.0, -0.08, 0.05), (0.70, 0.55), 5.0, spec=3.6, diff=0.8)
    cam = setup_camera(bpy, c_studio)
    scene.camera = cam

    world = scene.world or bpy.data.worlds.new('World')
    scene.world = world
    world.use_nodes = True
    bg = next((n for n in world.node_tree.nodes if n.type == 'BACKGROUND'), None)
    if bg:
        bg.inputs[0].default_value = (0.05, 0.045, 0.04, 1.0)
        bg.inputs[1].default_value = 1.0

    us = scene.unit_settings
    us.system, us.length_unit, us.scale_length = 'METRIC', 'MILLIMETERS', 1.0

    r = scene.render
    r.engine = 'CYCLES'
    r.resolution_x = r.resolution_y = 1600
    r.film_transparent = True
    r.image_settings.file_format = 'PNG'
    r.image_settings.color_mode = 'RGBA'
    cy = scene.cycles
    cy.samples = 256
    cy.use_denoising = True
    cy.max_bounces = 6
    try:
        scene.view_settings.view_transform = 'Standard'
        scene.view_settings.look = 'None'
    except Exception:
        pass
    return hat, p


def report(p):
    inner_a = p['A'] - p['t_shell']
    inner_b = p['B'] - p['t_shell']
    print('محيط الرأس المرجعي      : %.1f مم' % ellipse_perimeter(p['head_a'], p['head_b']))
    print('الرأس (طول × عرض)       : %.1f × %.1f مم' % (2 * p['head_a'], 2 * p['head_b']))
    print('فتحة الخوذة (طول × عرض)  : %.1f × %.1f مم  (محيط %.1f مم)' % (
        2 * inner_a, 2 * inner_b, ellipse_perimeter(inner_a, inner_b)))


if __name__ == '__main__':
    import sys
    import bpy

    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    hat, p = build_scene(bpy)
    report(p)
    if '--save' in args:
        bpy.ops.wm.save_as_mainfile(filepath=args[args.index('--save') + 1], compress=True)
    if '--render' in args:
        bpy.context.scene.render.filepath = args[args.index('--render') + 1]
        bpy.ops.render.render(write_still=True)
