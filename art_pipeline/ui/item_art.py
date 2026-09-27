"""
道具的兩種圖：背包裡的小圖示和右鍵道具資訊裡的大插圖，照 RO 分成兩張不同的圖。
2026-09-26 使用者：「小圖跟大圖是不同的」，大插圖試畫四張挑了 2、3、4 那種，種子固定用 13。

- 大插圖：拿那件道具的小圖示當參考，Flux 2 Klein 畫成一張放大、細節多的手繪插圖，白底，
  存成 assets/ui/illustrations/items/<id>.png，256×256。白底不去背，RO 的道具圖本來就是白底放在畫框裡
- 小圖示：還沒有圖示的道具先補。拿同一類道具的現有圖示當畫風參考畫在平灰底上，
  再用 ui/material.py 去背、裁切、縮成 40×40、加落影，和 ui/icons.py 切出來的那批同一套處理

ComfyUI 要先開著，見 docs/美術產線接手紀錄.md。
用法：
  python art_pipeline/ui/item_art.py icons         補缺的小圖示
  python art_pipeline/ui/item_art.py recut         不重畫，拿原始檔重新去背裁切補出來的小圖示
  python art_pipeline/ui/item_art.py illus [id...] 畫大插圖，不給 id 就畫全部還沒有的
  python art_pipeline/ui/item_art.py sheet         全部大插圖排成一張總覽，給人看
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comfy import flux  # noqa: E402
from ui import icons, material  # noqa: E402

PROJECT_ROOT = material.PROJECT_ROOT
ILLUS_DIR = os.path.join(PROJECT_ROOT, "assets", "ui", "illustrations", "items")
RAW_DIR = os.path.join(PROJECT_ROOT, "art_source", "ui", "item_art")
ILLUS_SIZE = 256
SEED = 13
## 小圖示去背：比這個暗的一定是描邊或物體；相鄰像素差超過這個就算碰到東西
BG_MIN_LUMA = 95
BG_STEP = 10
BG_MAX_CHROMA = 26
## 被細線圈起來的底：和背景平均色差多少以內、至少多大一片才算
BG_ENCLOSED = 22
BG_ENCLOSED_MIN = 400

ILLUS_PROMPT = ("A large hand-painted item illustration of {what}, the same object as the small reference icon but drawn "
                "much bigger and with much more detail, like the item collection artwork in the classic MMORPG Ragnarok "
                "Online: soft painterly shading, gentle warm light from the upper left, a slightly tilted three-quarter "
                "view, the whole object centered with space around it, plain pure white background with no light rays "
                "and no glow on the background, no text, no frame, no ground shadow.")
ICON_PROMPT = ("A small fantasy RPG inventory icon of {what}, painted in exactly the same style as the reference icon: "
               "chunky hand-painted shapes, a thin dark brown outline, warm light from the upper left, the whole object "
               "centered and filling most of the square, on a perfectly flat uniform mid grey background with no gradient, "
               "no light rays, no glow on the background, no vignette, no text, no frame.")

## 每件道具畫的是什麼，英文給模型看；icon_ref 是缺圖示時拿哪一個現有圖示當畫風參考
ITEMS = {
    "red_potion": "a round glass flask with a cork, filled with red potion",
    "orange_potion": "a round glass flask with a cork, filled with orange potion",
    "blue_potion": "a round glass flask with a cork, filled with glowing blue potion",
    "green_potion": "a round glass flask with a cork, filled with green potion",
    "small_apple": "a small shiny red apple with one green leaf",
    "flower_honey": "a small clay honey pot overflowing with golden flower honey",
    "dew_gel": "a wobbly blob of translucent green jelly",
    "clear_dewdrop": "a single large clear water droplet that sparkles with a tiny rainbow",
    "soft_moss": "a soft fluffy clump of green moss",
    "sprout_seed": "a brown seed with a tiny green two-leaf sprout growing from it",
    "bee_stinger": "a single curved insect stinger: a sharp tapered amber spike, pointed at one end, with a small fuzzy yellow and black base",
    "brittle_bone": "a dry cracked old bone",
    "ash_dust": "a small heap of fine grey ash dust",
    "knife": "a small simple beginner's knife with a wooden handle",
    "sword": "a plain steel short sword with a leather wrapped grip",
    "rusty_blade": "a rusty chipped short blade",
    "long_sword": "a long two-handed steel sword",
    "rod": "a wooden magic staff topped with a small blue gemstone",
    "elder_rod": ("a gnarled staff made from an old tree branch, twisted wood with a few leaves still growing on it", "rod"),
    "dawnspire_rod": ("a slender white staff with a pointed tip that glows with soft golden dawn light", "rod"),
    "dawn_censer": ("a small bronze censer lantern hanging from a chain, a little flame burning inside", "rod"),
    "vigil_censer": ("a dark iron censer lantern on a chain, burning with a pale white flame", "rod"),
    "dawnfire_censer": ("an ornate golden censer lantern on a chain, glowing with bright orange sunrise fire", "rod"),
    "bow": "a simple wooden short bow with a string",
    "hunting_bow": ("a hand-carved wooden hunting bow covered in little tally marks", "bow"),
    "ridge_bow": ("a tall stiff longbow of dark wood wrapped with leather at the grip", "bow"),
    "dawnwing_bow": ("an elegant white and gold recurve bow with a bowstring, each limb carved with feather patterns like a bird wing", "bow"),
    "guard": "a round wooden shield with an iron rim",
    "cotton_shirt": "a simple cream cotton shirt",
    "sandals": "a pair of brown leather sandals",
    "cap": "a soft brown cloth cap",
    "beetle_shell": "a hard green fern beetle shell",
    "glow_spore_cap": "a glowing pale mushroom cap",
    "dry_branch": "a dry forked twig",
    "wolf_fang": "a long sharp grey wolf fang",
    "wolf_pelt": "a folded grey wolf pelt",
    "snail_shell": "a heavy spiral rock snail shell",
    "flint_shard": "a sharp dark grey flint stone shard",
    "rat_tail": "a thin brown rat tail",
    "vulture_feather": "a long brown vulture feather",
    "bird_meat": "a raw bird drumstick",
    "bat_wing": "a thin leathery bat wing",
    "rotten_cloth": "a torn rotten grey rag",
    "bone_arrowhead": "an arrowhead ground from bone",
    "gloom_ember": "a dark smouldering ember glowing with cold purple light",
    "hollow_plate": "a dented empty armour plate",
    "ash_crown_shard": "a broken shard of a dark ash crown",
    "sovereign_core": "a dark crystal core framed in wood, swirling with purple haze",
    "steel_blade": ("a heavy two-handed steel greatsword with a flint-tempered wavy pattern on the blade", "long_sword"),
    "ashguard_plate": ("a padded cloth armour vest stitched with green sprout fibres", "cotton_shirt"),
    "ridge_greatsword": ("a massive two-handed greatsword with a thick blade that looks carved from layered grey stone", "long_sword"),
    "warden_blade": ("an old guardian's longsword with a green leaf engraving that glows faintly", "long_sword"),
    "verdant_mail": ("a suit of armour grown from living green vines and leaves", "cotton_shirt"),
    "verdant_draught": ("a tall glass bottle of thick dark green herbal medicine", "green_potion"),
    "dawn_tonic": ("a small glass vial of clear golden drink with a sparkling dewdrop floating in it", "orange_potion"),
    "town_scroll": ("a rolled parchment scroll tied with a red ribbon and a small wax seal", "clear_dewdrop"),
    "hourglass_edge": ("a dagger whose blade is a slim glass hourglass with golden sand falling inside", "knife"),
    "riftcutter": ("a two-handed sword with a jagged blade that seems to split the air with a violet crack", "long_sword"),
    "refine_dust": ("a little cloth pouch spilling fine sparkling grey sand", "ash_dust"),
    "refine_charm": ("a small wooden charm carved with a green sprout, hanging on a string", "sprout_seed"),
    "dawn_seal": ("a round golden seal medallion engraved with a rising sun", "ash_crown_shard"),
    "affix_solvent": ("a corked glass flask of swirling rainbow coloured liquid", "blue_potion"),
    "mossweave_robe": ("a long robe woven from soft green moss", "cotton_shirt"),
    "flint_dagger": ("a dagger chipped from dark flint with a leather grip, a few sparks flying", "knife"),
    "emberguard_cape": ("a short shoulder cape stitched from bat wings, glowing ember seams", "bat_wing"),
    "travel_cloak": ("a folded brown traveller's cloak with a hood", "cotton_shirt"),
    "guardian_cape": ("a deep green guardian cape with a golden leaf clasp", "cotton_shirt"),
    "tattered_cloak": ("a ragged torn old grey cloak full of holes", "rotten_cloth"),
    "dawn_edge": ("a short dagger whose edge shines with a faint soft light", "knife"),
    "dawnbreak_edge": ("a curved dagger leaving a streak of white light behind its blade", "knife"),
    "soul_horn_slime": "a bouncy glowing soul orb of the lime slime, green and jelly-like",
    "soul_leaf_sprout": "a glowing soul orb of the little sapling, warm green with a tiny leaf",
    "soul_crystal_bunny": "a glittering crystal soul orb of the crystal bunny",
    "soul_stump_king": "a hard wooden soul orb of the stump king with bark texture",
    "seed_stump_king": "a large seed marked with rings like a tree stump",
    "paint_blue": "a small jar of blue paint",
    "paint_green_rich": "a small jar of thick rich dark green paint",
    "paint_blue_rich": "a small jar of thick rich dark blue paint",
    "paint_green": "a small jar of green paint",
    "twig_straight": "a perfectly straight young twig",
    "twig_bent": "a slightly bent young twig",
    "twig_curly": "a very curly young twig",
    "twig_knotted": "a young twig tied in a knot",
    "solution_1": "a glass test flask of pale green liquid",
    "solution_2": "a glass test flask of bubbling red liquid",
    "solution_3": "a glass test flask of shining bright blue liquid",
    "solution_4": "a glass test flask of liquid with glittering sparkles inside",
    "solution_failed": "a cracked glass test flask of black liquid giving off dark smoke",
    "solution_mystery": "a glass test flask of purple liquid bubbling by itself",
}


def entry(item_id):
    value = ITEMS[item_id]
    return (value, None) if isinstance(value, str) else value


def icon_path(item_id):
    return os.path.join(icons.ITEMS_DIR, item_id + ".png")


def _white_reference(path, out_path):
    """圖示墊白底放大到 512 當參考，透明底直接送進去模型會把透明當黑色"""
    from PIL import Image
    icon = Image.open(path).convert("RGBA")
    card = Image.new("RGBA", icon.size, (255, 255, 255, 255))
    card.alpha_composite(icon)
    card.convert("RGB").resize((512, 512), Image.LANCZOS).save(out_path)
    return out_path


def build_icons(only=None):
    """補還沒有小圖示的道具"""
    from PIL import Image
    os.makedirs(RAW_DIR, exist_ok=True)
    for item_id in ITEMS:
        what, style_ref = entry(item_id)
        if style_ref is None or (os.path.exists(icon_path(item_id)) and item_id not in (only or [])):
            continue
        # 參考圖墊成和原圖示大圖一樣的平灰底，去背才抓得到底色
        icon = Image.open(icon_path(style_ref)).convert("RGBA")
        card = Image.new("RGBA", icon.size, (113, 110, 101, 255))
        card.alpha_composite(icon)
        ref_file = os.path.join(RAW_DIR, "ref_icon_%s.png" % style_ref)
        card.convert("RGB").resize((512, 512), Image.LANCZOS).save(ref_file)
        raw = flux.run(flux.graph(ICON_PROMPT.format(what=what), flux.upload(ref_file), SEED, size=512))
        raw.save(os.path.join(RAW_DIR, "icon_%s.png" % item_id))
        icons.save(cut_icon(raw), "item", item_id)
        print("icon", item_id, flush=True)


def cut_icon(raw):
    """產出來的灰底不平：模型常把左上的光畫成背景上一道光束。
    所以不拿單一底色去背，改從圖的四邊往內長：相鄰像素顏色差得不多就算同一片背景，
    長到圖示的深色描邊就停下來，描邊之內再亮再灰都留著"""
    import numpy as np
    from PIL import Image
    rgb = np.asarray(raw.convert("RGB"), dtype=np.int32)
    height, width, _ = rgb.shape
    luma = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    background = np.zeros((height, width), dtype=bool)
    stack = [(x, y) for x in range(width) for y in (0, height - 1)] +             [(x, y) for y in range(height) for x in (0, width - 1)]
    for x, y in stack:
        background[y, x] = True
    while stack:
        x, y = stack.pop()
        here = rgb[y, x]
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height and not background[ny, nx]:
                there = rgb[ny, nx]
                # 描邊是深褐色，比周圍的底暗很多；一步之內顏色跳太多也當成碰到東西了
                # 底是灰的，飽和度很低；暖色的紙、金屬碰到就停，不然亮紙會跟著亮背景一起被吃掉
                if luma[ny, nx] > BG_MIN_LUMA and chroma[ny, nx] <= BG_MAX_CHROMA                         and np.abs(there - here).max() <= BG_STEP:
                    background[ny, nx] = True
                    stack.append((nx, ny))
    # 被弓弦這種細線圈起來的底從外面灌不進去：顏色和已經確定是背景的平均色很近、又不飽和的一整片也算背景
    base = rgb[background].mean(axis=0)
    near = (np.abs(rgb - base).max(axis=2) <= BG_ENCLOSED) & (chroma <= BG_MAX_CHROMA)
    background |= _large_regions(near, BG_ENCLOSED_MIN)
    alpha = Image.fromarray(np.where(background, 0, 255).astype(np.uint8), "L")
    from PIL import ImageFilter
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.6))
    cut = raw.convert("RGBA")
    cut.putalpha(alpha)
    cut = material.drop_small_blobs(cut)
    cut = material.trim(cut)
    out = material.fit_into(cut, (icons.ICON_SIZE, icons.ICON_SIZE), icons.ICON_MARGIN)
    return material.drop_shadow(out)


def _large_regions(mask, min_pixels):
    """mask 裡面連成一片而且夠大的區塊"""
    import numpy as np
    height, width = mask.shape
    seen = np.zeros_like(mask)
    keep = np.zeros_like(mask)
    for start_y in range(height):
        for start_x in range(width):
            if not mask[start_y, start_x] or seen[start_y, start_x]:
                continue
            region = [(start_x, start_y)]
            seen[start_y, start_x] = True
            index = 0
            while index < len(region):
                x, y = region[index]
                index += 1
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < width and 0 <= ny < height and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        region.append((nx, ny))
            if len(region) >= min_pixels:
                for x, y in region:
                    keep[y, x] = True
    return keep


def recut_icons():
    """不重畫，拿存著的原始檔重新去背裁切"""
    from PIL import Image
    for item_id in ITEMS:
        raw_file = os.path.join(RAW_DIR, "icon_%s.png" % item_id)
        if os.path.exists(raw_file):
            icons.save(cut_icon(Image.open(raw_file).convert("RGB")), "item", item_id)


def build_illustrations(only=None):
    from PIL import Image
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(ILLUS_DIR, exist_ok=True)
    for item_id in ITEMS:
        if only and item_id not in only:
            continue
        out_file = os.path.join(ILLUS_DIR, item_id + ".png")
        if not only and os.path.exists(out_file):
            continue
        if not os.path.exists(icon_path(item_id)):
            print("skip %s：還沒有小圖示" % item_id)
            continue
        what, _ = entry(item_id)
        ref_file = _white_reference(icon_path(item_id), os.path.join(RAW_DIR, "ref_%s.png" % item_id))
        raw = flux.run(flux.graph(ILLUS_PROMPT.format(what=what), flux.upload(ref_file), SEED, size=768))
        raw.save(os.path.join(RAW_DIR, "illus_%s.png" % item_id))
        raw.resize((ILLUS_SIZE, ILLUS_SIZE), Image.LANCZOS).save(out_file)
        _write_import(item_id)
        print("illus", item_id, flush=True)


def _write_import(item_id):
    path = os.path.join(ILLUS_DIR, item_id + ".png.import")
    if os.path.exists(path):
        return
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("[remap]\n\nimporter=\"texture\"\ntype=\"CompressedTexture2D\"\n\n[deps]\n\n"
                     "source_file=\"res://assets/ui/illustrations/items/%s.png\"\n\n[params]\n\n"
                     "compress/mode=0\nmipmaps/generate=false\nprocess/fix_alpha_border=true\n"
                     "detect_3d/compress_to=0\n" % item_id)


def build_sheet(out_path):
    from PIL import Image
    files = [f for f in sorted(os.listdir(ILLUS_DIR)) if f.endswith(".png")]
    columns = 10
    cell = 128
    sheet = Image.new("RGB", (columns * (cell + 4), ((len(files) + columns - 1) // columns) * (cell + 4)), (200, 200, 200))
    for index, name in enumerate(files):
        image = Image.open(os.path.join(ILLUS_DIR, name)).convert("RGB").resize((cell, cell), Image.LANCZOS)
        icon_file = icon_path(name[:-4])
        if os.path.exists(icon_file):
            icon = Image.open(icon_file).convert("RGBA")
            image.paste(icon, (0, cell - icon.size[1]), icon)
        sheet.paste(image, ((index % columns) * (cell + 4), (index // columns) * (cell + 4)))
    sheet.save(out_path)
    print(out_path)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "illus"
    if command == "icons":
        build_icons(sys.argv[2:] or None)
    elif command == "recut":
        recut_icons()
    elif command == "illus":
        build_illustrations(sys.argv[2:] or None)
    elif command == "sheet":
        build_sheet(sys.argv[2] if len(sys.argv) > 2 else os.path.join(RAW_DIR, "sheet.png"))
    else:
        raise SystemExit(json.dumps(__doc__))
