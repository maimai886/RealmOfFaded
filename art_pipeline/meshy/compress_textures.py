"""
Godot 第一次匯入 towns 的 glb 時會把貼圖抽成旁邊的 jpg，預設是無損格式，一張 2K 在顯示記憶體裡 22 MB；
改成顯示卡壓縮格式只剩五分之一。Godot 匯入過一次之後跑這支，再讓 Godot 重新匯入一次。
2026-09-26 晨曦鎮換上新房子時量過：貼圖從 1033 MB 降到 916 MB，舊版是 900 MB

用法：python art_pipeline/meshy/compress_textures.py
"""
import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
changed = 0
for path in glob.glob(os.path.join(ROOT, "assets", "generated", "models", "towns", "*", "*.jpg.import")):
    text = open(path, encoding="utf-8").read()
    if "compress/mode=0\n" in text:
        open(path, "w", encoding="utf-8", newline="\n").write(text.replace("compress/mode=0\n", "compress/mode=2\n"))
        changed += 1
print("改了 %d 個" % changed)
