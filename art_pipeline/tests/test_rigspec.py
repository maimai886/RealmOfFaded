"""比例參數產生器的測試

這一組守的是「改一個參數，骨架整副跟著對」。
以前骨架是一組寫死的座標，改頭身比要有人手推每一根骨頭，
漏掉一根不會報錯，只會讓武器握在手掌外面幾公分的地方。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHARACTERS = os.path.join(os.path.dirname(HERE), "characters_v3")
if CHARACTERS not in sys.path:
    sys.path.insert(0, CHARACTERS)

import rigspec  # noqa: E402

# 骨架契約：六十二根骨頭，五個掛點，名字資料那邊認
SOCKETS = ["hand_r", "hand_l", "head", "back", "body"]


def test_標準骨架有六十二根骨頭和五個掛點():
    joints = rigspec.STANDARD.joints()
    assert len(joints) == 62, len(joints)
    for name in SOCKETS:
        assert name in joints, name


def test_改頭身比不會改角色的身高():
    for ratio in (2.2, 3.0, 4.07, 5.5):
        spec = rigspec.STANDARD.replace(head_ratio=ratio)
        assert abs(spec.height_m - 1.57) < 1e-9
        assert abs(spec.head_height * ratio - spec.height_m) < 1e-9
        assert abs(spec.chin_z + spec.head_height - spec.height_m) < 1e-9


def test_頭身比變大頭就變小身體就變長():
    small_head = rigspec.STANDARD.replace(head_ratio=6.0)
    big_head = rigspec.STANDARD.replace(head_ratio=2.2)
    assert small_head.head_height < big_head.head_height
    assert small_head.chin_z > big_head.chin_z
    assert small_head.crotch_z == big_head.crotch_z


def test_replace_不會動到原本那一份():
    before = rigspec.STANDARD.head_ratio
    other = rigspec.STANDARD.replace(head_ratio=3.0)
    assert other.head_ratio == 3.0
    assert rigspec.STANDARD.head_ratio == before


def test_不認得的參數會當場丟例外():
    try:
        rigspec.RigSpec(head_ratio=4.0, 肩膀=1.0)
    except ValueError:
        return
    raise AssertionError("寫錯參數名應該要丟例外，不能安靜地忽略")


def test_頭身比不能小於一():
    try:
        rigspec.RigSpec(head_ratio=0.5)
    except ValueError:
        return
    raise AssertionError("頭比人還高應該要丟例外")


def test_每一根骨頭都在地板和頭頂之間():
    for ratio in (2.2, 4.07, 6.0):
        spec = rigspec.STANDARD.replace(head_ratio=ratio)
        for name, point in spec.joints().items():
            assert -0.01 <= point[2] <= spec.height_m + 0.01, (ratio, name, point)


def test_左右兩邊完全對稱():
    joints = rigspec.STANDARD.joints()
    for name, point in joints.items():
        if not name.startswith("Left"):
            continue
        mirror = joints["Right" + name[4:]]
        assert abs(point[0] + mirror[0]) < 1e-9, name
        assert abs(point[1] - mirror[1]) < 1e-9, name
        assert abs(point[2] - mirror[2]) < 1e-9, name


def test_握持掛點落在手腕和指尖之間():
    """這一條就是上一版踩到的坑：掛點落在前臂裡面，十四具都握不到武器"""
    for ratio in (2.2, 4.07, 6.0):
        spec = rigspec.STANDARD.replace(head_ratio=ratio)
        joints = spec.joints()
        wrist = abs(joints["RightHand"][0])
        tip = spec.mesh_targets()["arm_tip"]
        socket = abs(joints["hand_r"][0])
        assert wrist < socket < tip, (ratio, wrist, socket, tip)


def test_網格目標和骨架是同一組參數算出來的():
    spec = rigspec.STANDARD
    targets = spec.mesh_targets()
    assert abs(targets["arm_tip"] - (spec.arm_x + spec.arm_span)) < 1e-9
    assert abs(targets["arm_z"] - spec.arm_z) < 1e-9
    # 腳踝的半寬要包含靴子的厚度，不然腿骨會落在靴子邊上
    assert targets["leg_x"] > spec.leg_x


def test_手臂三段加起來等於參數說的長度():
    spec = rigspec.STANDARD
    total = spec.upperarm + spec.lowerarm + spec.hand_length
    assert abs(total - spec.arm_span) < 1e-9


def test_腿三段加起來等於胯高():
    spec = rigspec.STANDARD
    ankle = spec.leg_length - spec.upperleg - spec.lowerleg
    assert ankle > 0.0
    assert abs(spec.upperleg + spec.lowerleg + ankle - spec.crotch_z) < 1e-9


def test_參數表每一項都寫了從哪裡量():
    for name, _default, meaning, source in rigspec.RigSpec.FIELDS:
        assert meaning.strip(), name
        assert source.strip(), name
        assert "\n" not in source, name
