"""Small signed-distance-field toolkit used to build the IgG antibody model.

Every part is described as an SDF (negative inside), sampled on a voxel grid
and turned into a closed triangle mesh with marching cubes.  Building parts
this way guarantees watertight, manifold meshes that slice cleanly, and lets
mating holes be carved from the exact shape of the part that plugs into them.
"""
import numpy as np
from skimage.measure import marching_cubes

F32 = np.float32


# --------------------------------------------------------------------------
# grids
# --------------------------------------------------------------------------
class Grid:
    """Axis-aligned voxel grid in a part's *local* frame."""

    def __init__(self, lo, hi, h):
        self.lo = np.asarray(lo, float)
        self.h = float(h)
        self.shape = tuple(int(np.ceil((hi[i] - lo[i]) / h)) + 1 for i in range(3))
        self.axes = [(self.lo[i] + self.h * np.arange(self.shape[i])).astype(F32) for i in range(3)]

    def points(self, sl=None):
        if sl is None:
            sl = (slice(None),) * 3
        ax = [self.axes[i][sl[i]] for i in range(3)]
        return np.meshgrid(*ax, indexing="ij", sparse=True)

    def box(self, c, rad):
        sl = []
        for i in range(3):
            a = int(np.floor((c[i] - rad - self.lo[i]) / self.h))
            b = int(np.ceil((c[i] + rad - self.lo[i]) / self.h)) + 1
            a, b = max(a, 0), min(b, self.shape[i])
            if a >= b:
                return None
            sl.append(slice(a, b))
        return tuple(sl)


class Frame:
    """Rigid frame: world = origin + local @ R.T  (R columns are the local axes)."""

    def __init__(self, origin=(0, 0, 0), U=(1, 0, 0), V=(0, 1, 0), W=(0, 0, 1)):
        self.o = np.asarray(origin, float)
        self.R = np.stack([np.asarray(U, float), np.asarray(V, float), np.asarray(W, float)], axis=1)

    def to_world(self, p):
        return self.o + np.asarray(p, float) @ self.R.T

    def to_local(self, p):
        return (np.asarray(p, float) - self.o) @ self.R

    def dir_to_local(self, d):
        return np.asarray(d, float) @ self.R

    def dir_to_world(self, d):
        return np.asarray(d, float) @ self.R.T


def transform_points(P, frame_from, frame_to):
    """Map broadcastable point tuple P given in frame_from into frame_to coords."""
    M = frame_to.R.T @ frame_from.R
    t = frame_to.R.T @ (frame_from.o - frame_to.o)
    X, Y, Z = P
    return tuple(M[i, 0] * X + M[i, 1] * Y + M[i, 2] * Z + t[i] for i in range(3))


# --------------------------------------------------------------------------
# primitives  (P is a tuple of broadcastable arrays)
# --------------------------------------------------------------------------
def _sub(P, c):
    return P[0] - F32(c[0]), P[1] - F32(c[1]), P[2] - F32(c[2])


def length(x, y, z):
    return np.sqrt(x * x + y * y + z * z)


def sphere(P, c, r):
    x, y, z = _sub(P, c)
    return length(x, y, z) - F32(r)


def ellipsoid(P, c, rad):
    """Fast, reasonably accurate ellipsoid SDF (Inigo Quilez' bound)."""
    x, y, z = _sub(P, c)
    rx, ry, rz = (F32(r) for r in rad)
    k0 = length(x / rx, y / ry, z / rz)
    k1 = length(x / (rx * rx), y / (ry * ry), z / (rz * rz))
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)


def capsule(P, a, b, r):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    ba = b - a
    x, y, z = _sub(P, a)
    hh = np.clip((x * ba[0] + y * ba[1] + z * ba[2]) / float(ba @ ba), 0.0, 1.0)
    return length(x - hh * ba[0], y - hh * ba[1], z - hh * ba[2]) - F32(r)


def _axis_basis(axis):
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    t = np.array([0, 0, 1.0]) if abs(a[2]) < 0.9 else np.array([1.0, 0, 0])
    e1 = np.cross(a, t)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    return a, e1, e2


def _axial(P, a0, axis, e1=None, e2=None):
    x, y, z = _sub(P, a0)
    a = axis
    t = x * a[0] + y * a[1] + z * a[2]
    if e1 is None:
        rx, ry, rz = x - t * a[0], y - t * a[1], z - t * a[2]
        return t, length(rx, ry, rz)
    u = x * e1[0] + y * e1[1] + z * e1[2]
    v = x * e2[0] + y * e2[1] + z * e2[2]
    return t, u, v


