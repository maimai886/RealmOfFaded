"""出貨的身體圖集不准有髒邊。2026-09-28 Victor 驗到男初心者站姿手臂腰邊一片粉色、右肩灰點、腳邊黑點，
原因是關節圓頭補到縮圖留下的淡邊上、去白底只調淡不還原顏色。量法在 common/sheet_clean.py。"""
import os

NEEDS_PILLOW = True

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BODY_ROOT = os.path.join(os.path.dirname(PIPELINE_DIR), "assets", "generated", "sprites", "characters", "body")


def _sheets():
    for name in sorted(os.listdir(BODY_ROOT)):
        path = os.path.join(BODY_ROOT, name, "sheet.png")
        if os.path.exists(path):
            yield name, path


def test_出貨的身體圖集每一格都沒有離島():
    from common import sheet_clean
    for name, path in _sheets():
        report = sheet_clean.sheet_report(path)
        assert report["total"]["islands"] == 0, (name, report["worst"])


def test_站姿第一格五個方向剪影外沒有淡色毛邊():
    import json
    from PIL import Image
    from common import sheet_clean
    for name, path in _sheets():
        with open(os.path.join(BODY_ROOT, name, "meta.json"), encoding="utf-8") as handle:
            meta = json.load(handle)
        fw, fh = meta["frame_size"]
        idle = meta["actions"]["idle"]
        sheet = Image.open(path)
        for d in range(len(meta["directions"])):
            index = idle["start"] + d * idle["frames"]
            r, c = divmod(index, meta["columns"])
            islands, haze, _ = sheet_clean.cell_dirt(sheet.crop((c * fw, r * fh, (c + 1) * fw, (r + 1) * fh)))
            assert islands.sum() == 0 and haze.sum() == 0, (name, meta["directions"][d], int(islands.sum()), int(haze.sum()))
