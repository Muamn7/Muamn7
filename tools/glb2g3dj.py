#!/usr/bin/env python3
"""
Convert glTF 2.0 / GLB models to libGDX's .g3dj format.

libGDX cannot read glTF, and pulling in a runtime glTF loader would add both a
dependency and per-launch parsing cost on a phone. Converting once, offline, and
committing the .g3dj means the game loads a format it reads natively.

What it handles
---------------
* static meshes  - node transforms are baked into the vertices
* skinned meshes - joints, inverse bind matrices and animations are carried over
* bone limits    - GLES2 only guarantees 128 vec4 vertex uniforms, so a mesh
                   using more joints than fit is split into parts that each
                   reference a small subset (the standard palette-split trick)
* textures       - extracted from the GLB and downscaled to a PS2-era budget

Usage
-----
    python3 tools/glb2g3dj.py INPUT.glb OUT_DIR --name idol [options]

    --scale F        uniform scale applied to the model
    --yaw D          rotate D degrees about Y (glTF models usually face -Z,
                     the game's characters face +Z, so 180 is common)
    --center         re-centre horizontally on the origin
    --floor          drop the lowest vertex to y = 0
    --tex-size N     max texture edge in pixels (default 256)
    --max-bones N    joints per mesh part (default 24)
    --only-mesh RE   keep only source meshes whose name matches this regex
    --list           print the model's contents and exit
"""

import argparse
import base64
import io
import json
import math
import os
import re
import struct
import sys

try:
    from PIL import Image
except ImportError:                                   # pragma: no cover
    Image = None

# glTF component type -> (struct code, byte size)
COMPONENT = {
    5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2),
    5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4),
}
NUM_COMPONENTS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4,
                  'MAT2': 4, 'MAT3': 9, 'MAT4': 16}


# --------------------------------------------------------------------------
# glTF reading
# --------------------------------------------------------------------------

def load_glb(path):
    """Returns (gltf_json, binary_chunk)."""
    with open(path, 'rb') as f:
        data = f.read()
    if data[:4] == b'glTF':
        magic, version, length = struct.unpack_from('<III', data, 0)
        offset, gltf, binary = 12, None, b''
        while offset < length:
            clen, ctype = struct.unpack_from('<II', data, offset)
            offset += 8
            chunk = data[offset:offset + clen]
            offset += clen
            if ctype == 0x4E4F534A:
                gltf = json.loads(chunk.decode('utf-8'))
            elif ctype == 0x004E4942:
                binary = chunk
        return gltf, binary
    # Plain .gltf with an embedded or sibling buffer.
    gltf = json.loads(data.decode('utf-8'))
    binary = b''
    for buf in gltf.get('buffers', []):
        uri = buf.get('uri', '')
        if uri.startswith('data:'):
            binary += base64.b64decode(uri.split(',', 1)[1])
        elif uri:
            with open(os.path.join(os.path.dirname(path), uri), 'rb') as bf:
                binary += bf.read()
    return gltf, binary


def read_accessor(gltf, binary, index):
    """Reads an accessor into a list of tuples (or scalars for SCALAR)."""
    acc = gltf['accessors'][index]
    count = acc['count']
    ncomp = NUM_COMPONENTS[acc['type']]
    code, csize = COMPONENT[acc['componentType']]
    elem_size = ncomp * csize

    if 'bufferView' not in acc:                       # accessor of all zeros
        zero = 0.0 if code == 'f' else 0
        return [tuple([zero] * ncomp) if ncomp > 1 else zero for _ in range(count)]

    view = gltf['bufferViews'][acc['bufferView']]
    base = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
    stride = view.get('byteStride') or elem_size

    normalized = acc.get('normalized', False)
    divisor = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}.get(
        acc['componentType'], 1.0)

    out = []
    fmt = '<' + code * ncomp
    for i in range(count):
        vals = struct.unpack_from(fmt, binary, base + i * stride)
        if normalized:
            vals = tuple(max(v / divisor, -1.0) for v in vals)
        out.append(vals[0] if ncomp == 1 else vals)
    return out


# --------------------------------------------------------------------------
# Small matrix / quaternion helpers (column-major, glTF convention)
# --------------------------------------------------------------------------

