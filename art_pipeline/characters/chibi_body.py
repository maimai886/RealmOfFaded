# -*- coding: utf-8 -*-
"""用幾何體拼的乾淨素體算八方向、八動作的身體圖集。在 Blender 裡跑。

生成的 3D 網格算出來的人物是垃圾，決策紀錄 2026-09-23 有寫。這條用的是 characters 那具幾何人偶：
球、管子、環拼出來的乾淨網格，比例照定裝圖量出來的 cbuild.CARD_SPEC，顏色是素體的膚色和白衣白褲，
頭藏掉由使用者畫的頭圖層蓋（headsheet.py），輪廓用 Freestyle 描邊。全部本機、不花錢、每一格都是同一個模型算的。

用法：
  blender -b --factory-startup --python-exit-code 1 -P art_pipeline/characters/chibi_body.py -- <名稱> [--gender male] [--job novice] [--preview] [--candidate] [--directions 8] [--no-head-layer] [--no-ink]
      [--gear 路徑.glb@掛點[*倍率]] [--layer 名稱=路徑.glb@掛點[*倍率]]
--gear 把網格掛在掛點上和身體一起算進同一張圖，例如鎧甲和武器；--layer 另外算成一張圖層圖集，交給引擎照前後疊，例如頭盔。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cbuild  # noqa: E402  它會把 characters、monsters、common 加進路徑

import bpy  # noqa: E402

import blenv  # noqa: E402
import dodge_anim  # noqa: E402
import mannequin  # noqa: E402
import material  # noqa: E402
import meshkit  # noqa: E402
import proportions  # noqa: E402
import rig_humanoid  # noqa: E402
import rigspec  # noqa: E402

# 素體的顏色，量自使用者的正面圖：膚色、白 T 恤、白短褲。褲子比衣服偏冷一點，交界才看得出來
COLORS = {"NeutralSkin": "#f4e2dd", "Neutral": "#f3e9e6", "NeutralDark": "#e9ecf2", "Face": "#f4e2dd"}
SUBDIVISION = 1


def _srgb(hex_color):
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return tuple(((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92 for c in (r, g, b)) + (1.0,)


def _apply_spec(spec):
    """人偶讀的是 proportions 和 mannequin 的模組常數，換成定裝圖那份比例"""
    proportions.HEIGHT = spec.height_m
    proportions.HEAD_TOP = spec.height_m
    proportions.HEAD_RATIO = 1.0 / spec.head_ratio
    proportions.HEAD_HEIGHT = spec.head_height
    proportions.CHIN = spec.chin_z
    proportions.HEAD_WIDTH = spec.head_width
    proportions.HEAD_RADIUS = spec.head_width / 2.0
    proportions.HEAD_CENTER_Z = spec.head_centre_z
    proportions.NECK_Z = spec.neck_z
    mannequin.HEAD_HEIGHT = spec.head_height
    mannequin.HEAD_RADIUS = spec.head_height / 2.0
    mannequin.HEAD_CENTER_Z = spec.height_m - spec.head_height / 2.0


def _paint(materials):
    """材質槽照 SLOTS 的位置換成素體的顏色，名字會被 Blender 加 .001 所以不用名字認"""
    painted = []
    for key, color in COLORS.items():
        mat = materials[material.SLOT_INDEX[key]]
        for node in mat.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                for link in list(node.inputs["Base Color"].links):
                    mat.node_tree.links.remove(link)
                node.inputs["Base Color"].default_value = _srgb(color)
                painted.append(mat.name)
    cbuild._log("上色：%s" % "、".join(painted))


def _build_mesh(materials):
    """照 mannequin.build 的順序拼，但手臂和腿用膚色：素體是短袖短褲赤腳，v3 人偶原本是長袖長褲加靴子"""
    mk = mannequin.mk
    builder = mk.Builder()
    mannequin._head(builder)
    mannequin._face(builder)
    body = proportions.BODIES["card"]
    mannequin._neck(builder, body)
    mannequin._torso(builder, body)
    mannequin._shorts(builder, body)
    grey = mannequin.GREY
    mannequin.GREY = mannequin.SKIN
    try:
        for side, sign in (("Left", 1), ("Right", -1)):
            mannequin._arm(builder, body, side, sign)
            mannequin._leg(builder, body, side, sign)
    finally:
        mannequin.GREY = grey
    for side, sign in (("Left", 1), ("Right", -1)):
        _sleeve(builder, body, side, sign, grey)
    obj = builder.to_object("mannequin", materials)
    mk.shade(obj)
    # 管子掃出來的手臂和腿法線朝內，開了背面剔除會整段消失只剩描邊殼，三段明暗也會算反；統一朝外
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return obj


def _sleeve(builder, body, side, sign, mat):
    """短袖：套在上臂前 45% 的一截管子，比手臂粗一點，袖口開著；T 姿勢的手臂沿 X 軸伸出去"""
    from mathutils import Vector
    mk = mannequin.mk
    x0 = body.arm_x * sign
    end = x0 + body.upperarm * 0.45 * sign
    big = body.arm_radius[0]
    path = [Vector((x0, 0.0, body.arm_z)), Vector((x0 + (end - x0) * 0.85, 0.0, body.arm_z)), Vector((end, 0.0, body.arm_z))]
    radii = [big * 1.22, big * 1.16, big * 1.14]
    mk.sweep(builder, path, radii, mannequin.LIMB_SIDES, mat=mat, region=mannequin.REGION_ARM[side],
             up=Vector((0, 0, 1)), cap_start=True, cap_end=False)


def build(gender):
    """做出人偶和骨架，回傳 (骨架, [網格])"""
    spec = rigspec.RigSpec(**cbuild.CARD_SPEC)
    _apply_spec(spec)
    body_shape = proportions.Body(gender, spec)
    proportions.BODIES["card"] = body_shape
    blenv.clear_scene()
    materials = material.build("novice")
    armature = rig_humanoid.build(gender, body_shape)
    dodge_anim.build_all(armature)
    rig_humanoid.rest_pose(armature)
    _paint(materials)
    obj = _build_mesh(materials)
    meshkit.bind(obj, armature)
    with blenv.ui():
        meshkit.subdivide_apply(obj, SUBDIVISION)
    mannequin.round_head(obj)
    cbuild._log("幾何人偶：%d 個頂點，%.2f 頭身" % (len(obj.data.vertices), spec.head_ratio))
    return armature, [obj]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        raise SystemExit(__doc__)
    name = argv[0]
    options = {"--gender": "male", "--job": "novice", "--directions": "8"}
    flags = set()
    gear, layers = [], []
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--gear" and index + 1 < len(argv):
            gear.append(cbuild._parse_layer("gear%d=%s" % (len(gear), argv[index + 1])))
            index += 2
        elif token == "--layer" and index + 1 < len(argv):
            layers.append(cbuild._parse_layer(argv[index + 1]))
            index += 2
        elif token in options and index + 1 < len(argv):
            options[token] = argv[index + 1]
            index += 2
        elif token in ("--preview", "--candidate", "--no-head-layer", "--no-ink"):
            flags.add(token)
            index += 1
        else:
            raise SystemExit("看不懂的參數 " + token)
    directions = cbuild.DIRECTIONS_5 if options["--directions"] == "5" else cbuild.DIRECTIONS_8
    armature, meshes = build(options["--gender"])
    for spec in gear:
        meshes.append(cbuild._attach_layer(armature, spec))
    cbuild.render(name, armature, meshes, directions, job=options["--job"], preview="--preview" in flags,
                  candidate="--candidate" in flags, layers=layers, head_layer="--no-head-layer" not in flags,
                  ink="--no-ink" not in flags)


if __name__ == "__main__":
    main()
