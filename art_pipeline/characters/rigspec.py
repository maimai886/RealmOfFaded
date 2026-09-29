"""比例參數 → 完整骨架的產生器

為什麼要有這一支：以前骨架是一組寫死的關節座標，換一個頭身比就要有人重新手推
每一根骨頭的位置。使用者的原話是「你應該要有一套方便調骨架的算法」。
現在改頭身比只要改 `head_ratio` 一個數字，六十二根骨頭和五個掛點全部自動重算。

整條路是：

    設定圖 → designsheet 量測 → RigSpec → 這一支 → 骨架和網格正規化目標

**參數只放看得懂、而且從一張設定圖上量得出來的東西**，不放內部的中間值。
每一個參數從圖上哪裡量，寫在下面 `FIELDS` 的第四欄，`table()` 會把整張表印出來。

## 這一支同時解掉「骨架對不上網格」那個坑

上一版刻意不用解析式骨架的數字，理由是 Meshy 的網格手臂比設計稿長 0.076 公尺，
照設計稿釘的話握持掛點會落在前臂裡面，十四具都握不到武器。
當時的解法是反過來把骨架搬去遷就網格，代價是骨架的形狀不再由參數決定，
而是由「這批網格剛好長什麼樣」決定，換一批網格就要重新量一次。

現在反過來：**同一組參數同時決定骨架和網格該被正規化成什麼樣子**。
`mesh_targets()` 回傳的四個數字就是網格被縮到位之後該量到的值，
`rehome_meshy` 會把每一具網格扭到那個形狀再綁骨。
手掌落在哪裡是參數說了算，所以握持掛點一定在手裡面，不是碰運氣對上的。
"""

# 骨架的座標約定和 proportions.py 一樣：+X 是角色的左手邊，-Y 是角色面向的方向，+Z 是上。
# 原點在腳底板。

# 軀幹各段高度落在「胯部到肩線」之間的哪個位置。
# 這四個數字是從 2026-09-16 那版比例表反推的，當時是一組絕對高度，
# 換算成相對位置之後就不會再跟著身高和頭身比跑掉。
# 不把它們放進參數表，是因為設定圖上量不到胸線和腰線在哪一格，
# 放進去只會變成一個沒有人知道怎麼來的數字
CHEST_BAND = 0.656
WAIST_BAND = 0.313
HIP_BAND = 0.137
# 肩關節在同一段裡的位置。比肩線低一點點，手臂是掛在肩膀下面的
ARM_BAND = 0.885
# 肩關節離身體中線多遠，以肩半寬為單位。關節要貼著軀幹表面，
# 再往內就整條手臂埋在身體裡，露出來的只剩一小截
ARM_ROOT_PER_SHOULDER = 0.78
# 頭骨接點壓在下巴下面這麼多個頭高。這個頭身比看得到脖子，但脖子很短
NECK_DROP_PER_HEAD = 0.016
# 頭心在下巴往上這麼多個頭高
HEAD_CENTRE_PER_HEAD = 0.52
# 腳踝到地板那一截佔腿長的比例，也就是靴子有多高。
# 和大腿小腿的比例不同，這一段從設定圖上量不到，靴子外面看不出腳踝在哪
ANKLE_PER_LEG = 0.209


