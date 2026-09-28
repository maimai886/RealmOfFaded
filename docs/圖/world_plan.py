# 整個世界的地圖清單和示意圖，一份資料同時出文件表格和圖
from PIL import Image, ImageDraw, ImageFont
import os, sys

# kind: city 城、field 野外、dungeon 地城
# cell: 世界地圖格子，x 往東、y 往南，晨曦鎮在 (0,0)
# phase: 0 已有、1 這次蓋、2 到 5 之後的批次
W = [
    # id, 名, kind, 等級, cell, phase
    ("town", "晨曦鎮", "city", "", (0, 0), 0),
    ("meadow", "萌芽草原", "field", "1-5", (0, 1), 0),
    ("whisper_forest", "低語森林", "field", "6-12", (0, -1), 0),
    ("stone_valley", "碎石谷", "field", "13-20", (0, -2), 0),
    ("gloom_cavern_b1", "灰蝕地窟 B1", "dungeon", "20-26", (1, -2), 0),
    ("gloom_cavern_b2", "灰蝕地窟 B2", "dungeon", "26-32", (2, -1), 0),
    ("windmill_hills", "風車丘", "field", "5-10", (0, 2), 1),
    ("tide_shore", "潮聲沙岸", "field", "9-15", (0, 3), 1),
    ("tidewell_port", "洄潮港", "city", "", (1, 3), 1),
    ("sea_cave", "海蝕洞", "dungeon", "14-20", (-1, 3), 2),
    ("academy_vault_b1", "學院典藏 B1", "dungeon", "22-28", (1, 4), 2),
    ("academy_vault_b2", "學院典藏 B2", "dungeon", "28-36", (2, 4), 2),
    ("reed_marsh", "蘆葦澤", "field", "14-20", (2, 2), 2),
    ("lanternford", "守燈渡", "city", "", (2, 1), 2),
    ("riverside_road", "河畔道", "field", "8-14", (1, 0), 2),
    ("highbough_ridge", "懸梢山脊", "field", "12-18", (-1, -1), 2),
    ("highbough_camp", "懸梢寨", "city", "", (-2, -1), 2),
    ("deep_wood", "懸梢深林", "field", "28-36", (-3, -1), 2),
    ("grindstone_slope", "礪岩坡道", "field", "15-22", (-1, -2), 2),
    ("grindstone_keep", "礪岩堡", "city", "", (-2, -2), 2),
    ("ember_mine_b1", "餘燼礦坑 B1", "dungeon", "30-38", (-1, -3), 2),
    ("ember_mine_b2", "餘燼礦坑 B2", "dungeon", "38-46", (-1, -4), 3),
    ("grey_plateau", "灰岩高原", "field", "40-46", (-2, -3), 3),
    ("maple_path", "紅葉參道", "field", "40-46", (0, -3), 3),
    ("cloudseat_capital", "雲居京", "city", "", (0, -4), 3),
    ("cedar_shrine", "杉林神域", "field", "46-52", (1, -4), 3),
    ("mist_gorge", "霧谷", "field", "52-58", (0, -5), 3),
    ("shrine_depths", "神域地底", "dungeon", "58-66", (2, -4), 4),
    ("cloud_summit", "雲巔", "field", "60-68", (1, -6), 4),
    ("gloom_cavern_b3", "灰蝕地窟 B3", "dungeon", "64-72", (3, -2), 4),
    ("gloom_cavern_b4", "灰蝕地窟 B4", "dungeon", "74-82", (3, -3), 4),
    ("ashen_waste", "灰蝕荒原", "field", "80-88", (2, -5), 5),
    ("gloom_heart", "灰蝕源頭", "dungeon", "88-99", (3, -4), 5),
]
LINKS = [
    ("town", "meadow"), ("town", "whisper_forest"), ("town", "riverside_road"),
    ("whisper_forest", "stone_valley"), ("stone_valley", "gloom_cavern_b1"), ("gloom_cavern_b1", "gloom_cavern_b2"),
    ("meadow", "windmill_hills"), ("windmill_hills", "tide_shore"), ("tide_shore", "tidewell_port"),
    ("tide_shore", "sea_cave"), ("tidewell_port", "academy_vault_b1"), ("academy_vault_b1", "academy_vault_b2"),
    ("tidewell_port", "reed_marsh"), ("reed_marsh", "lanternford"), ("lanternford", "riverside_road"),
    ("whisper_forest", "highbough_ridge"), ("highbough_ridge", "highbough_camp"), ("highbough_camp", "deep_wood"),
    ("stone_valley", "grindstone_slope"), ("grindstone_slope", "grindstone_keep"),
    ("grindstone_slope", "ember_mine_b1"), ("ember_mine_b1", "ember_mine_b2"),
    ("grindstone_keep", "grey_plateau"),
    ("stone_valley", "maple_path"), ("maple_path", "cloudseat_capital"), ("cloudseat_capital", "cedar_shrine"),
    ("cloudseat_capital", "mist_gorge"), ("cedar_shrine", "shrine_depths"), ("mist_gorge", "cloud_summit"),
    ("gloom_cavern_b2", "gloom_cavern_b3"), ("gloom_cavern_b3", "gloom_cavern_b4"),
    ("cloud_summit", "ashen_waste"), ("ashen_waste", "gloom_heart"), ("gloom_cavern_b4", "gloom_heart"),
]
# 走得遠的連線畫成虛線
LONG = set()

