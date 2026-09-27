"""
批次把城鎮概念圖送 Meshy lite 圖轉 3D，一件 15 點。已經有 model.glb 的跳過，重跑不會重複花點數；
送出後沒等到結果就中斷的，task_id.txt 留著，下次接著等同一個工作，不會再送一次。
金鑰在 ignore_data/meshy_ai，只從檔案讀、只送到 api.meshy.ai，不印出來。
概念圖在 art_source/concepts/towns/<城鎮>_<名字>_1.png，原始模型下載到 ignore_data/meshy_raw/<城鎮>/<名字>/，
之後用 import_models.py 整理進 assets。做法和花費見 docs/城鎮建築產線.md

用法：python art_pipeline/meshy/generate.py [城鎮/名字 ...]
"""
import base64
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KEY = open(os.path.join(PROJECT_ROOT, "ignore_data", "meshy_ai"), encoding="utf-8").read().strip()
API = "https://api.meshy.ai/openapi/v1/image-to-3d"
OUT = os.path.join(PROJECT_ROOT, "ignore_data", "meshy_raw")
CONCEPTS = os.path.join(PROJECT_ROOT, "art_source", "concepts", "towns")

TEXTURE = {
    "dawn": "stylized hand-painted fantasy village, whitewashed plaster, terracotta tiles with blue edges, dark weathered wood, blue painted doors, soft painterly texture",
    "magic": "stylized hand-painted fantasy magic academy, whitewashed plaster, dark timber, slate blue roof tiles, warm glowing windows, soft painterly texture",
    "japan": "stylized hand-painted Japanese village, dark wood, white plaster, grey-blue kawara roof tiles, vermilion accents, soft painterly texture",
    "parts": "stylized hand-painted fantasy village prop, soft painterly texture",
    "furniture": "stylized hand-painted fantasy furniture, warm wood, soft painterly texture",
    "street": "stylized hand-painted fantasy village street prop, soft painterly texture",
    "keep": "stylized hand-painted fantasy fortress, rough grey limestone blocks, dark slate roof, dark wood, red cloth banners, soft painterly texture",
    "highbough": "stylized hand-painted fantasy treetop village, rough brown logs and planks, mossy green shingles, rope, soft painterly texture",
    "lanternford": "stylized hand-painted fantasy riverside church town, whitewashed walls, dark wooden posts, grey-green shingles and terracotta tiles, warm lanterns, soft painterly texture",
}
# lite 生出來屋頂皺成一團的可以改用標準版，一件 30 點；町屋試過標準版一樣皺，問題在概念圖的瓦片畫法，已經拿掉
STANDARD = {}
JOBS = [
    ("dawn", n, 8000) for n in ["inn", "smithy", "storage", "town_hall", "house_2"]
] + [
    ("magic", n, 8000) for n in ["academy_tower", "observatory", "academy_hall", "canal_house"]
] + [
    ("japan", n, 8000) for n in ["inn", "pagoda", "shrine"]
] + [
    ("parts", n, 3000) for n in ["market_stall", "awning", "balcony", "stairs", "well", "torii", "stone_lantern"]
] + [
    ("keep", n, 8000) for n in ["gatehouse", "barracks", "great_hall", "watchtower", "forge"]
] + [("keep", "oath_stone", 4000)] + [
    ("highbough", n, 6000) for n in ["tree_platform", "lookout", "stilt_hut", "ladder_post"]
] + [("highbough", "rope_bridge", 3000)] + [
    ("lanternford", n, 8000) for n in ["chapel", "almshouse", "covered_bridge", "bell_tower", "boathouse", "herb_shop"]
] + [
    ("japan", n, 8000) for n in ["dojo", "onmyo_office", "ninja_house", "ascetic_hall", "forge", "gate",
                                 "tea_house"]
] + [
    ("furniture", n, 3000) for n in ["counter", "shelf", "bookshelf", "table_set", "bed", "fireplace", "anvil_set",
                                     "crates", "altar", "desk", "weapon_rack", "low_table", "kakejiku", "sword_stand"]
] + [("dawn", "item_shop", 8000)] + [
    ("street", n, 3000) for n in ["bench", "barrel", "barrels", "cart", "wall", "wall_tower", "flower_pots"]
] + [
    ("dawn", "windmill", 5000), ("magic", "bridge", 4000), ("magic", "crystal_well", 3000),
]


def call(url, body=None):
    headers = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    for attempt in range(5):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(20)
                continue
            raise RuntimeError("HTTP %d %s" % (e.code, e.read().decode(errors="replace")[:300]))
        except urllib.error.URLError:
            time.sleep(10)
    raise RuntimeError("retries exhausted")


def run(job):
    town, name, polys = job
    folder = os.path.join(OUT, town, name)
    os.makedirs(folder, exist_ok=True)
    if os.path.exists(os.path.join(folder, "model.glb")):
        return "%s/%s 已有" % (town, name)
    image = os.path.join(CONCEPTS, "%s_%s_1.png" % (town, name))
    uri = "data:image/png;base64," + base64.b64encode(open(image, "rb").read()).decode()
    task_file = os.path.join(folder, "task_id.txt")
    if os.path.exists(task_file):
        task_id = open(task_file).read().strip()
    else:
        task_id = call(API, {"image_url": uri, "ai_model": STANDARD.get("%s/%s" % (town, name), "meshy-6-lite"), "should_texture": True, "enable_pbr": False,
                             "should_remesh": True, "target_polycount": polys, "topology": "triangle",
                             "texture_prompt": TEXTURE[town]})["result"]
        open(task_file, "w").write(task_id)
    while True:
        info = call(API + "/" + task_id)
        if info["status"] in ("SUCCEEDED", "FAILED", "CANCELED"):
            break
        time.sleep(15)
    json.dump({k: v for k, v in info.items() if k not in ("model_urls", "texture_urls", "thumbnail_url")},
              open(os.path.join(folder, "task.json"), "w"), indent=1)
    if info["status"] != "SUCCEEDED":
        os.remove(task_file)
        return "%s/%s 失敗 %s" % (town, name, info.get("task_error"))
    urllib.request.urlretrieve(info["model_urls"]["glb"], os.path.join(folder, "model.glb"))
    if info.get("thumbnail_url"):
        urllib.request.urlretrieve(info["thumbnail_url"], os.path.join(folder, "thumb.png"))
    return "%s/%s 好了 %s 點" % (town, name, info.get("consumed_credits"))


if __name__ == "__main__":
    only = sys.argv[1:]
    jobs = [j for j in JOBS if not only or "%s/%s" % (j[0], j[1]) in only]
    # Premium 方案同時最多 30 個工作，留一點餘裕
    with ThreadPoolExecutor(20) as pool:
        for result in pool.map(run, jobs):
            print(result, flush=True)
