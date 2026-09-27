"""
技能圖示：石板底、石框、單色剪影浮雕。還沒學是灰色石雕，學會後符號亮起來加一圈光暈，光的顏色照技能類型。
2026-09-26 使用者看過七種風格後定案，參考圖在 art_source/ui/skill_icons/reference/icon_style_ref2.webp。

AI 只畫黑底白剪影，取出形狀存在 art_source/ui/skill_icons/glyphs/<技能 id>.png；
浮雕、石板、石框、光暈全部由這支程式畫，所以整套規格一致，兩種狀態一定是同一個形狀。
輸出 assets/ui/icons/skills/<技能 id>.png 是學會的，<技能 id>_locked.png 是還沒學的。

用法：python art_pipeline/ui/skill_icons.py --glyphs <技能 id ...> [--seeds 1,2]   畫剪影候選
      python art_pipeline/ui/skill_icons.py --sheet <技能 id ...>                  候選拼一張看
      python art_pipeline/ui/skill_icons.py --pick <技能 id> <種子>                挑一張，存剪影並出圖
      python art_pipeline/ui/skill_icons.py --build                               照 glyphs 全部重出
      python art_pipeline/ui/skill_icons.py --stone                               畫石板底紋，只要一次
"""
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from comfy import flux  # noqa: E402

SOURCE = os.path.join(flux.PROJECT_ROOT, "art_source", "ui", "skill_icons")
RAW = os.path.join(SOURCE, "_raw")
GLYPHS = os.path.join(SOURCE, "glyphs")
STONE = os.path.join(SOURCE, "stone.png")
SHIP = os.path.join(flux.PROJECT_ROOT, "assets", "ui", "icons", "skills")
SIZE = 128
BIG = 512

GLYPH_PROMPT = ("A single simple flat solid white silhouette pictogram of {what}, bold clean graphic shapes, only a few "
                "thin black cut lines inside for detail, centred with margin, on a pure solid black background, like a "
                "fantasy RPG ability icon glyph. No gradient, no shading, no border, no text.")
STONE_PROMPT = ("Seamless square texture of dark grey slate stone, subtle scratches, chips and grunge, very dark charcoal "
                "with slightly lighter mottled patches, flat even lighting, no objects, no text.")

# 學會後的光：照技能類型分，一眼看得出是攻擊、被動、增益、位移、控場還是治療
GLOW = {"attack": (255, 128, 72), "passive": (150, 240, 120), "buff": (120, 190, 255), "move": (100, 236, 220),
        "control": (214, 140, 255), "heal": (255, 214, 110)}

# 技能 id: (類型, 剪影畫什麼)；技能表在 docs/技能與流派.md 第 5 節
DESIGNS = {
    # 初心者
    "novice_basic": ("passive", "a small sprout with two leaves growing from a closed fist"),
    "first_aid": ("heal", "a rolled bandage with a small cross on it"),
    "full_colour_burst": ("attack", "a round paint splash exploding outward in all directions from a seed"),
    # 劍侍
    "sword_mastery": ("passive", "a single straight sword pointing up diagonally"),
    "rock_crash": ("attack", "a sword stabbed point down into a pile of broken rocks with impact lines"),
    "wind_pierce": ("attack", "a sword thrusting forward with three curved wind streaks around it"),
    "blade_breath": ("passive", "a sword with a leaf curling around the blade"),
    "momentum": ("passive", "three curved sword slash marks stacked"),
    "stone_skin": ("buff", "a heater shield with a few cracks"),
    "rush_step": ("move", "a boot dashing forward with speed lines"),
    "halt_shout": ("control", "a roaring lion head in profile"),
    # 術士
    "staff_mastery": ("passive", "a wooden wizard staff with a round crystal at the top"),
    "magic_bolt": ("attack", "a sharp crystal shard flying diagonally with a short trail"),
    "blast_glyph": ("attack", "a round magic rune circle on the ground bursting with an explosion"),
    "zone_glyph": ("attack", "a round magic rune circle with flames rising from the whole area"),
    "detonate": ("attack", "three small rune circles exploding at the same time"),
    "spirit_gather": ("passive", "swirling wisps of energy spiralling into a small orb"),
    "bind_glyph": ("control", "a rune circle with chains crossing over it"),
    "glyph_step": ("move", "a bold dashing silhouette leaving three fading afterimage copies behind it"),
    # 斥候
    "mark_shot": ("attack", "an arrow hitting a diamond-shaped mark"),
    "mark_chase": ("attack", "an arrow curving in the air toward a diamond-shaped mark"),
    "mark_burst": ("attack", "a diamond-shaped mark shattering into pieces"),
    "archery": ("passive", "a recurve bow with an arrow nocked"),
    "light_step": ("passive", "a feather above a light boot"),
    "colour_seek": ("passive", "an eye with a small sparkle inside the pupil"),
    "back_shot": ("move", "an archer leaping backward while shooting an arrow forward"),
    "deep_mark": ("passive", "three diamond-shaped marks stacked"),
    # 信徒
    "soothe": ("heal", "two open hands holding a small glowing leaf"),
    "dawn_ray": ("attack", "a radiant sun with a thick beam of light shooting diagonally from it"),
    "faith": ("passive", "a hanging censer with a small wisp of smoke"),
    "prayer_guard": ("buff", "a round shield with a sun symbol on it"),
    "dawn_step": ("move", "a winged sandal dashing forward"),
    "cleanse": ("heal", "a water drop with a sparkle washing away small dark specks"),
    "censer_strike": ("attack", "a swinging censer on a chain hitting with an impact burst"),
    "sanctuary": ("heal", "a flat magic circle on the ground seen at an angle with three tall pillars of light rising from it"),
}


