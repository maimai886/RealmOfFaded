"""
把 AI 產的手繪圖示大圖切成遊戲用的 40×40 圖示，輸出到 assets/ui/icons/items 和 skills。

原圖是 art_source/ui/icons_*_raw.png，每一張是一個整齊的格子陣列，畫在同一塊平灰底上，
同一張用同一段風格描述產生，所以整組的光源、描邊、飽和度是一致的。
處理步驟：切格子、去掉平灰底、裁到內容、等比例縮進 40×40、加一層落影。
對不上的名字會留著舊圖，遊戲端本來就有找不到圖示就畫佔位方塊的退路。

用法：python3 art_pipeline/ui/icons.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import material  # noqa: E402

PROJECT_ROOT = material.PROJECT_ROOT
ITEMS_DIR = os.path.join(PROJECT_ROOT, "assets", "ui", "icons", "items")
SKILLS_DIR = os.path.join(PROJECT_ROOT, "assets", "ui", "icons", "skills")

## 遊戲端讀的圖示大小，item_slot 會再依格子大小縮放
ICON_SIZE = 40
## 圖示四邊留的空白，圖示才不會貼著格子的金屬槽緣
ICON_MARGIN = 2
## 找分界縫時從名目格線往上下各找幾成格子
SEAM_REACH = 0.3

## 每一張大圖的格數和格子內容，順序是從左到右、從上到下
## kind 是 item 或 skill，決定輸出到哪個資料夾
SHEETS = [
    {"file": "icons_a_raw.png", "columns": 4, "rows": 4, "kind": "item", "names": [
        "red_potion", "blue_potion", "green_potion", "orange_potion",
        "small_apple", "bird_meat", "flower_honey", "clear_dewdrop",
        "dew_gel", "glow_spore_cap", "soft_moss", "sprout_seed",
        "dry_branch", "flint_shard", "ash_dust", "gloom_ember"]},
    {"file": "icons_b_raw.png", "columns": 4, "rows": 4, "kind": "item", "names": [
        "sword", "long_sword", "knife", "rusty_blade",
        "bow", "rod", "guard", "cap",
        "cotton_shirt", "sandals", "hollow_plate", "rotten_cloth",
        "snail_shell", "beetle_shell", "wolf_pelt", "wolf_fang"]},
    {"file": "icons_c_raw.png", "columns": 4, "rows": 4, "kind": "mixed", "names": [
        ("item", "bat_wing"), ("item", "bee_stinger"), ("item", "bone_arrowhead"), ("item", "brittle_bone"),
        ("item", "rat_tail"), ("item", "vulture_feather"), ("item", "ash_crown_shard"), ("item", "sovereign_core"),
        ("skill", "sword_mastery"), ("skill", "greatsword_mastery"), ("skill", "heavy_slash"),
        ("skill", "quake_slash"),
        ("skill", "whirl_slash"), ("skill", "pierce_thrust"), ("skill", "counter_stance"), ("skill", "war_roar")]},
    {"file": "icons_d_raw.png", "columns": 4, "rows": 4, "kind": "skill", "names": [
        "endure", "battle_haste", "focus", "first_aid",
        "hp_recovery", "sp_recovery", "novice_basic", "keen_eye",
        "hawk_eye", "double_shot", "arrow_rain", "fire_arrow",
        "frost_arrow", "thunder_arrow", "falcon_dive", "beast_bane"]},
    {"file": "icons_e_raw.png", "columns": 4, "rows": 3, "kind": "skill", "names": [
        "fire_orb", "thunder_orb", "frost_bind", "flame_wall",
        "blizzard_call", "meteor_fall", "mire_field", "napalm_beat",
        "storm_judgement", "snare_trap", "blast_trap", "frost_trap"]},
]

IMPORT_TEMPLATE = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://%s"
path="res://.godot/imported/%s.png-%s.ctex"
metadata={
"vram_texture": false
}

[deps]

source_file="res://assets/ui/icons/%s/%s.png"
dest_files=["res://.godot/imported/%s.png-%s.ctex"]

[params]

compress/mode=0
compress/high_quality=false
compress/lossy_quality=0.7
compress/hdr_compression=1
compress/normal_map=0
compress/channel_pack=0
mipmaps/generate=false
mipmaps/limit=-1
roughness/mode=0
roughness/src_normal=""
process/fix_alpha_border=true
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=0
"""


def _hash(kind, name):
    import hashlib
    return hashlib.md5(("ui_icon/%s/%s" % (kind, name)).encode()).hexdigest()


