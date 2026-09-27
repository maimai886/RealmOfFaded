import numpy as np


def pack_grid(rows):
    """rows 是二維清單，每格是 (高, 寬, 4) 的陣列，由上往下、由左往右排，較短的列右邊留透明"""
    height, width = rows[0][0].shape[:2]
    cols = max(len(row) for row in rows)
    result = np.zeros((height * len(rows), width * cols, 4), dtype=np.float32)
    for ri, row in enumerate(rows):
        for ci, frame in enumerate(row):
            result[ri * height:(ri + 1) * height, ci * width:(ci + 1) * width] = frame
    return result


def pack_actions(actions, direction_count, columns):
    """緊密排：所有格子接在一起排成一條，見 docs/精靈圖規格.md 的「圖集排版」

    actions 是 [(名稱, [每個方向一組的格清單])]，方向的順序就是 meta 的 directions。
    回傳 (圖, {名稱: 起始格號}, 列數)。

    格號的換算和 src/world/sprite_sheet.gd 的 frame_rect 一樣：
        格號 = start + 方向 × 格數 + 格
        欄   = 格號 % columns
        列   = 格號 // columns
    一個方向的格子可以跨列，那正是省面積的原因：
    固定格子的排法要 columns × (動作數 × 方向數) 格，緊密排只要真的有內容的那些格。
    """
    cells = []
    starts = {}
    for name, per_direction in actions:
        if len(per_direction) != direction_count:
            raise ValueError("動作 %s 有 %d 個方向，應該是 %d 個"
                             % (name, len(per_direction), direction_count))
        counts = {len(frames) for frames in per_direction}
        if len(counts) != 1:
            raise ValueError("動作 %s 每個方向的格數不一樣：%s。緊密排靠 frames 算格號，五個方向要一樣多"
                             % (name, sorted(counts)))
        starts[name] = len(cells)
        for frames in per_direction:
            cells.extend(frames)
    if not cells:
        raise ValueError("一格都沒有，排不出圖集")
    height, width = cells[0].shape[:2]
    rows = -(-len(cells) // columns)
    result = np.zeros((height * rows, width * columns, 4), dtype=np.float32)
    for index, frame in enumerate(cells):
        row, column = divmod(index, columns)
        result[row * height:(row + 1) * height, column * width:(column + 1) * width] = frame
    return result, starts, rows


def load_png(path):
    """讀 PNG 成由上往下的陣列，Blender 內部像素是由下往上存的所以要翻轉"""
    import bpy
    image = bpy.data.images.load(path)
    width, height = image.size
    flat = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(flat)
    bpy.data.images.remove(image)
    return np.flipud(flat.reshape(height, width, 4)).copy()


def save_png(array, path):
    import bpy
    height, width = array.shape[:2]
    image = bpy.data.images.new("atlas_out", width, height, alpha=True)
    image.pixels.foreach_set(np.flipud(array).astype(np.float32).ravel())
    image.filepath_raw = path
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)
