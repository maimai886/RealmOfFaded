"""角色的身體尺寸表，整張由 rigspec.py 的比例參數算出來

2026-09-18 第五版。上一版是一堆寫死的絕對尺寸，改頭身比要有人把每一個數字重推一次。
使用者的原話是「你應該要有一套方便調骨架的算法」，所以這一版把數字全部換成算式，
輸入是 `rigspec.STANDARD` 那十八個比例參數。改頭身比就只改 `head_ratio` 一個數字。

比例參數本身量自使用者 2026-09-18 拍板的初心者設定圖，
量法和每一項從圖上哪裡量，見 `rigspec.RigSpec.FIELDS` 和 docs/美術風格指南.md 第 2.1 節。

全身高度 1.57 公尺不變，那是世界契約，遊戲裡的碰撞、鏡頭、位置都照它算。
座標約定：+X 是角色的左手邊，-Y 是角色面向的方向，+Z 是上，原點在腳底。
"""

import rigspec

STANDARD = rigspec.STANDARD

HEIGHT = STANDARD.height_m
HEAD_TOP = HEIGHT
# 注意這一個是「頭佔全高的比例」不是頭身比，headshape.py 和匯出的骨架 json 都認這個意思。
# 頭身比在 rigspec 那邊叫 head_ratio，兩者互為倒數
HEAD_RATIO = 1.0 / STANDARD.head_ratio
HEAD_HEIGHT = STANDARD.head_height
CHIN = STANDARD.chin_z
HEAD_WIDTH = STANDARD.head_width
HEAD_RADIUS = HEAD_WIDTH / 2.0
HEAD_CENTER_Z = STANDARD.head_centre_z
NECK_Z = STANDARD.neck_z

# 女生相對男生的橫向差異，值是乘在男生那一份上面的倍率。
# 這一張表是從 2026-09-16 那版男女兩組絕對尺寸反推的，反推之後男女的差別
# 就只剩這幾個倍率，身高和頭身比一改它們也不用跟著動
FEMALE_TORSO = {"shoulder": 0.92, "chest": 0.925, "waist": 0.837, "hip": 1.023}
FEMALE_ARM_ROOT = 0.949
FEMALE_LEG_ROOT = 0.955
FEMALE_ARM_RADIUS = 0.867
FEMALE_LEG_RADIUS = 0.911
FEMALE_NECK_RADIUS = 0.871

# 手掌比手臂粗這麼多倍。楔形的手靠手腕那端和手臂一樣粗，往外收成一個扁扁的尖端
HAND_PER_ARM_RADIUS = 1.20
# 脖子多粗，以肩半寬為單位
NECK_PER_SHOULDER = 0.276
# 靴子多高，以腿長為單位
FOOT_PER_LEG = 0.110

# 骨頭名稱沿用 KayKit，既有的 76 個動作才能直接套上來。
# 另外加四根掛裝備用的骨頭，名稱照 docs/角色系統規格.md 固定成 hand_r、hand_l、back、body，
# 頭飾直接掛在原本就有的 head 上
SOCKETS = ["hand_r", "hand_l", "back", "body"]
BONE_ORDER = ["root", "hips", "spine", "chest", "head",
              "upperarm.l", "lowerarm.l", "wrist.l", "hand.l", "handslot.l",
              "upperarm.r", "lowerarm.r", "wrist.r", "hand.r", "handslot.r",
              "upperleg.l", "lowerleg.l", "foot.l", "toes.l",
              "upperleg.r", "lowerleg.r", "foot.r", "toes.r"] + SOCKETS


