"""衝擊閃光序列圖的驗收：量出貨的 assets/vfx/impact_flash.png 本身，不信產生時的參數。

Nora 的條件：光絲 7 到 11 條而且成簇、最長最短差三倍、沒有兩條一樣長、根部 3 到 6 像素、末端削尖、
亮度沿長度有起伏、白芯不是正圓、第 3 格亮度一半、第 4 格只剩碎片沒有白芯、深邊逐格變少；
Felix 的條件：內容不碰格子邊、兩格之間空 16 像素以上。
另外檢查出貨的圖就是產圖程式現在會畫出來的那一張，改了程式沒重跑會紅。
"""
import os
import sys

# Blender 內建的 Python 沒有 Pillow，run.py 看到這個旗標會改叫系統的 python3 跑
NEEDS_PILLOW = True

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PIPELINE_DIR, "vfx"))


def _shipped():
    import numpy as np
    from PIL import Image
    import impact_flash
    return np.asarray(Image.open(impact_flash.OUT).convert("RGBA"))


def test_shipped_atlas_passes_every_check():
    import impact_flash
    problems = impact_flash.check(_shipped())
    assert not problems, "；".join(problems)


def test_shipped_atlas_is_what_the_generator_draws():
    import numpy as np
    import impact_flash
    built, _ = impact_flash.build()
    shipped = _shipped()
    assert built.shape == shipped.shape
    assert int(np.abs(built.astype(int) - shipped.astype(int)).max()) <= 1, "出貨的圖和程式畫的不一樣，重跑 impact_flash.py"
