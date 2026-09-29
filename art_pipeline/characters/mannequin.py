"""灰白人體模型：現階段遊戲裡所有角色共用的身體

使用者給的線框參考圖長這樣，照這個做，不要自己加東西：

- Q 版基本體，T 姿勢，純灰色，沒有臉、沒有頭髮、沒有任何服裝
- 頭是一顆**大圓球**，光滑，佔全身高的四成到四成五，直接坐在肩上，脖子只露一小截
- 頭的兩側有小小的耳朵凸起，就是兩片圓角小耳朵，不做細節
- 軀幹小而簡單，胸到腰微收，再到臀，臀線有一個柔和的分界
- 手臂細，接近圓柱，往手腕微微變細。手掌是沒有手指的扁楔形連指手套，一片圓槳
- 腿短而粗，大腿粗、到腳踝變細，腳是簡單的楔形，不做腳趾
- 拓撲是乾淨的四邊面，每一節肢體都看得到一圈一圈的環，
  手肘、膝蓋、肩、臀、腰各有好幾圈，變形時才不會擠在一起

兩件事刻意和其他文件不一樣，不是做錯：

1. 頭是球。docs/美術風格指南.md 第 1.5 節寫的是「圓角方盒、前額接近平面」，
   那是**正式角色**的目標。人體模型照使用者給的線框圖做，所以是球。
   之後做正式角色時要回去照第 1.5 節那張表，不要拿這個人體模型當風格範本。
2. 手上沒有手指，骨架裡卻有手指關節。那是故意的：動作包只要有手指軌道就要找得到同名骨頭，
   沒有的話整個綁定會失敗。骨頭在、網格不動，這是正確的狀態。
"""

import math

from mathutils import Vector

import facesheet
import meshkit as mk
import proportions
from material import SLOT_INDEX

# 有穿衣服的部位。NPC 的身分色染在這個槽上，所以顏色讀起來是衣服不是皮膚
GREY = SLOT_INDEX["Neutral"]
SHORTS = SLOT_INDEX["NeutralDark"]
# 露出來的皮膚：頭、耳朵、脖子、手掌。這個槽永遠中性灰，不吃染色
SKIN = SLOT_INDEX["NeutralSkin"]
# 臉是一塊貼在頭前面的面片，UV 對到表情圖集的第 0 格。
# 表情靠遊戲端位移 UV 換格子，不換網格也不換材質，照 docs/角色系統規格.md
FACE = SLOT_INDEX["Face"]

# 每一段用幾個側面。數字夠大，細分之後才是圓的
LIMB_SIDES = 12
TORSO_SIDES = 16
HEAD_SEGMENTS = 24
HEAD_RINGS = 16

# 頭是球：直徑就是頭高，佔全身 45 個百分比
HEAD_HEIGHT = proportions.HEAD_HEIGHT
HEAD_RADIUS = HEAD_HEIGHT / 2.0
HEAD_CENTER_Z = proportions.HEAD_TOP - HEAD_RADIUS

# 骨頭分群。綁定時每個頂點只在自己那一群裡找最近的骨頭，手臂才不會被軀幹拉走
REGION_TORSO = ("Hips", "Spine", "Spine1", "Spine2")
REGION_NECK = ("Spine2", "Neck", "Head")
REGION_HEAD = ("Head",)
REGION_ARM = {"Left": ("LeftShoulder", "LeftArm", "LeftForeArm", "LeftForeArmTwist", "LeftHand"),
              "Right": ("RightShoulder", "RightArm", "RightForeArm", "RightForeArmTwist",
                        "RightHand")}
REGION_LEG = {"Left": ("Hips", "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase"),
              "Right": ("Hips", "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase")}
REGION_HIPS = ("Hips", "LeftUpLeg", "RightUpLeg")