class Body:
    """一種性別的身體尺寸，寬度全部是半寬，第二個數字是前後半厚

    每一個欄位都是從 spec 算出來的，沒有一個是寫死的絕對尺寸。
    """

    def __init__(self, gender, spec=None):
        self.gender = gender
        self.spec = spec or STANDARD
        spec = self.spec
        female = gender == "female"

        def torso(name, ratio):
            half = spec.shoulder_half * ratio
            if female:
                half *= FEMALE_TORSO[name]
            # 前後半厚和半寬同一個倍率。上一版每一段的厚寬比略有不同，
            # 0.88 到 0.94，換算成長度差不到 0.012 公尺，不到一個像素，收成一個數字
            return (half, half * spec.torso_depth_per_width)

        self.shoulder = torso("shoulder", 1.0)
        self.chest = torso("chest", spec.chest_per_shoulder)
        self.waist = torso("waist", spec.waist_per_shoulder)
        self.hip = torso("hip", spec.hip_per_shoulder)

        self.shoulder_z = spec.shoulder_z
        self.chest_z = spec.chest_z
        self.waist_z = spec.waist_z
        self.hip_z = spec.hip_z
        self.crotch_z = spec.crotch_z

        # 手臂。肩關節要貼著軀幹表面，不然手臂整段埋在身體裡，露出來的只剩一小截
        self.arm_x = spec.arm_x * (FEMALE_ARM_ROOT if female else 1.0)
        self.arm_z = spec.arm_z
        self.upperarm = spec.upperarm
        self.lowerarm = spec.lowerarm
        self.hand = spec.hand_length
        arm_radius = spec.arm_radius * (FEMALE_ARM_RADIUS if female else 1.0)
        self.arm_radius = (arm_radius, arm_radius * spec.torso_depth_per_width)
        self.hand_radius = arm_radius * HAND_PER_ARM_RADIUS

        # 腿。兩條腿要站開，不然加粗之後在中線會黏成一塊
        self.leg_x = spec.leg_x * (FEMALE_LEG_ROOT if female else 1.0)
        self.upperleg = spec.upperleg
        self.lowerleg = spec.lowerleg
        self.foot_z = spec.leg_length * FOOT_PER_LEG
        # 靴口在腿長的下三分之一，腿長就是胯高
        self.boot_top = self.crotch_z / 3.0
        leg_radius = spec.leg_radius * (FEMALE_LEG_RADIUS if female else 1.0)
        self.leg_radius = (leg_radius, leg_radius * spec.torso_depth_per_width)
        self.foot_forward = spec.foot_forward

        # 脖子。四頭身看得到脖子了，但它還是很短，只要讓頭和肩膀之間不破洞就好
        self.neck_radius = (spec.shoulder_half * NECK_PER_SHOULDER
                            * (FEMALE_NECK_RADIUS if female else 1.0))

    def joints(self):
        """骨頭名稱對到骨頭起點的世界座標

        這一份是 KayKit 命名的簡化骨架，正式角色用的是 humanoid.joints，
        兩邊的位置算式一樣，差別只在骨頭多寡和名字。
        """
        out = {}
        reach = self.upperarm + self.lowerarm
        for side, sign in (("l", 1), ("r", -1)):
            x = self.arm_x * sign
            out.update({
                "upperarm." + side: (x, 0.0, self.arm_z),
                "lowerarm." + side: (x + self.upperarm * sign, 0.0, self.arm_z),
                "wrist." + side: (x + reach * sign, 0.0, self.arm_z),
                "hand." + side: (x + (reach + self.hand * 0.19) * sign, 0.0, self.arm_z),
                "handslot." + side: (x + (reach + self.hand * 0.52) * sign, 0.0,
                                     self.arm_z - self.hand * 0.35),
                "upperleg." + side: (self.leg_x * sign, 0.0, self.crotch_z),
                "lowerleg." + side: (self.leg_x * sign, -0.005, self.crotch_z - self.upperleg),
                "foot." + side: (self.leg_x * sign, 0.010,
                                 self.crotch_z - self.upperleg - self.lowerleg),
                "toes." + side: (self.leg_x * sign, -self.foot_forward, 0.014),
            })
        out.update({
            "root": (0.0, 0.0, 0.0),
            "hips": (0.0, 0.0, self.crotch_z * 1.042),
            "spine": (0.0, 0.0, self.waist_z),
            "chest": (0.0, 0.0, self.chest_z),
            "head": (0.0, 0.0, NECK_Z),
            # 裝備掛點。武器掛點和 handslot 同位置但名字照規格書，資料只認這五個名字
            "hand_r": (-(self.arm_x + reach + self.hand * 0.52), 0.0,
                       self.arm_z - self.hand * 0.35),
            # 左手掛點比右手再往外往前推一點：弓是橫著拿的，長度和角色差不多，
            # 掛在手心正中央的話弓身會直接穿過軀幹，畫面上是一排雜點
            "hand_l": (self.arm_x + reach + self.hand * 0.95, -self.hand * 0.54,
                       self.arm_z - self.hand * 0.35),
            "back": (0.0, self.chest[1] * 0.92, self.chest_z + self.chest[0] * 0.28),
            "body": (0.0, 0.0, self.chest_z),
        })
        return out


MALE = Body("male")
FEMALE = Body("female")
# 灰白人體模型用的中性身體。現階段遊戲裡不分男女，全部用這一副
NEUTRAL = Body("neutral")
BODIES = {"male": MALE, "female": FEMALE, "neutral": NEUTRAL}
