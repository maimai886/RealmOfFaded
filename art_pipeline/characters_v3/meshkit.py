"""手刻低面數網格用的小工具

角色全部用程式算頂點堆出來，不靠修改器和布林，形狀才能精準控制也才重跑得出一樣的結果。
座標約定跟骨架一致：+X 是角色的左手邊，-Y 是角色面向的方向，+Z 是上。
每個頂點會記自己屬於哪個身體部位，綁骨頭時只在那個部位的骨頭裡找最近的，
手臂的權重就不會沾到身體，比自動權重穩定得多。
"""

import math

import bpy
from mathutils import Vector

TAU = math.pi * 2.0


class Builder:
    """累積頂點和面，最後一次做成一個帶多個材質槽的網格"""

    def __init__(self):
        self.verts = []
        self.regions = []
        self.faces = []
        self.face_mats = []
        self.face_uvs = []

    def add_verts(self, verts, region=None):
        base = len(self.verts)
        for vert in verts:
            self.verts.append(Vector(vert))
            self.regions.append(region)
        return base

    def add_face(self, indices, mat=0, uvs=None):
        self.faces.append(list(indices))
        self.face_mats.append(mat)
        self.face_uvs.append(uvs)

    def add_quad(self, a, b, c, d, mat=0, uvs=None):
        self.add_face((a, b, c, d), mat, uvs)

    def to_object(self, name, materials):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([tuple(v) for v in self.verts], [], self.faces)
        mesh.update()
        for material in materials:
            mesh.materials.append(material)
        layer = mesh.uv_layers.new(name="UVMap")
        for index, polygon in enumerate(mesh.polygons):
            polygon.material_index = self.face_mats[index]
            uvs = self.face_uvs[index]
            for offset, loop in enumerate(polygon.loop_indices):
                layer.data[loop].uv = uvs[offset] if uvs else (0.5, 0.5)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.view_layer.active_layer_collection.collection.objects.link(obj)
        obj["regions"] = [",".join(r) if r else "" for r in self.regions]
        return obj


def _bands(mat, count):
    """材質可以給單一編號或每一段各一個編號"""
    if isinstance(mat, (list, tuple)):
        return list(mat) + [mat[-1]] * (count - len(mat))
    return [mat] * count


def ring(center, rx, ry, n, flatten_back=1.0, front_shift=0.0):
    """在水平面上繞一圈的頂點，第 0 個在角色正前方也就是 -Y"""
    cx, cy, cz = center
    out = []
    for i in range(n):
        t = TAU * i / n
        x = math.sin(t) * rx
        y = -math.cos(t) * ry
        if y > 0:
            y *= flatten_back
        else:
            y -= front_shift * (-y / max(ry, 1e-6))
        out.append(Vector((cx + x, cy + y, cz)))
    return out


def bridge(builder, lower, upper, mat=0, flip=False):
    """mat 可以是材質編號，也可以是吃欄位編號的函式，用來做正面一片別的顏色的胸甲"""
    n = len(lower)
    for i in range(n):
        j = (i + 1) % n
        quad = (lower[i], lower[j], upper[j], upper[i])
        column_mat = mat(i) if callable(mat) else mat
        builder.add_quad(*(tuple(reversed(quad)) if flip else quad), mat=column_mat)


def front_columns(n, half_span_deg):
    """一圈裡位於正面某個角度範圍內的欄位編號，第 0 個頂點在正前方"""
    out = set()
    for i in range(n):
        center = (i + 0.5) * 360.0 / n
        if min(center, 360.0 - center) <= half_span_deg:
            out.add(i)
    return out


def cap(builder, loop, center_index, mat=0, flip=False):
    n = len(loop)
    for i in range(n):
        j = (i + 1) % n
        tri = (loop[i], loop[j], center_index)
        builder.add_face(tuple(reversed(tri)) if flip else tri, mat=mat)


def loft(builder, sections, mat=0, region=None, cap_bottom=True, cap_top=True):
    """把一疊由下到上的環接起來，mat 可以每一段不同"""
    rings = []
    for section in sections:
        base = builder.add_verts(section, region)
        rings.append([base + i for i in range(len(section))])
    mats = _bands(mat, len(rings) - 1)
    for index, (lower, upper) in enumerate(zip(rings, rings[1:])):
        bridge(builder, lower, upper, mat=mats[index])
    if cap_bottom:
        pts = [builder.verts[i] for i in rings[0]]
        center = builder.add_verts([sum(pts, Vector()) / len(pts)], region)
        cap(builder, rings[0], center, mat=mats[0], flip=False)
    if cap_top:
        pts = [builder.verts[i] for i in rings[-1]]
        center = builder.add_verts([sum(pts, Vector()) / len(pts)], region)
        cap(builder, rings[-1], center, mat=mats[-1], flip=True)
    return rings