def mat_identity():
    return [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def mat_mul(a, b):
    """Column-major a*b, both length-16."""
    out = [0.0] * 16
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4))
    return out


def mat_from_trs(t, r, s):
    x, y, z, w = r
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    m = [
        (1 - 2 * (yy + zz)) * s[0], (2 * (xy + wz)) * s[0], (2 * (xz - wy)) * s[0], 0.0,
        (2 * (xy - wz)) * s[1], (1 - 2 * (xx + zz)) * s[1], (2 * (yz + wx)) * s[1], 0.0,
        (2 * (xz + wy)) * s[2], (2 * (yz - wx)) * s[2], (1 - 2 * (xx + yy)) * s[2], 0.0,
        t[0], t[1], t[2], 1.0,
    ]
    return m


def mat_transform_point(m, p):
    x, y, z = p
    return (m[0] * x + m[4] * y + m[8] * z + m[12],
            m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14])


def mat_transform_dir(m, v):
    x, y, z = v
    return (m[0] * x + m[4] * y + m[8] * z,
            m[1] * x + m[5] * y + m[9] * z,
            m[2] * x + m[6] * y + m[10] * z)


def mat_decompose(m):
    """Splits a matrix into (translation, rotation quaternion, scale)."""
    t = (m[12], m[13], m[14])
    sx = math.sqrt(m[0] ** 2 + m[1] ** 2 + m[2] ** 2)
    sy = math.sqrt(m[4] ** 2 + m[5] ** 2 + m[6] ** 2)
    sz = math.sqrt(m[8] ** 2 + m[9] ** 2 + m[10] ** 2)
    # A negative determinant means a mirrored basis; fold it into x.
    det = (m[0] * (m[5] * m[10] - m[6] * m[9])
           - m[4] * (m[1] * m[10] - m[2] * m[9])
           + m[8] * (m[1] * m[6] - m[2] * m[5]))
    if det < 0:
        sx = -sx
    sx = sx or 1e-8
    sy = sy or 1e-8
    sz = sz or 1e-8
    r = [m[0] / sx, m[1] / sx, m[2] / sx,
         m[4] / sy, m[5] / sy, m[6] / sy,
         m[8] / sz, m[9] / sz, m[10] / sz]
    trace = r[0] + r[4] + r[8]
    if trace > 0:
        k = math.sqrt(trace + 1.0) * 2
        qw, qx, qy, qz = 0.25 * k, (r[5] - r[7]) / k, (r[6] - r[2]) / k, (r[1] - r[3]) / k
    elif r[0] > r[4] and r[0] > r[8]:
        k = math.sqrt(1.0 + r[0] - r[4] - r[8]) * 2
        qw, qx, qy, qz = (r[5] - r[7]) / k, 0.25 * k, (r[3] + r[1]) / k, (r[6] + r[2]) / k
    elif r[4] > r[8]:
        k = math.sqrt(1.0 + r[4] - r[0] - r[8]) * 2
        qw, qx, qy, qz = (r[6] - r[2]) / k, (r[3] + r[1]) / k, 0.25 * k, (r[7] + r[5]) / k
    else:
        k = math.sqrt(1.0 + r[8] - r[0] - r[4]) * 2
        qw, qx, qy, qz = (r[1] - r[3]) / k, (r[6] + r[2]) / k, (r[7] + r[5]) / k, 0.25 * k
    return list(t), [qx, qy, qz, qw], [sx, sy, sz]


