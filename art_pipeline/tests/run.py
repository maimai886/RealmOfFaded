"""
美術管線單元測試。
用法：blender -b --factory-startup --python-exit-code 1 -P art_pipeline/tests/run.py

有些測試量的是 Pillow 畫出來的圖，Blender 內建的 Python 沒有 Pillow，
那幾個模組會宣告 NEEDS_PILLOW，這裡自動改叫系統的 python3 跑同一支檔案，結果一起算進總數。
單獨跑一個模組：python3 art_pipeline/tests/run.py --only tests.test_ui_skin_quiet
"""
import importlib
import os
import subprocess
import sys
import traceback

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PIPELINE_DIR)

TEST_DIR = os.path.join(PIPELINE_DIR, "tests")


def has_pillow():
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def system_python():
    """找一個真的裝了 Pillow 的 python3，Blender 內建的沒有"""
    import shutil
    # Windows 上系統的直譯器叫 python 不叫 python3，而且 python3 可能是商店的空殼，
    # 所以兩個名字都試，真的 import 得到 PIL 的才算數
    candidates = ["/opt/homebrew/bin/python3", shutil.which("python3"), shutil.which("python"),
                  "/usr/local/bin/python3", "/usr/bin/python3"]
    for candidate in candidates:
        if not candidate or not os.path.exists(candidate):
            continue
        if subprocess.run([candidate, "-c", "import PIL"], capture_output=True).returncode == 0:
            return candidate
    return None


def run_module(module, file_name):
    """跑一個模組裡所有 test_ 開頭的函式，回傳跑了幾個、錯了幾個"""
    total = 0
    failed = 0
    for name in sorted(dir(module)):
        if not name.startswith("test_"):
            continue
        total += 1
        try:
            getattr(module, name)()
            print("  PASS %s.%s" % (file_name, name))
        except Exception:
            failed += 1
            print("  FAIL %s.%s" % (file_name, name))
            traceback.print_exc()
    return total, failed


def delegate(module_name):
    """這個直譯器沒有 Pillow，改叫系統的 python3 跑同一支檔案"""
    python = system_python()
    if python is None:
        print("  FAIL %s：找不到裝了 Pillow 的 python3" % module_name)
        return 1, 1
    # 子行程一律用 UTF-8 講話：Windows 的預設編碼是 cp950，中文訊息會解不開，整支測試直接當掉
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run([python, os.path.abspath(__file__), "--only", module_name],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    counted = 0
    for line in result.stdout.splitlines():
        if line.strip().startswith(("PASS ", "FAIL ")):
            counted += 1
    return counted, 0 if result.returncode == 0 else max(1, sum(
        1 for line in result.stdout.splitlines() if line.strip().startswith("FAIL ")))


def main():
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    total = 0
    failed = 0
    pillow = has_pillow()
    for file_name in sorted(os.listdir(TEST_DIR)):
        if not (file_name.startswith("test_") and file_name.endswith(".py")):
            continue
        module_name = "tests." + file_name[:-3]
        if only and module_name != only:
            continue
        module = importlib.import_module(module_name)
        if getattr(module, "NEEDS_PILLOW", False) and not pillow:
            counted, broke = delegate(module_name)
            total += counted
            failed += broke
            continue
        counted, broke = run_module(module, file_name)
        total += counted
        failed += broke
    print("%d 個測試，%d 個失敗" % (total, failed))
    if failed:
        raise SystemExit(1)


main()