def _cap(d_rad, d_ax, rr=0.0):
    """Combine radial / axial distances into a capped-prism SDF with edge radius rr."""
    dx = d_rad + rr
    dy = d_ax + rr
    return (np.minimum(np.maximum(dx, dy), 0.0)
            + np.sqrt(np.maximum(dx, 0.0) ** 2 + np.maximum(dy, 0.0) ** 2) - rr)


def cylinder(P, a, b, r, rr=0.0):
    """Capped cylinder between points a and b (edge rounding rr)."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    L = np.linalg.norm(b - a)
    ax = (b - a) / L
    t, rad = _axial(P, a, ax)
    return _cap(rad - F32(r), np.abs(t - F32(L / 2)) - F32(L / 2), rr)


def hex_prism(P, a, b, rc, rr=0.0, spin=0.0):
    """Hexagonal prism (circumradius rc) between a and b - a keyed peg."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    L = np.linalg.norm(b - a)
    ax, e1, e2 = _axis_basis(b - a)
    cs, sn = np.cos(spin), np.sin(spin)
    e1, e2 = cs * e1 + sn * e2, -sn * e1 + cs * e2
    t, u, v = _axial(P, a, ax, e1, e2)
    ri = rc * np.sqrt(3) / 2  # apothem
    d = None
    for k in range(6):
        ang = k * np.pi / 3
        di = u * F32(np.cos(ang)) + v * F32(np.sin(ang)) - F32(ri)
        d = di if d is None else np.maximum(d, di)
    return _cap(d, np.abs(t - F32(L / 2)) - F32(L / 2), rr)


def torus(P, c, axis, R, r):
    ax = np.asarray(axis, float)
    ax = ax / np.linalg.norm(ax)
    t, rad = _axial(P, c, ax)
    return np.sqrt((rad - F32(R)) ** 2 + t * t) - F32(r)


def halfspace(P, point, normal):
    """Negative on the side the normal points *away* from (n points outside)."""
    n = np.asarray(normal, float)
    n = n / np.linalg.norm(n)
    x, y, z = _sub(P, point)
    return x * n[0] + y * n[1] + z * n[2]


# --------------------------------------------------------------------------
# boolean helpers
# --------------------------------------------------------------------------
def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    m = np.minimum(a, b)
    return m - F32(k) * np.log1p(np.exp(-np.abs(a - b) / F32(k)))


def smin_all(fields, k):
    out = fields[0]
    for f in fields[1:]:
        out = smin(out, f, k)
    return out


def carve(field, tool, clearance=0.0):
    """field minus (tool grown by clearance)."""
    return np.maximum(field, -(tool - F32(clearance)))


def sweep(field, axis, sign):
    """Minkowski sweep of a solid along +/- one grid axis.

    Returns S(p) = min_{t>=0} field(p + t*sign*e_axis).  Carving a part with
    the sweep of its neighbour (in the direction the part is pulled off)
    removes every undercut, so the parts always slide together.
    """
    if sign > 0:
        f = np.flip(field, axis)
        return np.flip(np.minimum.accumulate(f, axis=axis), axis)
    return np.minimum.accumulate(field, axis=axis)