def mat_inverse(m):
    """General 4x4 inverse by Gauss-Jordan, column-major in and out."""
    rows = [[m[0], m[4], m[8], m[12]],
            [m[1], m[5], m[9], m[13]],
            [m[2], m[6], m[10], m[14]],
            [m[3], m[7], m[11], m[15]]]
    aug = [rows[r] + [1.0 if c == r else 0.0 for c in range(4)] for r in range(4)]
    for col in range(4):
        pivot = max(range(col, 4), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            return mat_identity()
        aug[col], aug[pivot] = aug[pivot], aug[col]
        d = aug[col][col]
        aug[col] = [v / d for v in aug[col]]
        for r in range(4):
            if r != col and aug[r][col]:
                f = aug[r][col]
                aug[r] = [v - f * w for v, w in zip(aug[r], aug[col])]
    inv = [row[4:] for row in aug]
    return [inv[0][0], inv[1][0], inv[2][0], inv[3][0],
            inv[0][1], inv[1][1], inv[2][1], inv[3][1],
            inv[0][2], inv[1][2], inv[2][2], inv[3][2],
            inv[0][3], inv[1][3], inv[2][3], inv[3][3]]


def node_local_matrix(node):
    if 'matrix' in node:
        return list(node['matrix'])
    return mat_from_trs(node.get('translation', [0, 0, 0]),
                        node.get('rotation', [0, 0, 0, 1]),
                        node.get('scale', [1, 1, 1]))


# --------------------------------------------------------------------------
# Conversion
# --------------------------------------------------------------------------

class Converter:

    def __init__(self, gltf, binary, args):
        self.g = gltf
        self.bin = binary
        self.args = args
        self.nodes = gltf.get('nodes', [])
        self.world = {}
        self.parent = {}
        self._compute_world_transforms()

        # Root transform for the whole model: scale, then pitch, then yaw.
        # Pitch exists because plenty of source models are authored Z-up, and
        # arrive lying on their back; --pitch -90 stands them up.
        k = args.scale
        scale = [k, 0, 0, 0, 0, k, 0, 0, 0, 0, k, 0, 0, 0, 0, 1]
        cp, sp = math.cos(math.radians(args.pitch)), math.sin(math.radians(args.pitch))
        pitch = [1, 0, 0, 0, 0, cp, sp, 0, 0, -sp, cp, 0, 0, 0, 0, 1]
        cy, sy = math.cos(math.radians(args.yaw)), math.sin(math.radians(args.yaw))
        yaw = [cy, 0, -sy, 0, 0, 1, 0, 0, sy, 0, cy, 0, 0, 0, 0, 1]
        self.root = mat_mul(yaw, mat_mul(pitch, scale))

    def _compute_world_transforms(self):
        scenes = self.g.get('scenes', [])
        scene = self.g.get('scene', 0)
        roots = scenes[scene]['nodes'] if scenes else range(len(self.nodes))

        def walk(index, parent_matrix, parent_index):
            self.parent[index] = parent_index
            m = mat_mul(parent_matrix, node_local_matrix(self.nodes[index]))
            self.world[index] = m
            for child in self.nodes[index].get('children', []):
                walk(child, m, index)

        for r in roots:
            walk(r, mat_identity(), None)
        # Nodes outside the scene graph still need a transform.
        for i in range(len(self.nodes)):
            if i not in self.world:
                self.world[i] = mat_identity()
                self.parent.setdefault(i, None)

    # -- naming -------------------------------------------------------

    def node_id(self, index):
        name = self.nodes[index].get('name') or ('node%d' % index)
        return '%s_%d' % (re.sub(r'[^A-Za-z0-9_]', '_', name), index)

    # -- textures -----------------------------------------------------

    def export_textures(self, out_dir, prefix):
        """Writes every image out as PNG, downscaled. Returns index -> filename."""
        os.makedirs(out_dir, exist_ok=True)
        result = {}
        for i, img in enumerate(self.g.get('images', [])):
            data = None
            if 'bufferView' in img:
                view = self.g['bufferViews'][img['bufferView']]
                start = view.get('byteOffset', 0)
                data = self.bin[start:start + view['byteLength']]
            elif img.get('uri', '').startswith('data:'):
                data = base64.b64decode(img['uri'].split(',', 1)[1])
            if data is None:
                continue

            name = '%s_%d.png' % (prefix, i)
            path = os.path.join(out_dir, name)
            if Image is None:
                # Without Pillow, keep the original bytes and its own extension.
                ext = '.jpg' if img.get('mimeType') == 'image/jpeg' else '.png'
                name = '%s_%d%s' % (prefix, i, ext)
                path = os.path.join(out_dir, name)
                with open(path, 'wb') as f:
                    f.write(data)
            else:
                im = Image.open(io.BytesIO(data)).convert('RGBA')
                limit = self.args.tex_size
                if max(im.size) > limit:
                    scale = limit / float(max(im.size))
                    im = im.resize((max(1, int(im.width * scale)),
                                    max(1, int(im.height * scale))), Image.LANCZOS)
                # Flatten to RGB unless the texture actually uses alpha.
                alpha = im.getchannel('A')
                if alpha.getextrema()[0] == 255:
                    im = im.convert('RGB')
                im.save(path, optimize=True)
            result[i] = name
            print('   texture %d -> %s' % (i, name))
        return result

    def material_texture(self, material_index):
        if material_index is None:
            return None
        mat = self.g.get('materials', [])[material_index]
        pbr = mat.get('pbrMetallicRoughness', {})
        info = pbr.get('baseColorTexture')
        if info is None:
            return None
        tex = self.g['textures'][info['index']]
        return tex.get('source')

    # -- geometry -----------------------------------------------------

    def primitive_vertices(self, prim, node_index, skinned):
        """Returns (attribute names, per-vertex float rows, indices)."""
        attrs = prim['attributes']
        positions = read_accessor(self.g, self.bin, attrs['POSITION'])
        count = len(positions)
        normals = (read_accessor(self.g, self.bin, attrs['NORMAL'])
                   if 'NORMAL' in attrs else [(0.0, 1.0, 0.0)] * count)
        uvs = (read_accessor(self.g, self.bin, attrs['TEXCOORD_0'])
               if 'TEXCOORD_0' in attrs else [(0.0, 0.0)] * count)

        joints = weights = None
        if skinned and 'JOINTS_0' in attrs and 'WEIGHTS_0' in attrs:
            joints = read_accessor(self.g, self.bin, attrs['JOINTS_0'])
            weights = read_accessor(self.g, self.bin, attrs['WEIGHTS_0'])

        if 'indices' in prim:
            indices = [int(i) for i in read_accessor(self.g, self.bin, prim['indices'])]
        else:
            indices = list(range(count))

        # A static primitive gets its node transform (and the model's root scale
        # and yaw) baked straight into the vertices.
        #
        # A skinned one must not: its vertices are consumed as
        # `jointGlobal * inverseBind * v`, so scaling v as well as the skeleton
        # would apply the root transform twice. The root transform goes on a
        # wrapper node above the skeleton instead - which also keeps it safe from
        # animations that overwrite the root joint's translation outright.
        transform = mat_identity() if skinned else mat_mul(self.root, self.world[node_index])

        rows = []
        for i in range(count):
            p = mat_transform_point(transform, positions[i])
            n = mat_transform_dir(transform, normals[i])
            length = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
            u, v = uvs[i][0], uvs[i][1]
            row = [p[0], p[1], p[2], n[0] / length, n[1] / length, n[2] / length, u, v]
            if joints is not None:
                jw = sorted(zip(joints[i], weights[i]), key=lambda e: -e[1])[:4]
                total = sum(w for _, w in jw) or 1.0
                for j, w in jw:
                    row.extend([float(int(j)), w / total])
                for _ in range(4 - len(jw)):
                    row.extend([0.0, 0.0])
            rows.append(row)

        names = ['POSITION', 'NORMAL', 'TEXCOORD0']
        if joints is not None:
            names += ['BLENDWEIGHT0', 'BLENDWEIGHT1', 'BLENDWEIGHT2', 'BLENDWEIGHT3']
        return names, rows, indices

    @staticmethod
    def partition_by_bones(rows, indices, max_bones):
        """
        Splits triangles into groups that each touch at most `max_bones` joints.

        GLES2 only promises 128 vec4 vertex uniforms - about 30 bone matrices -
        so a 54-joint character has to be drawn in several passes with a
        different bone palette each time.
        """
        groups = []                       # list of (index list, joint list)
        current, palette = [], []

        def joints_of(vertex):
            used = set()
            for k in range(4):
                bone = int(rows[vertex][8 + k * 2])
                weight = rows[vertex][9 + k * 2]
                if weight > 0.0:
                    used.add(bone)
            return used or {0}

        for t in range(0, len(indices) - 2, 3):
            tri = indices[t:t + 3]
            needed = set()
            for v in tri:
                needed |= joints_of(v)
            new = needed - set(palette)
            if len(palette) + len(new) > max_bones and current:
                groups.append((current, list(palette)))
                current, palette = [], []
                new = needed
            palette.extend(sorted(new - set(palette)))
            current.extend(tri)
        if current:
            groups.append((current, list(palette)))
        return groups

    # -- animations ---------------------------------------------------

    def convert_animations(self, joint_indices, bind_locals, keep=None):
        """
        Converts glTF animation channels into g3dj bone tracks.

        Uses the per-path track format rather than one combined keyframe list.
        A 54-joint character with 14 animations is mostly redundant data: joints
        that never move, tracks whose value never changes, and long constant
        runs. Dropping those turns megabytes of JSON into something an APK can
        reasonably carry, with no visible difference.
        """
        joint_set = set(joint_indices)
        pattern = re.compile(keep) if keep else None
        animations = []

        for anim in self.g.get('animations', []):
            name = anim.get('name') or ('anim%d' % len(animations))
            if pattern and not pattern.search(name):
                continue

            per_node = {}
            for channel in anim['channels']:
                target = channel['target']
                node = target.get('node')
                path = target['path']
                if node is None or node not in joint_set or path == 'weights':
                    continue
                sampler = anim['samplers'][channel['sampler']]
                times = read_accessor(self.g, self.bin, sampler['input'])
                values = read_accessor(self.g, self.bin, sampler['output'])
                if sampler.get('interpolation') == 'CUBICSPLINE':
                    # Each output is a (inTangent, value, outTangent) triple.
                    values = values[1::3]
                per_node.setdefault(node, {})[path] = (times, values)

            bones = []
            for node, paths in per_node.items():
                # Compare against the emitted bind-pose rest, not the file's node
                # TRS: dropping a constant track leaves whatever we wrote as the
                # joint's local transform, so that is what "unchanged" must mean.
                rest_t, rest_r, rest_s = mat_decompose(bind_locals[node])
                track = {'boneId': self.node_id(node)}
                for path, key, default, precision, tol in (
                        ('translation', 'translation', rest_t, 4, 0.002),
                        ('rotation', 'rotation', rest_r, 4, 0.004),
                        ('scale', 'scaling', rest_s, 3, 0.006)):
                    if path not in paths:
                        continue
                    times, values = paths[path]
                    frames = compress_track(times, values, default, precision, tol)
                    if frames:
                        track[key] = frames
                if len(track) > 1:
                    bones.append(track)

            if bones:
                animations.append({'id': name, 'bones': bones})
        return animations


def compress_track(times, values, rest, precision, tol):
    """
    Reduces one animation track to the keyframes that actually matter.

    Exporters bake a key on every frame for every joint, so most of the data is
    either a joint that never moves or a value linear interpolation would have
    produced anyway. `tol` is the error budget in the track's own units - a few
    thousandths of a quaternion component is well under a degree, which no player
    will ever see, and it removes the large majority of keys.
    """
    if not times:
        return None

    def close(a, b):
        return all(abs(x - y) <= tol for x, y in zip(a, b))

    rest = list(rest) + [0.0] * max(0, len(values[0]) - len(rest))
    if all(close(v, rest) for v in values):
        return None

    keep = [0]
    for i in range(1, len(values) - 1):
        span = times[i + 1] - times[keep[-1]]
        a = (times[i] - times[keep[-1]]) / span if span else 0.0
        predicted = [values[keep[-1]][k] + (values[i + 1][k] - values[keep[-1]][k]) * a
                     for k in range(len(values[i]))]
        if not close(values[i], predicted):
            keep.append(i)
    if len(values) > 1:
        keep.append(len(values) - 1)

    return [{'keytime': round(times[i] * 1000.0, 2),
             'value': [round(v, precision) for v in values[i]]} for i in keep]


def sample(times, values, t):
    """Linear sample of a keyframe track at time t."""
    if t <= times[0]:
        return list(values[0])
    if t >= times[-1]:
        return list(values[-1])
    lo, hi = 0, len(times) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if times[mid] <= t:
            lo = mid
        else:
            hi = mid
    span = times[hi] - times[lo] or 1.0
    a = (t - times[lo]) / span
    va, vb = values[lo], values[hi]
    if len(va) == 4:                      # quaternion: shortest-arc slerp
        return slerp(va, vb, a)
    return [va[i] + (vb[i] - va[i]) * a for i in range(len(va))]


def slerp(a, b, t):
    dot = sum(a[i] * b[i] for i in range(4))
    if dot < 0:
        b = [-v for v in b]
        dot = -dot
    if dot > 0.9995:
        out = [a[i] + (b[i] - a[i]) * t for i in range(4)]
    else:
        theta = math.acos(max(-1.0, min(1.0, dot)))
        st = math.sin(theta)
        wa, wb = math.sin((1 - t) * theta) / st, math.sin(t * theta) / st
        out = [a[i] * wa + b[i] * wb for i in range(4)]
    norm = math.sqrt(sum(v * v for v in out)) or 1.0
    return [v / norm for v in out]


# --------------------------------------------------------------------------

def convert(args):
    gltf, binary = load_glb(args.input)
    conv = Converter(gltf, binary, args)

    if args.list:
        for i, mesh in enumerate(gltf.get('meshes', [])):
            print('mesh %d: %s' % (i, mesh.get('name')))
        for i, anim in enumerate(gltf.get('animations', [])):
            print('anim %d: %s' % (i, anim.get('name')))
        return

    # Textures sit next to the .g3dj. libGDX resolves texture filenames relative
    # to the model file, and a "../textures/" prefix does not resolve through
    # Android's asset manager - a plain filename in the same folder always does.
    model_dir = os.path.join(args.out, 'models')
    os.makedirs(model_dir, exist_ok=True)
    image_files = conv.export_textures(model_dir, args.name)

    # ---- materials ----
    materials, material_ids = [], {}
    for i, mat in enumerate(gltf.get('materials', [])):
        mid = 'mat%d' % i
        material_ids[i] = mid
        pbr = mat.get('pbrMetallicRoughness', {})
        base = pbr.get('baseColorFactor', [1, 1, 1, 1])
        entry = {'id': mid, 'diffuse': [round(c, 4) for c in base[:3]]}
        source = conv.material_texture(i)
        if source is not None and source in image_files:
            entry['textures'] = [{'id': 'tex%d' % i,
                                  'filename': image_files[source],
                                  'type': 'DIFFUSE'}]
        if mat.get('alphaMode') == 'BLEND':
            entry['opacity'] = round(base[3], 4)
        materials.append(entry)
    if not materials:
        materials = [{'id': 'mat0', 'diffuse': [1, 1, 1]}]
        material_ids[None] = 'mat0'

    # ---- geometry ----
    keep = re.compile(args.only_mesh) if args.only_mesh else None
    meshes, static_parts, skinned_parts = [], [], []
    static_meshes = []
    joint_indices, inverse_binds, bind_globals = [], {}, {}
    bounds = [1e30, 1e30, 1e30, -1e30, -1e30, -1e30]

    for node_index, node in enumerate(conv.nodes):
        if 'mesh' not in node:
            continue
        mesh = gltf['meshes'][node['mesh']]
        if keep and not keep.search(mesh.get('name', '')):
            continue

        # A skinned mesh's vertices are already in bind-pose world space, because
        # jointGlobal * inverseBind is the identity at bind time. So a rig with no
        # animations - or a weapon we only want the geometry of - can be flattened
        # to a static mesh and skip the bones entirely.
        skin_index = None if args.unskin else node.get('skin')
        skinned = skin_index is not None
        if skinned and not joint_indices:
            skin = gltf['skins'][skin_index]
            joint_indices = list(skin['joints'])
            if 'inverseBindMatrices' in skin:
                mats = read_accessor(gltf, binary, skin['inverseBindMatrices'])
                for j, joint in enumerate(joint_indices):
                    inverse_binds[joint] = list(mats[j])
            bind_globals = bind_globals_of(conv, joint_indices, inverse_binds)

        for prim_index, prim in enumerate(mesh['primitives']):
            if prim.get('mode', 4) != 4:               # triangles only
                continue
            names, rows, indices = conv.primitive_vertices(prim, node_index, skinned)
            if not rows:
                continue

            # Skinned vertices are still in unscaled skin space, so measure them
            # through the root transform to get the model's final size.
            for row in rows:
                p = mat_transform_point(conv.root, row[:3]) if skinned else row[:3]
                for a in range(3):
                    bounds[a] = min(bounds[a], p[a])
                    bounds[a + 3] = max(bounds[a + 3], p[a])

            mesh_id = 'mesh_%d_%d' % (node_index, prim_index)
            material_id = material_ids.get(prim.get('material'), materials[0]['id'])
            parts = []

            if skinned:
                groups = Converter.partition_by_bones(rows, indices, args.max_bones)
                # Each group needs its own copy of any vertex it shares with
                # another group, because the joint ids are rewritten to that
                # group's palette. Build one combined vertex array as we go.
                combined = []
                for gi, (group_indices, palette) in enumerate(groups):
                    part_id = '%s_p%d' % (mesh_id, gi)
                    slot = {bone: k for k, bone in enumerate(palette)}
                    part_indices = append_group(combined, rows, group_indices, slot)
                    parts.append({'id': part_id, 'type': 'TRIANGLES',
                                  'indices': part_indices})
                    skinned_parts.append({
                        'meshpartid': part_id,
                        'materialid': material_id,
                        'bones': [bone_entry(conv, joint_indices, bind_globals, b)
                                  for b in palette],
                    })
                rows = combined
            else:
                parts.append({'id': mesh_id + '_p0', 'type': 'TRIANGLES',
                              'indices': indices})
                static_parts.append({'meshpartid': mesh_id + '_p0',
                                     'materialid': material_id})

            flat = [round(v, 5) for row in rows for v in row]
            entry = {'attributes': names, 'vertices': flat, 'parts': parts}
            meshes.append(entry)
            if not skinned:
                static_meshes.append(entry)

    if not meshes:
        sys.exit('no triangle meshes matched')

    # ---- optional re-centring ----
    offset = [0.0, 0.0, 0.0]
    if args.center:
        offset[0] = -(bounds[0] + bounds[3]) * 0.5
        offset[2] = -(bounds[2] + bounds[5]) * 0.5
    if args.floor:
        offset[1] = -bounds[1]
    if any(offset):
        # Static geometry moves at the vertex level; skinned geometry moves by
        # shifting the wrapper node above the skeleton, further down.
        for mesh in static_meshes:
            width = row_width(mesh['attributes'])
            verts = mesh['vertices']
            for i in range(0, len(verts), width):
                verts[i] += offset[0]
                verts[i + 1] += offset[1]
                verts[i + 2] += offset[2]

    # ---- nodes ----
    nodes = []
    if static_parts:
        nodes.append({'id': args.name + '_static', 'parts': static_parts})
    if skinned_parts:
        nodes.append({'id': args.name + '_skin', 'parts': skinned_parts})
        bind_locals = bind_pose_locals(conv, joint_indices, bind_globals)
        nodes.append(build_rig_node(conv, args.name, joint_indices, bind_locals, offset))

    model = {
        'version': [0, 1],
        'id': args.name,
        'meshes': meshes,
        'materials': materials,
        'nodes': nodes,
        'animations': (conv.convert_animations(joint_indices, bind_locals, args.anims)
                       if joint_indices else []),
    }

    out_path = os.path.join(model_dir, args.name + '.g3dj')
    with open(out_path, 'w') as f:
        json.dump(model, f, separators=(',', ':'))

    tris = sum(len(p['indices']) // 3 for m in meshes for p in m['parts'])
    size = [round(bounds[a + 3] - bounds[a], 3) for a in range(3)]
    print('   %s: %d tris, %d mesh parts, %d joints, %d animations, size %s'
          % (args.name, tris, sum(len(m['parts']) for m in meshes),
             len(joint_indices), len(model['animations']), size))
    print('   wrote %s (%.1f KB)' % (out_path, os.path.getsize(out_path) / 1024.0))


def row_width(attributes):
    width = 0
    for a in attributes:
        width += {'POSITION': 3, 'NORMAL': 3}.get(a, 2)
    return width


def append_group(combined, rows, group_indices, slot):
    """
    Copies a triangle group's vertices into `combined`, rewriting their joint ids
    to index the group's own bone palette. Returns the group's indices.
    """
    lookup, new_indices = {}, []
    for v in group_indices:
        if v not in lookup:
            row = list(rows[v])
            for k in range(4):
                bone = int(row[8 + k * 2])
                row[8 + k * 2] = float(slot.get(bone, 0))
            lookup[v] = len(combined)
            combined.append(row)
        new_indices.append(lookup[v])
    return new_indices


def bone_entry(conv, joint_indices, bind_globals, bone):
    """
    One entry of a node part's `bones` list.

    The .g3dj format stores the joint's BIND POSE transform here, not its inverse
    - libGDX inverts it on load (Model.java: `new Matrix4(b.value).inv()`). Emit
    the inverse bind matrix straight from the glTF and every skinned vertex is
    transformed by the square of the wrong matrix.
    """
    joint = joint_indices[bone] if bone < len(joint_indices) else joint_indices[0]
    t, r, s = mat_decompose(bind_globals.get(joint, mat_identity()))
    return {'node': conv.node_id(joint),
            'translation': [round(v, 6) for v in t],
            'rotation': [round(v, 6) for v in r],
            'scale': [round(v, 6) for v in s]}


def bind_globals_of(conv, joint_indices, inverse_binds):
    """Bind-pose world transform of each joint: the inverse of its inverse bind."""
    out = {}
    for j in joint_indices:
        inv = inverse_binds.get(j)
        out[j] = mat_inverse(inv) if inv else conv.world[j]
    return out


def bind_pose_locals(conv, joint_indices, bind_globals):
    """
    Derives each joint's rest transform from the inverse bind matrices.

    Exporters routinely leave the scene graph posed at frame 0 of some animation
    rather than at the bind pose, so the node TRS in the file cannot be trusted
    as a rest pose - use it and the mesh renders as a spray of stretched
    triangles. The inverse bind matrices are authoritative: the bind-pose world
    transform of a joint is exactly their inverse, and a local transform follows
    from dividing out the parent's.

    Returns {joint node index: local matrix}.
    """
    joint_set = set(joint_indices)
    globals_ = bind_globals
    locals_ = {}
    for j in joint_indices:
        parent = conv.parent.get(j)
        if parent in joint_set:
            locals_[j] = mat_mul(mat_inverse(globals_[parent]), globals_[j])
        else:
            locals_[j] = globals_[j]
    return locals_


def build_rig_node(conv, name, joint_indices, bind_locals, offset):
    """
    Emits the skeleton under a single wrapper node that carries the model's
    scale, yaw and re-centring.

    The wrapper matters: animations overwrite a joint's translation and rotation
    outright, so anything baked onto a root joint would be thrown away the moment
    an animation played. A parent node is never touched by the animation data.
    """
    joint_set = set(joint_indices)
    roots = [j for j in joint_indices
             if conv.parent.get(j) is None or conv.parent.get(j) not in joint_set]

    def build(index):
        t, r, s = mat_decompose(bind_locals[index])
        out = {'id': conv.node_id(index),
               'translation': [round(v, 6) for v in t],
               'rotation': [round(v, 6) for v in r],
               'scale': [round(v, 6) for v in s]}
        children = [c for c in conv.nodes[index].get('children', []) if c in joint_set]
        if children:
            out['children'] = [build(c) for c in children]
        return out

    t, r, s = mat_decompose(conv.root)
    return {'id': name + '_rig',
            'translation': [round(t[0] + offset[0], 6),
                            round(t[1] + offset[1], 6),
                            round(t[2] + offset[2], 6)],
            'rotation': [round(v, 6) for v in r],
            'scale': [round(v, 6) for v in s],
            'children': [build(j) for j in roots]}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input')
    ap.add_argument('out', nargs='?', default='assets/imported')
    ap.add_argument('--name', required=False, default=None)
    ap.add_argument('--scale', type=float, default=1.0)
    ap.add_argument('--yaw', type=float, default=0.0)
    ap.add_argument('--pitch', type=float, default=0.0,
                    help='rotate about X; use -90 for Z-up source models')
    ap.add_argument('--center', action='store_true')
    ap.add_argument('--floor', action='store_true')
    ap.add_argument('--tex-size', type=int, default=256)
    ap.add_argument('--max-bones', type=int, default=24)
    ap.add_argument('--only-mesh', default=None)
    ap.add_argument('--unskin', action='store_true',
                    help='flatten skinned meshes to static bind-pose geometry')
    ap.add_argument('--anims', default=None, help='regex of animation names to keep')
    ap.add_argument('--list', action='store_true')
    args = ap.parse_args()
    if args.name is None:
        args.name = os.path.splitext(os.path.basename(args.input))[0]
    print('converting %s' % os.path.basename(args.input))
    convert(args)


if __name__ == '__main__':
    main()