def sweep(builder, path, radii, n, mat=0, region=None, up=Vector((0, 0, 1)),
          cap_start=True, cap_end=True, squash=None):
    """沿著一條折線掃出管子，用來做手臂和腿"""
    rings = []
    for index, point in enumerate(path):
        if index == 0:
            direction = Vector(path[1]) - Vector(path[0])
        elif index == len(path) - 1:
            direction = Vector(path[-1]) - Vector(path[-2])
        else:
            direction = Vector(path[index + 1]) - Vector(path[index - 1])
        direction.normalize()
        side = Vector(up).cross(direction)
        if side.length < 1e-4:
            side = Vector((1, 0, 0)).cross(direction)
        side.normalize()
        other = direction.cross(side).normalized()
        radius = radii[index]
        depth = radius * (squash[index] if squash else 1.0)
        section = [Vector(point) + side * (math.cos(TAU * i / n) * radius)
                   + other * (math.sin(TAU * i / n) * depth) for i in range(n)]
        base = builder.add_verts(section, region)
        rings.append([base + i for i in range(n)])
    mats = _bands(mat, len(rings) - 1)
    for index, (lower, upper) in enumerate(zip(rings, rings[1:])):
        bridge(builder, lower, upper, mat=mats[index], flip=True)
    if cap_start:
        pts = [builder.verts[i] for i in rings[0]]
        center = builder.add_verts([sum(pts, Vector()) / len(pts)], region)
        cap(builder, rings[0], center, mat=mats[0], flip=False)
    if cap_end:
        pts = [builder.verts[i] for i in rings[-1]]
        center = builder.add_verts([sum(pts, Vector()) / len(pts)], region)
        cap(builder, rings[-1], center, mat=mats[-1], flip=True)
    return rings


def sphere(builder, center, radius, segments=14, rings_count=8, mat=0, region=None,
           scale=(1, 1, 1), shift=None):
    """球體，scale 壓成橢圓，shift 是依高度做的前後位移，用來削平後腦勺"""
    cx, cy, cz = center
    sx, sy, sz = scale
    rows = []
    top = builder.add_verts([(cx, cy + (shift(1.0) if shift else 0.0), cz + radius * sz)], region)
    for r in range(1, rings_count):
        phi = math.pi * r / rings_count
        z = math.cos(phi)
        rad = math.sin(phi)
        section = []
        for i in range(segments):
            t = TAU * i / segments
            x = math.sin(t) * rad * radius * sx
            y = -math.cos(t) * rad * radius * sy
            section.append((cx + x, cy + y + (shift(z) if shift else 0.0), cz + z * radius * sz))
        base = builder.add_verts(section, region)
        rows.append([base + i for i in range(segments)])
    bottom = builder.add_verts([(cx, cy + (shift(-1.0) if shift else 0.0), cz - radius * sz)], region)
    for i in range(segments):
        j = (i + 1) % segments
        builder.add_face((top, rows[0][j], rows[0][i]), mat=mat)
        builder.add_face((bottom, rows[-1][i], rows[-1][j]), mat=mat)
    for lower, upper in zip(rows, rows[1:]):
        bridge(builder, upper, lower, mat=mat)
    return rows


def blob(builder, center, size, mat=0, region=None, segments=10, rings_count=6, shift=None):
    """壓扁的球，手掌和頭髮量體都用這個"""
    radius = max(size)
    return sphere(builder, center, radius, segments, rings_count, mat, region,
                  scale=(size[0] / radius, size[1] / radius, size[2] / radius), shift=shift)


# 圓角方塊橫截面的取樣點，走一圈四個角各有兩個點，細分之後角是圓的、邊還是直的
_ROUND_RECT = [(1.0, 0.62), (0.62, 1.0), (-0.62, 1.0), (-1.0, 0.62),
               (-1.0, -0.62), (-0.62, -1.0), (0.62, -1.0), (1.0, -0.62)]