def _face(builder):
    """臉：貼在頭球前面的一塊面片，UV 對到表情圖集的第 0 格

    為什麼是一塊面片不是把整顆球攤平：球的 UV 只是用來貼素色，
    另外做一塊小面片可以把整張圖集的解析度都花在五官上，
    也不用動到頭球本身的拓撲。面片往外推一點點才不會和頭球閃爍。
    """
    half_angle = math.radians(facesheet.FACE_HALF_ANGLE)
    top_polar = math.acos(1.0 - 2.0 * facesheet.FACE_TOP_V)
    bottom_polar = math.acos(1.0 - 2.0 * facesheet.FACE_BOTTOM_V)
    cols, rows = 14, 14
    # 圖集第 0 格的 UV 範圍。Blender 的 v 是從下往上，所以要翻過來
    cell_u = 1.0 / facesheet.COLUMNS
    cell_v = 1.0 / facesheet.ROWS
    grid = []
    for row in range(rows + 1):
        fv = row / rows
        polar = top_polar + (bottom_polar - top_polar) * fv
        line = []
        for col in range(cols + 1):
            fu = col / cols
            azimuth = (fu - 0.5) * 2.0 * half_angle
            # 往外推的距離要大於深度緩衝在遊戲鏡頭距離下的精度。
            # 只推千分之二也就是 0.7 公釐的話，32 公尺外會和頭球互相穿插，
            # 眼睛那一大塊深色會出現規則的網格狀雜點，看起來像貼圖被壓壞了
            radius = HEAD_RADIUS * 1.014
            line.append(Vector((math.sin(azimuth) * math.sin(polar) * radius,
                                -math.cos(azimuth) * math.sin(polar) * radius,
                                HEAD_CENTER_Z + math.cos(polar) * radius)))
        base = builder.add_verts(line, REGION_HEAD)
        grid.append([base + i for i in range(cols + 1)])
    for row in range(rows):
        for col in range(cols):
            u0, u1 = col / cols * cell_u, (col + 1) / cols * cell_u
            v0, v1 = 1.0 - row / rows * cell_v, 1.0 - (row + 1) / rows * cell_v
            # 繞向要讓面朝外，反了的話遊戲裡會被背面剔除，臉整個不見只剩一顆光頭
            builder.add_quad(grid[row + 1][col], grid[row + 1][col + 1],
                             grid[row][col + 1], grid[row][col], mat=FACE,
                             uvs=[(u0, v1), (u1, v1), (u1, v0), (u0, v0)])


def _head(builder):
    """大圓球加兩片小耳朵"""
    mk.sphere(builder, (0.0, 0.0, HEAD_CENTER_Z), HEAD_RADIUS,
              segments=HEAD_SEGMENTS, rings_count=HEAD_RINGS, mat=SKIN, region=REGION_HEAD)
    # 耳朵：貼在球的兩側，稍微往後一點，只是兩片圓角小凸起
    ear_z = HEAD_CENTER_Z - HEAD_RADIUS * 0.08
    for sign in (1, -1):
        mk.blob(builder, (sign * HEAD_RADIUS * 1.00, HEAD_RADIUS * 0.06, ear_z),
                (HEAD_RADIUS * 0.10, HEAD_RADIUS * 0.070, HEAD_RADIUS * 0.17),
                mat=SKIN, region=REGION_HEAD, segments=10, rings_count=6)


def _neck(builder, body):
    """只露一小截的脖子，把頭和肩接起來"""
    top = proportions.CHIN + 0.010
    sections = []
    for z, radius in ((body.shoulder_z - 0.004, body.neck_radius * 1.22),
                      (body.shoulder_z + 0.022, body.neck_radius),
                      (top, body.neck_radius * 0.98)):
        sections.append(mk.ring((0, 0, z), radius, radius * 0.94, TORSO_SIDES))
    mk.loft(builder, sections, mat=SKIN, region=REGION_NECK, cap_bottom=True, cap_top=True)