def _uid(kind, name):
    letters = "abcdefghijklmnopqrstuvwxyz0123456789"
    value = int(_hash(kind, name)[:12], 16)
    out = ""
    for _ in range(12):
        out += letters[value % len(letters)]
        value //= len(letters)
    return "c" + out


def save(image, kind, name):
    folder = ITEMS_DIR if kind == "item" else SKILLS_DIR
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".png")
    image.save(path)
    # 已經有匯入設定就不動，Godot 自己寫的那份和範本的雜湊不一樣，蓋掉會讓每一個圖示都變成改過
    if os.path.exists(path + ".import"):
        return
    digest = _hash(kind, name)
    plural = "items" if kind == "item" else "skills"
    with open(path + ".import", "w", encoding="utf-8") as handle:
        handle.write(IMPORT_TEMPLATE % (_uid(kind, name), name, digest, plural, name, name, digest))


def cut_sheet(sheet):
    """切一張大圖，回傳 [(kind, name, 圖)]"""
    from PIL import Image
    source = material.load_source(sheet["file"])
    if source is None:
        print("[ui/icons] 缺原圖 %s" % sheet["file"])
        return []
    columns, rows = sheet["columns"], sheet["rows"]
    cell_w = source.size[0] // columns
    cell_h = source.size[1] // rows
    # 整張先去背再找縫，每一排和每一欄的分界落在內容最少的那一條線上
    keyed = material.key_flat_background(source)
    ys = _seams(keyed, rows, cell_h, axis=1)
    xs = _seams(keyed, columns, cell_w, axis=0)
    result = []
    for index, entry in enumerate(sheet["names"]):
        kind, name = entry if isinstance(entry, tuple) else (sheet["kind"], entry)
        column = index % columns
        row = index // columns
        # 沿著真正的空白縫切，不照固定格子切：AI 畫的格子不準，第一排的藥水瓶底和影子
        # 超出格子伸進第二排，照格子硬切會把瓶底切掉、影子跑進下一格
        cut = keyed.crop((xs[column], ys[row], xs[column + 1], ys[row + 1]))
        cut = material.drop_small_blobs(cut)
        cut = material.trim(cut)
        if cut.size[0] < 8 or cut.size[1] < 8:
            print("[ui/icons] %s 切出來太小，跳過" % name)
            continue
        icon = material.fit_into(cut, (ICON_SIZE, ICON_SIZE), ICON_MARGIN)
        icon = material.drop_shadow(icon)
        result.append((kind, name, icon))
    return result


def _seams(image, count, cell, axis):
    """回傳 count+1 條分界線的位置：頭尾是圖的邊，中間每一條在名目格線上下 SEAM_REACH 格之內找透明度加總最少的那一列
    axis=1 找橫的分界、回傳 y；axis=0 找直的分界、回傳 x"""
    import numpy as np
    alpha = np.asarray(image.getchannel("A"), dtype=np.int64)
    profile = alpha.sum(axis=axis)
    size = profile.shape[0]
    seams = [0]
    for index in range(1, count):
        nominal = index * cell
        reach = int(cell * SEAM_REACH)
        low = max(seams[-1] + 1, nominal - reach)
        high = min(size - 1, nominal + reach)
        window = profile[low:high + 1]
        # 一樣少的時候挑離名目格線最近的，才不會整排往一邊偏
        best = min(range(len(window)), key=lambda i: (window[i], abs(low + i - nominal)))
        seams.append(low + best)
    seams.append(size)
    return seams


def build():
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("[ui/icons] 這個直譯器沒有 Pillow，改用系統的 python3")
        subprocess.run([_system_python(), os.path.abspath(__file__)], check=True)
        return
    count = 0
    for sheet in SHEETS:
        for kind, name, icon in cut_sheet(sheet):
            # 已經換成石板浮雕的技能圖示由 skill_icons.py 負責，有 _locked 那一張的就是，不能蓋回舊圖
            if kind == "skill" and os.path.exists(os.path.join(SKILLS_DIR, name + "_locked.png")):
                continue
            save(icon, kind, name)
            count += 1
    print("[ui/icons] 完成 %d 個手繪圖示" % count)


def _system_python():
    import shutil
    for candidate in ["/opt/homebrew/bin/python3", shutil.which("python3"), "/usr/local/bin/python3",
                      "/usr/bin/python3"]:
        if candidate and os.path.exists(candidate) and \
                subprocess.run([candidate, "-c", "import PIL"], capture_output=True).returncode == 0:
            return candidate
    raise SystemExit("找不到裝了 Pillow 的 python3")


if __name__ == "__main__":
    build()