def box(builder, center, size, mat=0, region=None, taper=(1.0, 1.0), shear=0.0):
    """圓角方塊，taper 是上端的左右和前後縮放，shear 是上端往前後偏移

    不是八個角的純長方體：細分曲面會把純長方體縮成一顆小球，尺寸整個跑掉。
    這裡橫截面用圓角矩形、上下各多一層內縮的環，細分之後才留得住原本的大小和方正的感覺，
    同時每個轉折都是圓角，符合 docs/美術風格指南.md 的「剪影裡沒有硬角」。
    """
    cx, cy, cz = center
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    # 由下到上四層：最下、下肩、上肩、最上；最下和最上稍微內縮做出上下的圓角
    levels = [(-1.0, 0.80), (-0.80, 1.0), (0.80, 1.0), (1.0, 0.80)]
    sections = []
    for level, inset in levels:
        t = (level + 1.0) / 2.0
        fx = 1.0 + (taper[0] - 1.0) * t
        fy = 1.0 + (taper[1] - 1.0) * t
        dy = shear * t
        section = [(cx + sx * hx * fx * inset, cy + sy * hy * fy * inset + dy, cz + level * hz)
                   for sx, sy in _ROUND_RECT]
        sections.append(section)
    loft(builder, sections, mat=mat, region=region, cap_bottom=True, cap_top=True)
    return len(builder.verts)


def patch(builder, corners, cols, rows, mat=0, region=None, uv_rect=(0, 0, 1, 1), project=None):
    """帶 UV 的格狀面片，用來做臉。corners 是左下、右下、右上、左上"""
    p00, p10, p11, p01 = [Vector(c) for c in corners]
    u0, v0, u1, v1 = uv_rect
    grid = []
    for r in range(rows + 1):
        fv = r / rows
        row = []
        for c in range(cols + 1):
            fu = c / cols
            point = (p00.lerp(p10, fu)).lerp(p01.lerp(p11, fu), fv)
            if project:
                point = project(point, fu, fv)
            row.append(point)
        base = builder.add_verts(row, region)
        grid.append([base + i for i in range(cols + 1)])
    for r in range(rows):
        for c in range(cols):
            fu0, fu1 = c / cols, (c + 1) / cols
            fv0, fv1 = r / rows, (r + 1) / rows
            uvs = [(u0 + (u1 - u0) * fu0, v0 + (v1 - v0) * fv0),
                   (u0 + (u1 - u0) * fu1, v0 + (v1 - v0) * fv0),
                   (u0 + (u1 - u0) * fu1, v0 + (v1 - v0) * fv1),
                   (u0 + (u1 - u0) * fu0, v0 + (v1 - v0) * fv1)]
            builder.add_quad(grid[r][c], grid[r][c + 1], grid[r + 1][c + 1], grid[r + 1][c],
                             mat=mat, uvs=uvs)
    return grid


def mirror_x(builder, start_vert, start_face):
    """把某個索引之後建立的幾何鏡射到另一邊，左右手左右腳只要寫一次"""
    offset = len(builder.verts) - start_vert
    originals = builder.verts[start_vert:]
    regions = builder.regions[start_vert:]
    for vert, region in zip(originals, regions):
        flipped = tuple(r.replace(".l", ".r") if r.endswith(".l") else
                        r.replace(".r", ".l") if r.endswith(".r") else r
                        for r in region) if region else None
        builder.add_verts([(-vert.x, vert.y, vert.z)], flipped)
    for index in range(start_face, len(builder.faces)):
        face = builder.faces[index]
        builder.add_face([i + offset if i >= start_vert else i for i in reversed(face)],
                         mat=builder.face_mats[index], uvs=builder.face_uvs[index])


def subdivide(obj, levels=1):
    """加一個細分曲面修改器，讓手刻的低面數量體變成飽滿的圓弧

    照 docs/美術風格指南.md：這個畫風的質感有一大半來自「剪影裡沒有硬角」，
    所以每個網格建好之後都過一次細分。放在骨架修改器後面，變形完才細分，關節才不會被拉出稜角。
    """
    modifier = obj.modifiers.new("Subdivision", "SUBSURF")
    modifier.subdivision_type = "CATMULL_CLARK"
    modifier.levels = levels
    modifier.render_levels = levels
    if hasattr(modifier, "use_limit_surface"):
        modifier.use_limit_surface = True
    return obj