def _torso(builder, body):
    """胸到腰微收再到臀，臀線有一個柔和的分界

    每一段之間都多插一圈，細分之後腰和臀的轉折才留得住，也才有參考圖上那些環。
    """
    stops = [
        (body.crotch_z - 0.022, body.hip[0] * 0.60, body.hip[1] * 0.64),
        (body.crotch_z + 0.004, body.hip[0] * 0.90, body.hip[1] * 0.92),
        (body.crotch_z + 0.030, body.hip[0], body.hip[1]),
        (body.hip_z, body.hip[0], body.hip[1]),
        # 臀線的分界：上面一圈稍微收一點，剪影上就看得出腰臀的轉折
        (body.hip_z + 0.022, body.hip[0] * 0.96, body.hip[1] * 0.96),
        (body.waist_z, body.waist[0], body.waist[1]),
        ((body.waist_z + body.chest_z) / 2.0,
         (body.waist[0] + body.chest[0]) / 2.0, (body.waist[1] + body.chest[1]) / 2.0),
        (body.chest_z, body.chest[0], body.chest[1]),
        (body.shoulder_z - 0.016, body.shoulder[0], body.shoulder[1]),
        (body.shoulder_z, body.shoulder[0], body.shoulder[1]),
        (body.shoulder_z + 0.016, body.shoulder[0] * 0.74, body.shoulder[1] * 0.84),
    ]
    sections = [mk.ring((0, 0, z), rx, ry, TORSO_SIDES) for z, rx, ry in stops]
    mk.loft(builder, sections, mat=GREY, region=REGION_TORSO, cap_bottom=True, cap_top=True)


def _shorts(builder, body):
    """一條短褲。參考圖上沒有，但使用者說穿條內褲也行，
    有一圈深一點的灰，腿和軀幹的分界在動起來時看得比較清楚"""
    scale = 1.03
    stops = [(body.crotch_z + 0.004, body.hip[0] * scale * 0.94, body.hip[1] * scale * 0.94),
             (body.crotch_z + 0.030, body.hip[0] * scale, body.hip[1] * scale),
             (body.hip_z + 0.026, body.hip[0] * scale * 0.98, body.hip[1] * scale * 0.98)]
    sections = [mk.ring((0, 0, z), rx, ry, TORSO_SIDES) for z, rx, ry in stops]
    mk.loft(builder, sections, mat=SHORTS, region=REGION_HIPS, cap_bottom=False, cap_top=False)
    # 褲管：套在大腿最上面一小段，才看得出是短褲不是一條腰帶
    for sign in (1, -1):
        x = body.leg_x * sign
        big = body.leg_radius[0]
        leg_region = REGION_LEG["Left" if sign > 0 else "Right"]
        tube = [mk.ring((x, -0.004, body.crotch_z - 0.046), big * 1.05, big * 1.05, LIMB_SIDES),
                mk.ring((x, -0.004, body.crotch_z - 0.010), big * 1.06, big * 1.06, LIMB_SIDES),
                mk.ring((x, -0.004, body.crotch_z + 0.016), big * 1.07, big * 1.07, LIMB_SIDES)]
        mk.loft(builder, tube, mat=SHORTS, region=leg_region, cap_bottom=False, cap_top=False)


def _arm(builder, body, side, sign):
    """細圓柱手臂，往手腕微微收，末端接一片扁扁的連指手套

    T 姿勢：手臂沿著 X 軸直直伸出去。肩、肘、腕各多插一圈當變形用的環。
    """
    region = REGION_ARM[side]
    x0 = body.arm_x * sign
    elbow = x0 + body.upperarm * sign
    wrist = x0 + (body.upperarm + body.lowerarm) * sign
    big, small = body.arm_radius
    path, radii = [], []
    for fraction, radius in ((0.00, big * 1.10), (0.10, big), (0.46, big * 0.94),
                             (0.54, big * 0.92), (0.90, small), (1.00, small * 0.94)):
        along = x0 + (wrist - x0) * fraction
        path.append(Vector((along, 0.0, body.arm_z)))
        radii.append(radius)
    mk.sweep(builder, path, radii, LIMB_SIDES, mat=GREY, region=region,
             up=Vector((0, 0, 1)), cap_start=True, cap_end=False)
    # 連指手套：一片扁扁的圓槳，從手腕接出去，前端收圓，不做手指
    hand_len = body.hand * 0.86
    centre = wrist + hand_len * 0.80 * sign
    mk.blob(builder, (centre, 0.0, body.arm_z),
            (hand_len, body.hand_radius * 0.96, body.hand_radius * 0.46),
            mat=SKIN, region=region, segments=12, rings_count=8)
    _ = elbow