PHASE_COLOR = {0: (92, 148, 88), 1: (214, 146, 48), 2: (84, 128, 190), 3: (150, 104, 182), 4: (178, 84, 84),
               5: (70, 70, 70)}
PHASE_NAME = {0: "已有", 1: "第一批，蓋好還沒接", 2: "第二批 Lv 8-38", 3: "第三批 Lv 38-58", 4: "第四批 Lv 58-82",
              5: "第五批 Lv 80-99"}

FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../assets/vendor/fonts/NotoSansTC-wght.ttf")


def draw(path):
    xs = [c[4][0] for c in W]
    ys = [c[4][1] for c in W]
    cw, ch = 190, 118
    pad = 70
    top = 90
    width = (max(xs) - min(xs) + 1) * cw + pad * 2
    height = (max(ys) - min(ys) + 1) * ch + pad * 2 + top + 70
    img = Image.new("RGB", (width, height), (246, 240, 226))
    d = ImageDraw.Draw(img)
    f_title = ImageFont.truetype(FONT, 30)
    f_name = ImageFont.truetype(FONT, 19)
    f_small = ImageFont.truetype(FONT, 14)

    def center(cell):
        return (pad + (cell[0] - min(xs)) * cw + cw // 2, top + pad + (cell[1] - min(ys)) * ch + ch // 2)

    pos = {m[0]: center(m[4]) for m in W}
    d.text((pad, 24), "Realm of Faded 整個世界  2026-09-27 規劃", font=f_title, fill=(50, 44, 36))
    d.text((pad, 62), "北在上。格子就是遊戲裡世界地圖的格子；圓角方塊是城，方塊是野外，虛框是地城", font=f_small,
           fill=(90, 80, 66))
    for a, b in LINKS:
        pa, pb = pos[a], pos[b]
        if (a, b) in LONG:
            n = 14
            for i in range(n):
                if i % 2 == 0:
                    s = (pa[0] + (pb[0] - pa[0]) * i / n, pa[1] + (pb[1] - pa[1]) * i / n)
                    e = (pa[0] + (pb[0] - pa[0]) * (i + 1) / n, pa[1] + (pb[1] - pa[1]) * (i + 1) / n)
                    d.line([s, e], fill=(120, 110, 96), width=3)
        else:
            d.line([pa, pb], fill=(120, 110, 96), width=4)
    for mid, name, kind, lv, cell, phase in W:
        x, y = pos[mid]
        col = PHASE_COLOR[phase]
        bw, bh = 162, 84
        box = [x - bw // 2, y - bh // 2, x + bw // 2, y + bh // 2]
        fill = (255, 252, 244)
        if kind == "city":
            d.rounded_rectangle(box, radius=22, fill=(255, 246, 214), outline=col, width=5)
        elif kind == "dungeon":
            d.rectangle(box, fill=(232, 228, 236), outline=col, width=3)
            d.rectangle([box[0] + 5, box[1] + 5, box[2] - 5, box[3] - 5], outline=col, width=1)
        else:
            d.rectangle(box, fill=fill, outline=col, width=4)
        tw = d.textlength(name, font=f_name)
        d.text((x - tw / 2, y - 30), name, font=f_name, fill=(40, 36, 30))
        sub = ("主城" if mid in ("town", "tidewell_port", "cloudseat_capital") else "城") if kind == "city" else "Lv " + lv
        tw = d.textlength(sub, font=f_small)
        d.text((x - tw / 2, y - 4), sub, font=f_small, fill=col)
        tw = d.textlength(mid, font=f_small)
        d.text((x - tw / 2, y + 16), mid, font=f_small, fill=(120, 112, 100))
    ly = height - 60
    lx = pad
    for ph in range(6):
        d.rectangle([lx, ly, lx + 18, ly + 18], outline=PHASE_COLOR[ph], width=4)
        d.text((lx + 26, ly - 1), PHASE_NAME[ph], font=f_small, fill=(60, 54, 46))
        lx += 40 + int(d.textlength(PHASE_NAME[ph], font=f_small)) + 20
    img.save(path)


if __name__ == "__main__":
    cells = {}
    for m in W:
        assert m[4] not in cells, (m, cells.get(m[4]))
        cells[m[4]] = m[0]
    ids = {m[0] for m in W}
    for a, b in LINKS:
        assert a in ids and b in ids, (a, b)
    draw(sys.argv[1])
    print(len(W), "maps", len(LINKS), "links")