def subdivide_apply(obj, levels=1):
    """把細分曲面直接烘進網格

    模組化角色要匯出成 glb，而 glTF 匯出時一旦選擇烘修改器就會連骨架修改器一起烘掉、蒙皮整個不見。
    所以細分要在綁骨架之前就烘進網格，之後匯出時什麼都不烘，蒙皮和動畫才留得住。
    """
    import bpy as _bpy
    modifier = obj.modifiers.new("Subdivision", "SUBSURF")
    modifier.subdivision_type = "CATMULL_CLARK"
    modifier.levels = levels
    modifier.render_levels = levels
    if hasattr(modifier, "use_limit_surface"):
        modifier.use_limit_surface = True
    _bpy.context.view_layer.objects.active = obj
    # 綁完骨架才細分：頂點群組會跟著內插到新的頂點上，但每個頂點自己記的區域標籤不會，
    # 所以順序一定是先綁再細分。細分要排在骨架修改器前面才套得下去
    if len(obj.modifiers) > 1:
        _bpy.ops.object.modifier_move_to_index(modifier=modifier.name, index=0)
    _bpy.ops.object.modifier_apply(modifier=modifier.name)
    return obj


def shade(obj, angle=math.radians(72)):
    """平滑著色，夾角超過門檻的邊才標成銳利邊

    圓潤風幾乎不要硬邊，所以門檻訂得很高，只有接近直角的轉折才留成銳利邊。
    """
    mesh = obj.data
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    mesh.calc_loop_triangles()
    face_normals = {p.index: p.normal.copy() for p in mesh.polygons}
    edge_faces = {}
    for polygon in mesh.polygons:
        for key in polygon.edge_keys:
            edge_faces.setdefault(key, []).append(polygon.index)
    sharp = set()
    for key, faces in edge_faces.items():
        if len(faces) != 2:
            sharp.add(key)
            continue
        if face_normals[faces[0]].angle(face_normals[faces[1]]) > angle:
            sharp.add(key)
    for edge in mesh.edges:
        edge.use_edge_sharp = (edge.key in sharp)
    return obj


# 身體各區域允許用到的骨頭，綁權重時只在自己這一區裡找
REGION_TORSO = ("hips", "spine", "chest")
REGION_HEAD = ("head",)
REGION_NECK = ("chest", "head")
REGION_ARM_L = ("chest", "upperarm.l", "lowerarm.l", "wrist.l", "hand.l")
REGION_ARM_R = ("chest", "upperarm.r", "lowerarm.r", "wrist.r", "hand.r")
REGION_LEG_L = ("hips", "upperleg.l", "lowerleg.l", "foot.l", "toes.l")
REGION_LEG_R = ("hips", "upperleg.r", "lowerleg.r", "foot.r", "toes.r")
REGION_SKIRT = ("hips", "upperleg.l", "upperleg.r")


def _segment_distance(point, head, tail):
    axis = tail - head
    length_sq = axis.length_squared
    if length_sq < 1e-9:
        return (point - head).length
    t = max(0.0, min(1.0, (point - head).dot(axis) / length_sq))
    return (point - (head + axis * t)).length


def bind(obj, armature, falloff=3.0, max_bones=2):
    """依每個頂點自己的區域，找最近的骨頭線段算權重

    自動權重在這種一節一節分開的低面數身體上常常算壞，改用距離權重穩定又可預期。
    """
    regions = list(obj["regions"])
    bones = {b.name: (b.head_local.copy(), b.tail_local.copy()) for b in armature.data.bones}
    groups = {}
    for name in bones:
        groups[name] = obj.vertex_groups.new(name=name)

    for index, vertex in enumerate(obj.data.vertices):
        allowed = [n for n in regions[index].split(",") if n in bones] if regions[index] else None
        if not allowed:
            allowed = [n for n in bones if not n.startswith(("IK", "control", "knee", "elbow", "hand" + "IK", "heel"))]
        point = vertex.co
        scored = []
        for name in allowed:
            head, tail = bones[name]
            distance = _segment_distance(point, head, tail)
            scored.append((1.0 / (distance ** falloff + 1e-6), name))
        scored.sort(reverse=True)
        chosen = scored[:max_bones]
        total = sum(weight for weight, _ in chosen)
        for weight, name in chosen:
            groups[name].add([index], weight / total, "REPLACE")

    obj.parent = armature
    obj.matrix_parent_inverse = armature.matrix_world.inverted()
    modifier = obj.modifiers.new("Armature", "ARMATURE")
    modifier.object = armature
    return obj