def _graph_no_ref(prompt, seed):
    g = flux.graph(prompt, "unused", seed, size=1024)
    for key in ("10", "20", "30", "40", "50"):
        g.pop(key, None)
    g["64"]["inputs"]["positive"] = ["4", 0]
    g["64"]["inputs"]["negative"] = ["5", 0]
    return g


def _rr(inset, radius):
    m = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(m).rounded_rectangle((inset, inset, BIG - 1 - inset, BIG - 1 - inset), radius=radius, fill=255)
    return m


def _stone(offset, gain):
    t = Image.open(STONE).convert("L")
    t = t.crop((offset, offset, offset + 700, offset + 700)).resize((BIG, BIG), Image.LANCZOS)
    t = ImageOps.autocontrast(t, cutoff=1)
    return t.point(lambda v: int(min(255, v * gain)))


def _gray(layer, scale, bias):
    return Image.merge("RGB", [layer.point(lambda v: int(v * scale + bias))] * 3)


def _mask(layer, amount):
    return layer.point(lambda v: int(v * amount))


def glyph_mask(path):
    """剪影裁到主體、放到正中間佔六成"""
    g = Image.open(path).convert("L").point(lambda v: 255 if v > 128 else 0)
    g = g.crop(g.getbbox())
    room = int(BIG * 0.6)
    scale = room / max(g.size)
    g = g.resize((max(1, int(g.width * scale)), max(1, int(g.height * scale))), Image.LANCZOS)
    m = Image.new("L", (BIG, BIG), 0)
    m.paste(g, ((BIG - g.width) // 2, (BIG - g.height) // 2))
    return m


def compose(mask, kind, learned, seed):
    """石框、深色石板、暗角、凹槽；還沒學是浮雕石雕，學會是發光的符號"""
    black = Image.new("L", (BIG, BIG), 0)
    out = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    radius = 30
    outer = _rr(0, radius)
    # 石框：較亮的石頭，左上亮邊、右下暗邊
    out.paste(_gray(_stone(40 + seed % 200, 0.95), 0.55, 40), (0, 0), outer)
    lit = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(lit).rounded_rectangle((2, 2, BIG - 14, BIG - 14), radius=radius, outline=255, width=10)
    out.paste((210, 206, 198), (0, 0), _mask(Image.composite(lit.filter(ImageFilter.GaussianBlur(3)), black, outer), 0.5))
    dark = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(dark).rounded_rectangle((12, 12, BIG - 3, BIG - 3), radius=radius, outline=255, width=10)
    out.paste((10, 8, 10), (0, 0), _mask(Image.composite(dark.filter(ImageFilter.GaussianBlur(3)), black, outer), 0.7))
    # 內板：深色石板加暗角
    inset = 34
    inner = _rr(inset, radius - 12)
    out.paste(_gray(_stone(300 - seed % 200, 0.6), 0.42, 18), (0, 0), inner)
    vignette = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(vignette).ellipse((-60, -60, BIG + 60, BIG + 60), fill=255)
    vignette = _mask(ImageOps.invert(vignette.filter(ImageFilter.GaussianBlur(70))), 0.8)
    out.paste((0, 0, 0), (0, 0), Image.composite(vignette, black, inner))
    groove = Image.new("L", (BIG, BIG), 0)
    ImageDraw.Draw(groove).rounded_rectangle((inset, inset, BIG - 1 - inset, BIG - 1 - inset), radius=radius - 12,
                                             outline=255, width=8)
    out.paste((6, 5, 6), (0, 0), groove)
    out.paste((0, 0, 0), (0, 0), Image.composite(groove.filter(ImageFilter.GaussianBlur(16)), black, inner))
    if learned:
        color = GLOW[kind]
        halo = Image.composite(mask.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.GaussianBlur(26)), black, inner)
        out.paste(color, (0, 0), _mask(halo, 0.95))
        wide = Image.composite(mask.filter(ImageFilter.GaussianBlur(60)), black, inner)
        out.paste(color, (0, 0), _mask(wide, 0.5))
        out.paste((20, 12, 8), (0, 0), _mask(ImageChops.offset(mask, 5, 7).filter(ImageFilter.GaussianBlur(4)), 0.5))
        # 符號本體：中心近白，邊緣一圈帶類型色
        body = tuple(min(255, int(c * 0.35 + 170)) for c in color)
        edge = ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(9))).filter(ImageFilter.GaussianBlur(2))
        out.paste(body, (0, 0), mask)
        out.paste(color, (0, 0), _mask(edge, 0.8))
    else:
        out.paste((0, 0, 0), (0, 0), _mask(ImageChops.offset(mask, 6, 9).filter(ImageFilter.GaussianBlur(5)), 0.8))
        out.paste(_gray(_stone(120 + seed % 150, 1.0), 0.25, 150), (0, 0), mask)
        high = ImageChops.subtract(mask, ImageChops.offset(mask, 4, 5)).filter(ImageFilter.GaussianBlur(1.5))
        out.paste((236, 232, 224), (0, 0), _mask(high, 0.8))
        low = ImageChops.subtract(mask, ImageChops.offset(mask, -4, -5)).filter(ImageFilter.GaussianBlur(1.5))
        out.paste((60, 56, 54), (0, 0), _mask(low, 0.8))
    return out.resize((SIZE, SIZE), Image.LANCZOS)