# --------------------------------------------------------------------------
# lumpy "protein surface" domains
# --------------------------------------------------------------------------
def poisson_on_surface(verts, normals, spacing, rng):
    order = rng.permutation(len(verts))
    cell = spacing / np.sqrt(3)
    buckets = {}
    keep = []
    s2 = spacing * spacing
    for i in order:
        p = verts[i]
        key = tuple((p // cell).astype(int))
        ok = True
        rng_c = 2
        for dx in range(-rng_c, rng_c + 1):
            for dy in range(-rng_c, rng_c + 1):
                for dz in range(-rng_c, rng_c + 1):
                    j = buckets.get((key[0] + dx, key[1] + dy, key[2] + dz))
                    if j is not None and np.sum((verts[j] - p) ** 2) < s2:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            buckets[key] = i
            keep.append(i)
    keep = np.array(keep)
    return verts[keep], normals[keep]


def envelope_surface(env_fn, lo, hi, h=0.5):
    g = Grid(lo, hi, h)
    f = env_fn(g.points()).astype(F32)
    v, faces, _, _ = marching_cubes(f, 0.0, spacing=(h, h, h))
    v = v + g.lo
    e = 1e-3
    P = (v[:, 0], v[:, 1], v[:, 2])
    gx = env_fn((P[0] + e, P[1], P[2])) - env_fn((P[0] - e, P[1], P[2]))
    gy = env_fn((P[0], P[1] + e, P[2])) - env_fn((P[0], P[1] - e, P[2]))
    gz = env_fn((P[0], P[1], P[2] + e)) - env_fn((P[0], P[1], P[2] - e))
    n = np.stack([gx, gy, gz], 1)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    return v, n


class LumpyDomain:
    """A globular protein domain: a smooth core covered with clustered spheres."""

    def __init__(self, env_fn, bounds, seed, layers=None, shrink=2.1, k=0.42):
        self.env_fn = env_fn
        self.bounds = bounds
        self.rng = np.random.default_rng(seed)
        self.shrink = shrink
        self.k = k
        if layers is None:
            layers = [
                # spacing, r_min, r_max, protrusion_min, protrusion_max
                (6.8, 4.0, 5.2, 1.3, 2.1),
                (3.9, 2.4, 3.1, 0.9, 1.5),
            ]
        lo, hi = bounds
        verts, norms = envelope_surface(env_fn, np.array(lo) - 1, np.array(hi) + 1)
        self.spheres = []
        for spacing, rmin, rmax, pmin, pmax in layers:
            pv, pn = poisson_on_surface(verts, norms, spacing, self.rng)
            r = self.rng.uniform(rmin, rmax, len(pv))
            prot = self.rng.uniform(pmin, pmax, len(pv))
            c = pv - pn * (r - prot)[:, None]
            self.spheres += list(zip(c, r))

    def field(self, grid):
        k = F32(self.k)
        core = self.env_fn(grid.points()).astype(F32) + F32(self.shrink)
        core = np.clip(core, -12.0, 40.0)
        acc = np.exp(-core / k)
        for c, r in self.spheres:
            sl = grid.box(c, r + 9 * self.k)
            if sl is None:
                continue
            d = sphere(grid.points(sl), c, r)
            acc[sl] += np.exp(-np.clip(d, -12.0, 40.0) / k)
        return (-k * np.log(acc + F32(1e-30))).astype(F32)


# --------------------------------------------------------------------------
# meshing
# --------------------------------------------------------------------------
def mesh_field(field, grid, frame):
    f = field.copy()
    # close the surface at the grid boundary
    f[0, :, :] = f[-1, :, :] = np.abs(f[0, :, :]).clip(min=0.5)
    f[:, 0, :] = f[:, -1, :] = np.abs(f[:, 0, :]).clip(min=0.5)
    f[:, :, 0] = f[:, :, -1] = np.abs(f[:, :, 0]).clip(min=0.5)
    v, faces, _, _ = marching_cubes(f, 0.0, spacing=(grid.h,) * 3, allow_degenerate=False)
    v = v + grid.lo
    v = frame.to_world(v)
    faces = faces.astype(np.int64)
    a, b, c = v[faces[:, 0]], v[faces[:, 1]], v[faces[:, 2]]
    vol = np.sum(np.einsum("ij,ij->i", a, np.cross(b, c))) / 6.0
    if vol < 0:
        faces = faces[:, ::-1]
    return v.astype(np.float32), faces.astype(np.int32)


def march(field_fn, p0, d, t_max, step=0.05):
    """First t where field_fn(p0 + t d) < 0 (point-wise SDF on arrays)."""
    d = np.asarray(d, float)
    d = d / np.linalg.norm(d)
    ts = np.arange(0, t_max, step)
    pts = np.asarray(p0, float)[None] + ts[:, None] * d[None]
    vals = field_fn((pts[:, 0], pts[:, 1], pts[:, 2]))
    idx = np.nonzero(vals < 0)[0]
    return None if len(idx) == 0 else float(ts[idx[0]])


def sample_grid_field(field, grid, pts):
    """Trilinear lookup of a sampled field at local points (N,3)."""
    from scipy.ndimage import map_coordinates
    idx = (np.asarray(pts, float) - grid.lo) / grid.h
    return map_coordinates(field, idx.T, order=1, mode="nearest")