class RigSpec:
    """一組角色比例。改一個欄位，骨架和網格正規化目標一起跟著變

    每一個欄位都是無單位的比值，只有 `height_m` 有單位。
    這樣同一組參數換一個身高照樣成立，身高是世界契約不是美術比例。
    """

    # 欄位名、預設值、意思、從設定圖哪裡量
    FIELDS = [
        ("height_m", 1.57, "角色全高，公尺",
         "不從圖上量。這是世界契約，碰撞和鏡頭都照它算"),
        ("head_ratio", 4.07, "全高 ÷ 頭高，也就是幾頭身",
         "髮際輪廓最高點到下巴 vs 到鞋底"),
        ("head_width_per_head", 1.096, "頭寬 ÷ 頭高",
         "頭那一段最寬的一列，量之前先做一次開運算磨掉髮尖"),
        ("shoulder_per_head_width", 1.081, "肩寬 ÷ 頭寬",
         "脖子往下 0.45 個頭高之內最寬的一列"),
        ("chest_per_shoulder", 0.93, "胸寬 ÷ 肩寬",
         "腋下那一圈的寬度。正背兩視圖分不出胸和肩，沿用上一份"),
        ("waist_per_shoulder", 0.86, "腰寬 ÷ 肩寬",
         "腋下到胯部之間最窄的一圈。被下襬蓋住，沿用上一份"),
        ("hip_per_shoulder", 0.88, "臀寬 ÷ 肩寬",
         "胯部往上一點點那一圈。被下襬蓋住，沿用上一份"),
        ("torso_depth_per_width", 0.88, "軀幹前後厚 ÷ 軀幹寬",
         "側視圖。只有正面背面的設定圖量不到，沿用上一份"),
        ("shoulder_per_height", 0.684, "肩線高 ÷ 全高",
         "脖子以下第一列寬到肩寬九成的那一列"),
        ("crotch_per_height", 0.369, "胯高 ÷ 全高",
         "兩條腿分得開的最高那一列；這張圖被下襬蓋住只量到 0.294，照下巴以下的 0.49 推回去"),
        ("arm_span_per_height", 0.255, "肩關節到指尖 ÷ 全高",
         "手垂著，從肩關節那一列量到剪影收窄的那一列"),
        ("forearm_share", 0.481, "前臂 ÷ 上臂加前臂",
         "手肘那一格。這張圖手臂貼著身體分不出來，沿用上一份"),
        ("hand_share", 0.231, "手掌長 ÷ 肩關節到指尖",
         "護腕到手末端。這張圖分不出來，沿用上一份"),
        ("thigh_share", 0.430, "大腿 ÷ 胯部到腳底",
         "膝蓋那一格。被褲子蓋住，沿用上一份"),
        ("stance_per_head_width", 0.654, "兩腳中心距 ÷ 頭寬",
         "小腿那一段兩條腿的中心距，取中位數"),
        ("leg_width_per_head_width", 0.480, "單腿寬 ÷ 頭寬",
         "小腿那一段單邊的寬度，取中位數"),
        ("arm_width_per_head_width", 0.330, "手臂寬 ÷ 頭寬",
         "前臂最細的一段。這張圖手臂貼著身體分不出來，沿用風格指南第 2.1 節量到的值"),
        ("foot_forward_per_height", 0.074, "腳尖往前伸 ÷ 全高",
         "側視圖。沒有側視圖就沿用上一份"),
    ]

    def __init__(self, **values):
        unknown = set(values) - {name for name, _, _, _ in self.FIELDS}
        if unknown:
            raise ValueError("不認得的比例參數：%s" % "、".join(sorted(unknown)))
        for name, default, _, _ in self.FIELDS:
            setattr(self, name, float(values.get(name, default)))
        if self.head_ratio <= 1.0:
            raise ValueError("頭身比要大於 1，收到 %.3f" % self.head_ratio)

    def replace(self, **values):
        """換掉幾個參數做出一份新的，原本那一份不動"""
        current = {name: getattr(self, name) for name, _, _, _ in self.FIELDS}
        current.update(values)
        return RigSpec(**current)

    # 下面這些是從參數算出來的尺寸，單位公尺。不要把它們寫回參數表，
    # 它們是結果不是輸入

    @property
    def head_height(self):
        return self.height_m / self.head_ratio

    @property
    def chin_z(self):
        return self.height_m - self.head_height

    @property
    def head_width(self):
        return self.head_height * self.head_width_per_head

    @property
    def head_centre_z(self):
        return self.chin_z + self.head_height * HEAD_CENTRE_PER_HEAD

    @property
    def neck_z(self):
        return self.chin_z - self.head_height * NECK_DROP_PER_HEAD

    @property
    def shoulder_half(self):
        return self.head_width * self.shoulder_per_head_width / 2.0

    @property
    def shoulder_z(self):
        return self.height_m * self.shoulder_per_height

    @property
    def crotch_z(self):
        return self.height_m * self.crotch_per_height

    def _band(self, fraction):
        """胯部到肩線之間某個位置的高度"""
        return self.crotch_z + (self.shoulder_z - self.crotch_z) * fraction

    @property
    def chest_z(self):
        return self._band(CHEST_BAND)

    @property
    def waist_z(self):
        return self._band(WAIST_BAND)

    @property
    def hip_z(self):
        return self._band(HIP_BAND)

    @property
    def arm_z(self):
        return self._band(ARM_BAND)

    @property
    def arm_x(self):
        return self.shoulder_half * ARM_ROOT_PER_SHOULDER

    @property
    def arm_span(self):
        """肩關節到指尖的長度"""
        return self.height_m * self.arm_span_per_height

    @property
    def hand_length(self):
        return self.arm_span * self.hand_share

    @property
    def upperarm(self):
        return (self.arm_span - self.hand_length) * (1.0 - self.forearm_share)

    @property
    def lowerarm(self):
        return (self.arm_span - self.hand_length) * self.forearm_share

    @property
    def leg_length(self):
        return self.crotch_z

    @property
    def upperleg(self):
        return self.leg_length * self.thigh_share

    @property
    def lowerleg(self):
        """小腿。腳踝到地板那一截是靴子，不算在小腿裡"""
        return self.leg_length * (1.0 - self.thigh_share - ANKLE_PER_LEG)

    @property
    def leg_x(self):
        """腿骨離中線多遠，也就是站距的一半"""
        return self.head_width * self.stance_per_head_width / 2.0

    @property
    def leg_radius(self):
        return self.head_width * self.leg_width_per_head_width / 2.0

    @property
    def arm_radius(self):
        return self.head_width * self.arm_width_per_head_width / 2.0

    @property
    def foot_forward(self):
        return self.height_m * self.foot_forward_per_height

    def mesh_targets(self):
        """網格被正規化之後應該量到的四個數字，單位公尺

        這四項和 `rehome_meshy.measure_mesh` 量的是同一組東西，
        定義也一樣：指尖最外緣、手臂管心的高度、腋下那一段最窄的半寬、腳踝的半寬。

        有了這一份，網格就是被扭到骨架這邊來，而不是骨架被搬去遷就網格。
        握持掛點會落在手裡面是算出來的，不是碰運氣對上的
        """
        return {
            "arm_tip": self.arm_x + self.arm_span,
            "arm_z": self.arm_z,
            # 量到的那一圈落在胸線和腰線之間，比肩膀窄一點，所以用胸寬不用肩寬
            "torso_half": self.shoulder_half * self.chest_per_shoulder,
            "leg_x": self.leg_x + self.leg_radius,
        }

    def joints(self):
        """六十二根骨頭和五個掛點的世界座標

        實際算式在 humanoid.joints 裡，那一份同時被灰白人體模型和正式角色用。
        這裡只負責把參數攤成它要的身體尺寸
        """
        import humanoid
        return humanoid.joints(self.body())

    def body(self, gender="neutral"):
        """做出一份 proportions.Body，欄位全部由參數算出來"""
        import proportions
        return proportions.Body(gender, self)

    def table(self):
        """整張參數表，交件和文件直接貼這一份"""
        lines = ["| 參數 | 值 | 意思 | 從設定圖哪裡量 |", "|---|---|---|---|"]
        for name, _, meaning, source in self.FIELDS:
            lines.append("| `%s` | %.3f | %s | %s |"
                         % (name, getattr(self, name), meaning, source))
        return "\n".join(lines)

    def summary(self):
        """算出來的幾個關鍵尺寸，用來對照量測結果"""
        targets = self.mesh_targets()
        return ("全高 %.3f、頭高 %.3f、下巴 %.3f、頭寬 %.3f、肩半寬 %.3f、"
                "肩線 %.3f、胯部 %.3f、手臂管心 %.3f、指尖 %.3f、腳踝半寬 %.3f"
                % (self.height_m, self.head_height, self.chin_z, self.head_width,
                   self.shoulder_half, self.shoulder_z, self.crotch_z,
                   targets["arm_z"], targets["arm_tip"], targets["leg_x"]))


# 出貨用的那一份，量自使用者 2026-09-18 拍板的初心者設定圖。
# 量法和數字來源寫在 docs/美術風格指南.md 第 2.1 節，
# 重量一次：python3 art_pipeline/characters/designsheet.py spec 設定圖.png
#
# 十四具身體共用同一副骨架，所以標準只能有一份。
# 之後使用者再畫別的設定圖，不是換掉這一份，是用 designsheet.normalize
# 把新圖調到這一份的比例，除非他明講要換標準
STANDARD = RigSpec()


if __name__ == "__main__":
    print(STANDARD.table())
    print()
    print(STANDARD.summary())