def build(skill_id):
    kind, _ = DESIGNS[skill_id]
    mask = glyph_mask(os.path.join(GLYPHS, skill_id + ".png"))
    # 每招從石頭取不同的位置，整排不會長得一樣
    seed = sum(ord(c) * (i + 1) for i, c in enumerate(skill_id))
    compose(mask, kind, True, seed).save(os.path.join(SHIP, skill_id + ".png"))
    compose(mask, kind, False, seed).save(os.path.join(SHIP, skill_id + "_locked.png"))


def sheet(ids, out):
    cells = []
    for skill_id in ids:
        for name in sorted(os.listdir(RAW)):
            if name.startswith(skill_id + "_") and name[len(skill_id) + 1:-4].isdigit():
                cells.append((name[:-4], Image.open(os.path.join(RAW, name)).convert("RGB").resize((192, 192))))
    columns = 8
    board = Image.new("RGB", (192 * columns, 212 * ((len(cells) + columns - 1) // columns)), (40, 40, 40))
    draw = ImageDraw.Draw(board)
    for i, (label, img) in enumerate(cells):
        x, y = (i % columns) * 192, (i // columns) * 212
        board.paste(img, (x, y))
        draw.text((x + 4, y + 194), label, fill=(230, 230, 230))
    board.save(out)


def main():
    args = sys.argv[1:]
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(GLYPHS, exist_ok=True)
    if args[0] == "--stone":
        flux.run(_graph_no_ref(STONE_PROMPT, 1)).save(STONE)
    elif args[0] == "--pick":
        skill_id, seed = args[1], int(args[2])
        Image.open(os.path.join(RAW, "%s_%d.png" % (skill_id, seed))).convert("L").point(
            lambda v: 255 if v > 128 else 0).save(os.path.join(GLYPHS, skill_id + ".png"))
        build(skill_id)
    elif args[0] == "--build":
        for name in sorted(os.listdir(GLYPHS)):
            if name.endswith(".png") and name[:-4] in DESIGNS:
                build(name[:-4])
    elif args[0] == "--sheet":
        sheet(args[1:], os.path.join(RAW, "_sheet.png"))
    elif args[0] == "--glyphs":
        ids = args[1:]
        seeds = [1, 2]
        if "--seeds" in ids:
            i = ids.index("--seeds")
            seeds = [int(s) for s in ids[i + 1].split(",")]
            ids = ids[:i] + ids[i + 2:]
        for skill_id in ids or list(DESIGNS):
            for seed in seeds:
                path = os.path.join(RAW, "%s_%d.png" % (skill_id, seed))
                if not os.path.exists(path):
                    flux.run(_graph_no_ref(GLYPH_PROMPT.format(what=DESIGNS[skill_id][1]), seed)).save(path)
                print(skill_id, seed, flush=True)


if __name__ == "__main__":
    main()