def _leg(builder, body, side, sign):
    """短粗的腿，大腿粗到腳踝變細，腳是簡單的楔形"""
    region = REGION_LEG[side]
    x = body.leg_x * sign
    knee_z = body.crotch_z - body.upperleg
    ankle_z = knee_z - body.lowerleg
    big, small = body.leg_radius
    path, radii = [], []
    for z, radius in ((body.crotch_z + 0.018, big * 1.02), (body.crotch_z - 0.018, big),
                      (knee_z + 0.026, big * 0.90), (knee_z, big * 0.86),
                      (knee_z - 0.026, big * 0.84), (ankle_z + 0.030, small * 0.82),
                      (ankle_z, small * 0.76)):
        path.append(Vector((x, -0.004, z)))
        radii.append(radius)
    mk.sweep(builder, path, radii, LIMB_SIDES, mat=GREY, region=region,
             up=Vector((0, 1, 0)), cap_start=True, cap_end=True)
    # 楔形的腳：腳底比腳踝寬也比較往前，前端收圓，不分腳趾。
    # 每一圈是一個往前偏移的橢圓，由下往上疊，接到小腿末端
    sole_y = -body.foot_forward * 0.34
    stops = [
        (0.014, small * 0.92, body.foot_forward * 0.74, sole_y),
        (0.040, small * 0.94, body.foot_forward * 0.76, sole_y),
        (0.066, small * 0.86, body.foot_forward * 0.60, sole_y * 0.70),
        (ankle_z + 0.034, small * 0.74, small * 0.80, -0.006),
    ]
    sections = [mk.ring((x, cy, z), rx, ry, LIMB_SIDES) for z, rx, ry, cy in stops]
    mk.loft(builder, sections, mat=GREY, region=region, cap_bottom=True, cap_top=True)


def round_head(obj):
    """細分之後把頭頂那一圈拉回真正的球面

    Catmull-Clark 會把極點那一圈的三角扇往內收，收的量和球面其他地方不一樣，
    頭頂就多出一塊一兩公釐的淺凹。卡通材質的明暗是硬邊的，那塊淺凹在遊戲裡
    會讀成頭頂有一個深色的圓斑。把落在球面附近的點推回正確半徑就沒事了，
    耳朵凸出去的點超過門檻所以不受影響。
    """
    # 臉那塊面片要跳過。它是刻意推到球面外面一點點的，
    # 被這裡拉回球面就會和頭球共面，遠處看整片眼睛會出現規則的網狀雜點
    face_verts = set()
    for polygon in obj.data.polygons:
        if polygon.material_index == FACE:
            face_verts.update(polygon.vertices)
    centre = Vector((0.0, 0.0, HEAD_CENTER_Z))
    for index, vertex in enumerate(obj.data.vertices):
        if index in face_verts:
            continue
        offset = vertex.co - centre
        distance = offset.length
        if distance < 1e-6:
            continue
        ratio = distance / HEAD_RADIUS
        if 0.90 <= ratio <= 1.03:
            vertex.co = centre + offset * (HEAD_RADIUS / distance)
    obj.data.update()
    return obj


def build(materials, gender="neutral", with_shorts=True, name="mannequin"):
    """做出整具人體模型，原點在腳底"""
    body = proportions.BODIES[gender]
    builder = mk.Builder()
    _head(builder)
    _face(builder)
    _neck(builder, body)
    _torso(builder, body)
    if with_shorts:
        _shorts(builder, body)
    for side, sign in (("Left", 1), ("Right", -1)):
        _arm(builder, body, side, sign)
        _leg(builder, body, side, sign)
    obj = builder.to_object(name, materials)
    mk.shade(obj)
    return obj
