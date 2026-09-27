"""把 mp3 的標籤整個拿掉，只留聲音本身。

Suno 下載回來的檔案裡塞了 ID3v2 標籤和 C2PA 出處簽章，
裡面有歌曲網址、帳號、產生時間，還有一張封面圖，加起來好幾十 KB。
那些東西出貨給玩家沒有用，來源和授權記在 docs/資產清單.json 就夠了。

用法：

    python3 art_pipeline/audio/strip_tags.py assets/vendor/audio/music/*.mp3

不給檔名就處理 assets/vendor/audio/music/ 底下全部的 mp3。
改完要再跑一次 godot --headless --path . --import。
"""

import pathlib
import re
import sys

MUSIC_DIR = pathlib.Path("assets/vendor/audio/music")
# 標籤裡不該再出現的字，改完拿來自我檢查
LEAK_PATTERNS = [rb"suno", rb"c2pa", rb"jumbf", rb"restrainedgroupie", rb"DigiCert"]


def id3v2_size(data: bytes) -> int:
    """開頭那個 ID3v2 標籤佔幾個位元組，沒有標籤回傳 0"""
    if len(data) < 10 or data[:3] != b"ID3":
        return 0
    flags = data[5]
    # 長度是四個位元組的同步安全整數，每個位元組只用低七位
    size = 0
    for b in data[6:10]:
        size = (size << 7) | (b & 0x7F)
    total = 10 + size
    # 有 footer 旗標的話後面還有十個位元組
    if flags & 0x10:
        total += 10
    return total


def tail_tag_size(data: bytes) -> int:
    """結尾的 ID3v1 或 APEv2 標籤佔幾個位元組"""
    size = 0
    if len(data) >= 128 and data[-128:-125] == b"TAG":
        size = 128
    rest = data[: len(data) - size] if size else data
    if len(rest) >= 32 and rest[-32:-24] == b"APETAGEX":
        # APEv2 footer 的第 13 到 16 個位元組是整個標籤的長度，不含 header
        length = int.from_bytes(rest[-20:-16], "little")
        size += length + 32
    return size


def strip(path: pathlib.Path) -> str:
    data = path.read_bytes()
    before = len(data)
    head = id3v2_size(data)
    tail = tail_tag_size(data)
    body = data[head: len(data) - tail if tail else len(data)]
    # 第一個音框一定以 0xFF 開頭，切錯位置的話寧可不寫
    start = body.find(b"\xff")
    if start < 0 or start > 4096:
        raise SystemExit("%s 切完找不到音框，沒有動這個檔" % path)
    body = body[start:]
    leaked = [p.decode() for p in LEAK_PATTERNS if re.search(p, body, re.IGNORECASE)]
    if leaked:
        raise SystemExit("%s 切完還找得到 %s，沒有動這個檔" % (path, leaked))
    path.write_bytes(body)
    return "%s %d → %d KB，少了 %d KB" % (
        path.name, before // 1024, len(body) // 1024, (before - len(body)) // 1024)


def main() -> None:
    args = [pathlib.Path(a) for a in sys.argv[1:]]
    targets = args if args else sorted(MUSIC_DIR.glob("*.mp3"))
    if not targets:
        raise SystemExit("找不到任何 mp3")
    for path in targets:
        if id3v2_size(path.read_bytes()) == 0 and tail_tag_size(path.read_bytes()) == 0:
            print("%s 已經沒有標籤了" % path.name)
            continue
        print(strip(path))


if __name__ == "__main__":
    main()
