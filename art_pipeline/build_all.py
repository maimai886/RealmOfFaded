"""
一鍵產生遊戲素材。
用法：blender -b --factory-startup --python-exit-code 1 -P art_pipeline/build_all.py -- [--only characters/novice]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from props import foliage, landmarks, nature, town_kit, town_retex  # noqa: E402
from textures import tileable  # noqa: E402
from ui import cursors as ui_cursors, icons as ui_icons, skin  # noqa: E402

# 順序有關係：貼圖先做，樹和城鎮重製版的模型會引用貼圖檔
# ui/skin 只靠 Pillow，Blender 裡沒有的話它會自己改叫系統的 python3
TARGETS = {
    "textures/tileable": tileable.build,
    "props/nature": nature.build,
    "props/foliage": foliage.build,
    "props/town_retex": town_retex.build,
    "props/dungeon_retex": town_retex.build_dungeon,
    "props/town_kit": town_kit.build,
    "props/landmarks": landmarks.build,
    "ui/skin": skin.build,
    "ui/icons": ui_icons.build,
    "ui/cursors": ui_cursors.build,
}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", help="只產生指定項目，可重複")
    args = parser.parse_args(argv)
    names = args.only or list(TARGETS)
    unknown = [name for name in names if name not in TARGETS]
    if unknown:
        raise SystemExit("unknown targets: %s，可用的有：%s" % (unknown, list(TARGETS)))
    for name in names:
        print("[build] %s" % name)
        TARGETS[name]()
    print("[build] done")


main()
