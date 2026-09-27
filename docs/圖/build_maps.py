# 第一批新地圖：風車丘、潮聲沙岸、洄潮港，加萌芽草原往南的出口
# 用法：python3 build_maps.py <repo 路徑>
import json, math, random, sys, os

REPO = sys.argv[1] if len(sys.argv) > 1 else "/home/user/RealmOfFaded"
# 萌芽草原往南的出口接不接：世界地圖視窗在 700×232 的紙上擺不下六列，介面改好之前先不接
CONNECT_MEADOW = "--connect" in sys.argv
MAPS = os.path.join(REPO, "data/maps")
FOOT = json.load(open(os.path.join(REPO, "data/props.json")))["footprints"]


def r2(v):
    return round(v, 2)


def footprint_rects(prop):
    """擺設擋住的矩形，照 prop_footprints.gd 的做法近似：方形邊長 2×r×0.8862，矩形照 90 度轉"""
    f = FOOT.get(prop["model"])
    if not f or not f.get("blocks"):
        return []
    parts = f.get("parts") or [f]
    out = []
    rot = prop.get("rotation_y", 0) % 360
    sc = prop.get("scale", 1.0)
    x0, z0 = prop["position"]
    for p in parts:
        if p.get("shape") == "square":
            h = p["radius"] * 0.8862 * sc
            hx = hz = h
            ox, oz = 0, 0
        else:
            hx, hz = p["half"][0] * sc, p["half"][1] * sc
            ox, oz = (p.get("offset", [0, 0])[0] * sc, p.get("offset", [0, 0])[1] * sc)
            if p.get("shape") == "square":
                pass
            a = math.radians(rot)
            c, s = abs(math.cos(a)), abs(math.sin(a))
            hx, hz = hx * c + hz * s, hx * s + hz * c
            ca, sa = math.cos(a), math.sin(a)
            ox, oz = ox * ca + oz * sa, -ox * sa + oz * ca
        out.append((x0 + ox - hx, z0 + oz - hz, x0 + ox + hx, z0 + oz + hz))
    return out


def seg_dist(p, a, b):
    ax, az = a
    bx, bz = b
    px, pz = p
    dx, dz = bx - ax, bz - az
    L = dx * dx + dz * dz
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (pz - az) * dz) / L))
    return math.hypot(px - (ax + t * dx), pz - (az + t * dz))


def path_dist(p, paths):
    best = 1e9
    for line in paths:
        for i in range(len(line) - 1):
            best = min(best, seg_dist(p, line[i], line[i + 1]))
    return best


def rect_dist(p, r):
    x, z = p
    dx = max(r[0] - x, 0, x - r[2])
    dz = max(r[1] - z, 0, z - r[3])
    return math.hypot(dx, dz)


def edge_blockers(rng, half, portals, openings=()):
    """沿四邊排一段一段深淺不一的矩形，照萌芽草原的做法；傳送點前後 8 公尺壓淺；openings 那幾段不排"""
    out = []
    lo, hi = -half, half

    def near_portal(x, z):
        return any(math.hypot(x - p[0], z - p[1]) < 9.0 for p in portals)

    for side in ("n", "s", "w", "e"):
        t = lo
        while t < hi:
            L = rng.uniform(3.0, 7.0)
            t2 = min(hi, t + L)
            mid = (t + t2) / 2
            depth = rng.uniform(2.5, 10.0)
            if side in ("n", "s"):
                x, z = mid, (lo if side == "n" else hi)
            else:
                x, z = (lo if side == "w" else hi), mid
            if near_portal(x, z):
                depth = rng.uniform(1.6, 2.4)
            skip = any(o[0] == side and o[1] <= mid <= o[2] for o in openings)
            if not skip:
                a, b = t - 0.1, t2 + 0.1
                a, b = max(lo, a), min(hi, b)
                if side == "n":
                    out.append({"type": "rect", "min": [r2(a), lo], "max": [r2(b), r2(lo + depth)]})
                elif side == "s":
                    out.append({"type": "rect", "min": [r2(a), r2(hi - depth)], "max": [r2(b), hi]})
                elif side == "w":
                    out.append({"type": "rect", "min": [lo, r2(a)], "max": [r2(lo + depth), r2(b)]})
                else:
                    out.append({"type": "rect", "min": [r2(hi - depth), r2(a)], "max": [hi, r2(b)]})
            t = t2
    return out


def blocked(p, blockers, water, grow=0.0):
    for b in blockers:
        r = (b["min"][0], b["min"][1], b["max"][0], b["max"][1])
        if rect_dist(p, r) <= grow:
            return True
    for w in water:
        r = (w["min"][0], w["min"][1], w["max"][0], w["max"][1])
        if rect_dist(p, r) <= grow:
            return True
    return False


def scatter(rng, props, model, count, half, avoid, scale=(1.0, 1.0), rot=True, clear=2.6, spacing=3.0):
    """範圍內零星撒擺設，避開路、傳送點、水、邊界、別的擺設"""
    placed = 0
    tries = 0
    while placed < count and tries < count * 200:
        tries += 1
        p = (rng.uniform(-half + 3, half - 3), rng.uniform(-half + 3, half - 3))
        if not avoid(p, clear):
            continue
        if any(math.hypot(p[0] - q["position"][0], p[1] - q["position"][1]) < spacing for q in props):
            continue
        props.append({"model": model, "position": [r2(p[0]), r2(p[1])], "rotation_y": r2(rng.uniform(0, 360)) if rot else 0,
                      "scale": r2(rng.uniform(*scale))})
        placed += 1


def make_avoid(paths, portals, blockers, water, keep_out):
    def avoid(p, clear):
        if path_dist(p, paths) < clear:
            return False
        if any(math.hypot(p[0] - q[0], p[1] - q[1]) < 6.0 for q in portals):
            return False
        if blocked(p, blockers, water, grow=1.6):
            return False
        for c, r in keep_out:
            if math.hypot(p[0] - c[0], p[1] - c[1]) < r:
                return False
        return True
    return avoid


# ---------------------------------------------------------------- 風車丘

def windmill_hills():
    rng = random.Random(20260927)
    half = 48.0
    north = (-6.0, -43.5)
    south = (6.0, 43.5)
    blockers = edge_blockers(rng, half, [north, south])
    path_main = [[-6, -43], [-8, -32], [-3, -20], [5, -8], [3, 5], [-4, 17], [-1, 29], [5, 37], [6, 43]]
    if not CONNECT_MEADOW:
        path_main = path_main[1:]
    path_mill = [[3, 5], [13, 13], [21, 22], [25, 27]]
    paths = [path_main, path_mill]
    props = []
    # 三座風車立在西邊的風車田，離路八公尺以上
    for pos, rot in [((-28, -26), 20), ((-20, -6), -15), ((-34, 6), 40)]:
        props.append({"model": "generated/models/towns/dawn/windmill", "position": list(pos), "rotation_y": rot, "scale": 1.0})
    # 乾草場和農舍
    props += [
        {"model": "generated/models/towns/dawn/house_2", "position": [-27, 24], "rotation_y": 0, "scale": 1.0},
        {"model": "generated/models/towns/dawn/house_1", "position": [-17, 31], "rotation_y": 0, "scale": 1.0},
        {"model": "generated/models/towns/parts/well", "position": [-19, 21.5], "rotation_y": 0, "scale": 1.0},
        {"model": "generated/models/towns/street/cart", "position": [-23, 19.5], "rotation_y": 30, "scale": 1.3},
        {"model": "generated/models/towns/street/barrels", "position": [-31, 21], "rotation_y": 90, "scale": 1.0},
        {"model": "generated/models/towns/furniture/crates", "position": [-13.2, 28.6], "rotation_y": 12, "scale": 1.0},
        # 老磨坊的空地，王在這裡
        {"model": "generated/models/towns/dawn/windmill", "position": [31, 35], "rotation_y": -30, "scale": 0.9},
        {"model": "generated/models/towns/furniture/crates", "position": [21, 32], "rotation_y": 25, "scale": 1.0},
        {"model": "generated/models/towns/street/barrels", "position": [31, 27.5], "rotation_y": -10, "scale": 1.0},
        # 路邊的路標
        {"model": "generated/models/townkit/signpost", "position": [-2, 31.5], "rotation_y": 0, "scale": 1.0},
    ]
    # 東邊麥田用一排矮樹叢隔成兩塊，中間留缺口；townkit 的樹籬一段八千面，十五段就多一百七十次繪製，所以用卡片樹叢
    for x in [11, 14, 17, 28, 31, 34]:
        props.append({"model": "generated/models/shrub", "position": [x, -8.5], "rotation_y": r2(rng.uniform(0, 360)), "scale": 1.0})
    for z in [-29, -26, -18]:
        props.append({"model": "generated/models/shrub", "position": [9.5, z], "rotation_y": r2(rng.uniform(0, 360)), "scale": 1.0})
    water = []
    portals_xy = [north, south]
    keep_out = [((26, 30), 6.0), ((-24, -14), 3.0), ((22, -20), 3.0), ((22, 6), 3.0), ((-26, 6), 3.0), ((-20, 26), 3.0)]
    avoid = make_avoid(paths, portals_xy, blockers, water, keep_out + [((p["position"][0], p["position"][1]), 5.5) for p in props if "windmill" in p["model"] or "house" in p["model"]])
    scatter(rng, props, "generated/models/tree_broadleaf", 22, half, avoid, (0.95, 1.3))
    scatter(rng, props, "generated/models/shrub", 18, half, avoid, (0.85, 1.2), spacing=2.4)
    scatter(rng, props, "generated/models/boulder", 10, half, avoid, (1.0, 1.4))
    m = {
        "name": "風車丘",
        "scene": "meadow",
        "safe_zone": False,
        "level_range": [5, 10],
        "warp_allowed": True,
        "bounds": {"min": [-half, -half], "max": [half, half]},
        "player_spawn": [-6.0, -38.0],
        "paths": paths,
        "ground": {
            "outside": "dark",
            "dry_amount": 0.62,
            "relief": {"edge_height": 0.0, "edge_span": 13.0, "edge_start": 1.5},
            "areas": [
                {"layer": "dry", "shape": "circle", "center": [-26, -18], "radius": 12, "edge": 3.0},
                {"layer": "dry", "shape": "circle", "center": [-24, 1], "radius": 10, "edge": 3.0},
                {"layer": "dry", "shape": "circle", "center": [-35, -6], "radius": 8, "edge": 3.0},
                {"layer": "dry", "shape": "circle", "center": [22, -22], "radius": 11, "edge": 2.5},
                {"layer": "dry", "shape": "circle", "center": [32, -16], "radius": 8, "edge": 2.5},
                {"layer": "dry", "shape": "circle", "center": [23, 4], "radius": 10, "edge": 2.5},
                {"layer": "dry", "shape": "circle", "center": [33, 9], "radius": 7, "edge": 2.5},
                {"layer": "dirt", "shape": "circle", "center": [-22, 24], "radius": 7, "edge": 2.5},
                {"layer": "dirt", "shape": "circle", "center": [-16, 30], "radius": 4.5, "edge": 2.0},
                {"layer": "dirt", "shape": "circle", "center": [26, 30], "radius": 4.5, "edge": 1.5},
            ],
            "cover": {"grass_tuft": 2200, "flower_white": 50, "flower_pink": 30, "flower_blue": 30, "pebbles": 40,
                      "puddle": 4, "moss": 10},
            "flower_patches": [[-8, -28, "flower_white"], [16, 20, "flower_pink"], [-30, -2, "flower_blue"]],
        },
        "water": water,
        "spawns": [],
        "npcs": [],
        "portals": ([{"id": "north_road", "position": list(north), "radius": 1.5, "to_map": "meadow",
                      "to_position": [-6.0, 40.0]}] if CONNECT_MEADOW else []) + [
            {"id": "south_road", "position": list(south), "radius": 1.5, "to_map": "tide_shore", "to_position": [6.0, -40.0]},
        ],
        "zones": [
            {"id": "north_slope", "name": "北坡", "center": [-6, -37], "radius": 7, "hint": "草原過來的坡，沒有怪"},
            {"id": "windmill_field", "name": "風車田", "center": [-24, -10], "radius": 15, "hint": "三座風車立在田中間"},
            {"id": "wheat_north", "name": "北麥田", "center": [24, -21], "radius": 12, "hint": "樹籬圍起來的麥田"},
            {"id": "wheat_south", "name": "南麥田", "center": [24, 5], "radius": 12, "hint": "樹籬南邊的麥田"},
            {"id": "hay_yard", "name": "乾草場", "center": [-22, 25], "radius": 10, "hint": "農舍和水井"},
            {"id": "old_mill", "name": "老磨坊", "center": [26, 30], "radius": 6, "hint": "小路盡頭，王在這裡"},
            {"id": "behind_mill", "name": "風車背後", "center": [-32, -32], "radius": 3, "hint": "第一座風車後面的角落", "hidden": True},
        ],
        "props": props,
        "blockers": blockers,
    }
    return m


# ---------------------------------------------------------------- 潮聲沙岸

def tide_shore():
    rng = random.Random(20260928)
    half = 48.0
    north = (6.0, -43.5)
    east = (43.5, -6.0)
    # 南邊三分之一是海，岸線一段一段進退；海一路延伸到地圖外
    # 海是一整塊，每一塊水面四邊都有浪花，拼起來會在接縫多一條白線；岸線的進退交給礁岩和沙丘
    water = [
        {"min": [-140, 29], "max": [140, 140]},
    ]
    blockers = edge_blockers(rng, half, [north, east])
    # 南邊那一段交給海，邊界的矩形不要伸進海裡
    trimmed = []
    for b in blockers:
        if b["min"][1] >= 28:
            continue
        if b["max"][1] > 29:
            b = {"type": "rect", "min": b["min"], "max": [b["max"][0], 29.0]}
        trimmed.append(b)
    blockers = trimmed
    path_main = [[6, -43], [3, -32], [-4, -20], [-3, -8], [6, -2], [18, -6], [30, -5], [43, -6]]
    path_spit = [[-3, -8], [-14, 2], [-24, 20], [-32, 21.5]]
    paths = [path_main, path_spit]
    props = []
    # 礁岩：岸邊一排大石頭
    reef = [(12, 21), (15, 23), (19, 22), (22, 24.5), (25, 21.5), (4, 23.5), (-6, 24), (36, 21), (40, 22.5)]
    for x, z in reef:
        props.append({"model": "generated/models/boulder", "position": [x, z], "rotation_y": r2(rng.uniform(0, 360)),
                      "scale": r2(rng.uniform(2.0, 2.8))})
    # 岸邊幾叢大礁岩把直直的海岸線切開，看起來一段一段進退
    for x, z in [(-44, 26), (-40.5, 27.2), (-20, 27), (-16.8, 26.4), (30, 26.5), (33.5, 27.3), (44, 25.5)]:
        props.append({"model": "generated/models/boulder", "position": [x, z], "rotation_y": r2(rng.uniform(0, 360)),
                      "scale": r2(rng.uniform(2.6, 3.4))})
    # 退潮灘：地圖檔的水面是方的，一小塊水窪只剩一圈浪花像泳池，所以不畫水，用濕泥那一層畫退潮後的濕沙
    # 沉船殘骸：燈標沙嘴，王在這裡
    props += [
        {"model": "generated/models/towns/furniture/crates", "position": [-37, 18], "rotation_y": 35, "scale": 1.0},
        {"model": "generated/models/towns/street/barrels", "position": [-29, 25], "rotation_y": 80, "scale": 1.0},
        {"model": "generated/models/towns/street/barrel", "position": [-39, 23], "rotation_y": 0, "scale": 1.0},
        {"model": "generated/models/townkit/signpost", "position": [9, -3.5], "rotation_y": 0, "scale": 1.0},
    ]
    # 西邊礁岩底下是海蝕洞的洞口，第二批才開，現在用石頭封著
    for x, z in [(-44.5, 9.5), (-43.8, 12.2), (-44.6, 14.6)]:
        props.append({"model": "generated/models/boulder", "position": [x, z], "rotation_y": r2(rng.uniform(0, 360)),
                      "scale": 1.6})
    portals_xy = [north, east]
    keep_out = [((-34, 24), 5.0), ((-18, -24), 3), ((22, -24), 3), ((-22, 12), 3), ((16, 14), 3)]
    avoid = make_avoid(paths, portals_xy, blockers, water, keep_out)
    # 北邊沙丘才有樹和樹叢，岸邊只有石頭
    north_avoid = lambda p, c: p[1] < 0 and avoid(p, c)
    scatter(rng, props, "generated/models/tree_broadleaf", 12, half, north_avoid, (0.9, 1.2))
    scatter(rng, props, "generated/models/shrub", 20, half, lambda p, c: p[1] < 14 and avoid(p, c), (0.8, 1.15), spacing=2.4)
    scatter(rng, props, "generated/models/boulder", 12, half, lambda p, c: p[1] > -10 and avoid(p, c), (1.0, 1.5))
    m = {
        "name": "潮聲沙岸",
        "scene": "meadow",
        "safe_zone": False,
        "level_range": [9, 15],
        "warp_allowed": True,
        "bounds": {"min": [-half, -half], "max": [half, half]},
        "player_spawn": [6.0, -38.0],
        "paths": paths,
        "ground": {
            "outside": "dark",
            "layers": {"grass": "sand.png", "dirt": "wet_mud.png"},
            "mood_overrides": {"grass_tint": "#e8d2ae"},
            "dry_amount": 0.2,
            "relief": {"edge_height": 0.0, "edge_span": 13.0, "edge_start": 1.5},
            "areas": [
                {"layer": "dry", "shape": "circle", "center": [-26, -30], "radius": 16, "edge": 5.0},
                {"layer": "dry", "shape": "circle", "center": [0, -34], "radius": 13, "edge": 5.0},
                {"layer": "dry", "shape": "circle", "center": [26, -30], "radius": 15, "edge": 5.0},
                {"layer": "dry", "shape": "circle", "center": [-30, -8], "radius": 11, "edge": 5.0},
                {"layer": "dry", "shape": "circle", "center": [36, -14], "radius": 8, "edge": 4.0},
                {"layer": "dirt", "shape": "circle", "center": [-34, 22], "radius": 3.8, "edge": 1.5},
                {"layer": "dirt", "shape": "circle", "center": [-22, 12], "radius": 6, "edge": 4.0},
                {"layer": "dirt", "shape": "circle", "center": [-12, 18], "radius": 4.5, "edge": 3.5},
                {"layer": "dirt", "shape": "circle", "center": [4, 22], "radius": 5, "edge": 4.0},
            ],
            "carpet_rect": [[-48, -48], [48, -12]],
            "edge_tree": "broadleaf",
            "cover": {"grass_tuft": 900, "pebbles": 120, "moss": 12, "flower_white": 16, "puddle": 18},
            "flower_patches": [[-20, -30, "flower_white"], [26, -34, "flower_blue"]],
        },
        "water": water,
        "spawns": [],
        "npcs": [],
        "portals": [
            {"id": "north_road", "position": list(north), "radius": 1.5, "to_map": "windmill_hills", "to_position": [6.0, 40.0]},
            {"id": "east_road", "position": list(east), "radius": 1.5, "to_map": "tidewell_port", "to_position": [-26.0, 6.0]},
        ],
        "zones": [
            {"id": "dunes", "name": "沙丘", "center": [-18, -26], "radius": 13, "hint": "風車丘下來的沙丘"},
            {"id": "gull_slope", "name": "海風坡", "center": [22, -24], "radius": 12, "hint": "東邊的長草坡"},
            {"id": "tidal_flat", "name": "退潮灘", "center": [-20, 14], "radius": 10, "hint": "退潮後濕濕的沙灘"},
            {"id": "reef", "name": "礁岩", "center": [18, 18], "radius": 10, "hint": "岸邊的礁岩"},
            {"id": "beacon_spit", "name": "燈標沙嘴", "center": [-34, 22], "radius": 5, "hint": "小路盡頭，王在這裡"},
            {"id": "sea_cave_mouth", "name": "浪蝕洞口", "center": [-42, 12], "radius": 4, "hint": "封著的洞口，海蝕洞以後從這裡開", "hidden": True},
        ],
        "props": props,
        "blockers": blockers,
    }
    return m


# ---------------------------------------------------------------- 洄潮港

def tidewell_port():
    props = []
    wall = "generated/models/towns/street/wall"
    # 城牆：西、北、東三面，南邊是碼頭和海
    x_w, x_e, z_n, z_s = -30.0, 30.0, -28.0, 20.0
    for i in range(10):
        z = z_n + 3.2 + i * 6.4 - 0.0
        if z > z_s - 1:
            break
        if abs(z - 6.0) > 4.0:
            props.append({"model": wall, "position": [x_w, r2(z)], "rotation_y": 90, "scale": 0.82})
        props.append({"model": wall, "position": [x_e, r2(z)], "rotation_y": 90, "scale": 0.82})
    for i in range(10):
        x = x_w + 3.2 + i * 6.4
        if x > x_e - 1:
            break
        props.append({"model": wall, "position": [r2(x), z_n], "rotation_y": 0, "scale": 0.82})
    for pos in [(x_w, z_n), (x_e, z_n), (x_w, 18.6), (x_e, 18.6)]:
        props.append({"model": "generated/models/towns/street/wall_tower", "position": list(pos), "rotation_y": 0, "scale": 0.9})
    props.append({"model": "generated/models/townkit/gatehouse", "position": [x_w, 6.0], "rotation_y": 90, "scale": 1.0})
    # 學院：西北角，大廳面向南邊的廣場，高塔和觀星台在後面
    props += [
        {"model": "generated/models/towns/magic/academy_hall", "position": [-15.0, -19.5], "rotation_y": 0, "scale": 1.0},
        {"model": "generated/models/towns/magic/academy_tower", "position": [-24.5, -22.5], "rotation_y": 0, "scale": 1.0},
        {"model": "generated/models/towns/magic/observatory", "position": [-6.0, -22.0], "rotation_y": 0, "scale": 1.0},
        # 水晶廣場
        {"model": "generated/models/towns/magic/crystal_well", "position": [-15.0, -2.0], "rotation_y": 0, "scale": 1.0},
        {"model": "generated/models/towns/street/bench", "position": [-20.5, -2.0], "rotation_y": 90, "scale": 1.0},
        {"model": "generated/models/towns/street/bench", "position": [-9.5, -2.0], "rotation_y": -90, "scale": 1.0},
        {"model": "generated/models/towns/street/flower_pots", "position": [-19.5, -7.0], "rotation_y": 0, "scale": 1.0},
        {"model": "generated/models/towns/street/flower_pots", "position": [-10.5, -7.0], "rotation_y": 0, "scale": 1.0},
        # 西南碼頭邊的運河屋
        {"model": "generated/models/towns/magic/canal_house", "position": [-23.0, 13.5], "rotation_y": 0, "scale": 0.85},
        {"model": "generated/models/towns/magic/canal_house", "position": [-8.0, 13.5], "rotation_y": 0, "scale": 0.85},
        {"model": "generated/models/towns/parts/awning", "position": [-8.0, 9.4], "rotation_y": 0, "scale": 1.0},
        # 運河東岸：住家一排面向運河
        {"model": "generated/models/towns/magic/canal_house", "position": [8.0, -20.0], "rotation_y": 0, "scale": 0.85},
        {"model": "generated/models/towns/magic/canal_house", "position": [22.5, -20.0], "rotation_y": 0, "scale": 0.85},
        # 水晶廣場西邊、城牆腳下一間面向廣場
        {"model": "generated/models/towns/magic/canal_house", "position": [-25.5, -2.0], "rotation_y": 90, "scale": 0.85},
        # 運河西岸、學院前面一間
        {"model": "generated/models/towns/magic/canal_house", "position": [-5.5, -3.5], "rotation_y": -90, "scale": 0.8},
        # 東邊市集廣場
        {"model": "generated/models/towns/parts/market_stall", "position": [10.0, -3.0], "rotation_y": 10, "scale": 1.0},
        {"model": "generated/models/towns/parts/market_stall", "position": [20.0, -4.5], "rotation_y": -6, "scale": 1.0},
        {"model": "generated/models/towns/parts/market_stall", "position": [25.0, -1.0], "rotation_y": 8, "scale": 1.0},
        {"model": "generated/models/towns/parts/well", "position": [20.0, 1.5], "rotation_y": 0, "scale": 1.0},
        {"model": "generated/models/towns/street/cart", "position": [25.5, 2.5], "rotation_y": 60, "scale": 1.0},
        # 東南碼頭的倉庫
        {"model": "generated/models/towns/magic/canal_house", "position": [22.5, 13.5], "rotation_y": 0, "scale": 0.85},
        {"model": "generated/models/towns/magic/canal_house", "position": [8.5, 13.5], "rotation_y": 0, "scale": 0.85},
        {"model": "generated/models/towns/parts/awning", "position": [8.5, 9.4], "rotation_y": 0, "scale": 1.0},
    ]
    # 碼頭邊的貨：木箱木桶靠著海
    for pos, m, rot in [((-17, 18.6), "generated/models/towns/furniture/crates", 10), ((-13.5, 18.8), "generated/models/towns/street/barrels", 0),
                        ((14, 18.8), "generated/models/towns/street/barrels", 0), ((17.5, 18.6), "generated/models/towns/furniture/crates", -15),
                        ((27, 18.7), "generated/models/towns/street/barrel", 0), ((-27, 18.7), "generated/models/towns/street/barrel", 0)]:
        props.append({"model": m, "position": list(pos), "rotation_y": rot, "scale": 1.0})
    # 路燈沿主街
    for pos in [(-24, 3.8), (-4, 3.8), (4, 3.8), (26, 8.4), (-4, -8.3), (4, -8.3), (-24, -8.3), (24, -8.3),
                (-2.6, -18), (2.6, -18)]:
        props.append({"model": "generated/models/townkit/lamp_post", "position": list(pos), "rotation_y": 0, "scale": 1.0})
    # 城牆腳下的樹，照 footprint 擋
    for pos in [(-27, -15), (27, -15), (13, -25.5), (-3.5, -25.5), (27, 10.5), (-20.5, -12.8), (-9.5, -12.8),
                (5, -14.5), (18, -14.5), (-14.5, 12.5), (-27.5, 10)]:
        props.append({"model": "generated/models/tree_broadleaf", "position": list(pos), "rotation_y": 0, "scale": 1.0})
    # 運河從北牆流到南邊的海，兩條大街從上面過
    water = [
        {"min": [-160, 20], "max": [160, 140]},
        {"min": [-1.6, -29], "max": [1.6, -12.4]},
        {"min": [-1.6, -8.6], "max": [1.6, 4.4]},
        {"min": [-1.6, 8.6], "max": [1.6, 20]},
    ]
    # 城牆外看不見的邊界：地圖範圍比牆多一點，只有城門的通道出得去
    blockers = [
        {"type": "rect", "min": [-31.5, -29.5], "max": [-30.2, 3.6]},
        {"type": "rect", "min": [-31.5, 8.4], "max": [-30.2, 20.0]},
    ]
    m = {
        "name": "洄潮港",
        "scene": "town",
        "safe_zone": True,
        "level_range": [1, 99],
        "warp_allowed": True,
        "bounds": {"min": [-31.5, -27.2], "max": [29.2, 20.0]},
        "player_spawn": [-22.0, 6.0],
        "ground": {
            "paths": [
                {"points": [[-31, 6], [30, 6]], "width": 3.4, "layer": "stone"},
                {"points": [[-26, -10.5], [26, -10.5]], "width": 3.0, "layer": "stone"},
                {"points": [[-15, -14], [-15, 6]], "width": 3.0, "layer": "stone"},
                {"points": [[15, -16], [15, 6]], "width": 3.0, "layer": "stone"},
                {"points": [[-28, 18.2], [28, 18.2]], "width": 3.4, "layer": "stone"},
                {"points": [[-3, 6], [-3, 18.2]], "width": 2.4, "layer": "stone"},
                {"points": [[3, 6], [3, 18.2]], "width": 2.4, "layer": "stone"},
            ],
            "areas": [
                {"shape": "circle", "center": [-15, -2], "radius": 6.5, "layer": "stone", "edge": 0.6},
                {"shape": "rect", "min": [7, -7], "max": [27, 4], "layer": "stone", "edge": 0.6},
                {"shape": "rect", "min": [-30, 16.4], "max": [30, 20.5], "layer": "stone", "edge": 0.4},
            ],
            "town": {"plaza": [-15, -2, 6.5], "sapling": False, "outskirts": False, "banners": False, "greenery": False},
            "relief": {"edge_height": 0.0},
        },
        "water": water,
        "spawns": [],
        "npcs": [],
        "portals": [
            {"id": "west_gate", "position": [-30.0, 6.0], "radius": 1.2, "to_map": "tide_shore", "to_position": [40.0, -6.0]},
        ],
        "zones": [
            {"id": "academy", "name": "學院", "center": [-15, -20], "radius": 9, "hint": "學院大廳、高塔和觀星台"},
            {"id": "crystal_plaza", "name": "水晶廣場", "center": [-15, -2], "radius": 7, "hint": "城裡的廣場"},
            {"id": "canal", "name": "運河", "center": [0, -2], "radius": 5, "hint": "從北牆流到海裡"},
            {"id": "market", "name": "市集", "center": [17, -2], "radius": 8, "hint": "運河東邊的攤位"},
            {"id": "harbor", "name": "碼頭", "center": [0, 17], "radius": 10, "hint": "南邊靠海的碼頭"},
            {"id": "west_gate", "name": "西城門", "center": [-26, 6], "radius": 4, "hint": "往潮聲沙岸"},
        ],
        "props": props,
        "blockers": blockers,
    }
    return m


def patch_meadow():
    path = os.path.join(MAPS, "meadow.json")
    m = json.load(open(path))
    portal = {"id": "south_road", "position": [-6.0, 43.8], "radius": 1.5, "to_map": "windmill_hills", "to_position": [-6.0, -40.0]}
    m["portals"] = [p for p in m["portals"] if p["id"] != "south_road"] + [portal]
    # 出口那一段邊界壓淺，讓出一個小灣
    for b in m["blockers"]:
        if b["min"] == [-9.14, 42.45] and b["max"] == [-3.1, 48.0]:
            b["min"] = [-9.14, 46.2]
    branch = [[-2.0, 24.0], [-7.0, 30.0], [-8.0, 37.0], [-6.0, 43.0]]
    m["paths"] = [m["paths"][0], branch]
    for z in m["zones"]:
        pass
    if not any(z["id"] == "south_exit" for z in m["zones"]):
        m["zones"].append({"id": "south_exit", "name": "南邊出口", "center": [-7, 40], "radius": 4, "hint": "往風車丘"})
    return m


def dump(name, m):
    # 還沒接上萌芽草原的時候整條鏈走不到，先不畫在世界地圖上
    if not CONNECT_MEADOW and name != "meadow":
        m = dict(m)
        keys = list(m.keys())
        m["world_map"] = False
        m = {k: m[k] for k in keys[:keys.index("warp_allowed") + 1] + ["world_map"] + keys[keys.index("warp_allowed") + 1:]}
    with open(os.path.join(MAPS, name + ".json"), "w") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    dump("windmill_hills", windmill_hills())
    dump("tide_shore", tide_shore())
    dump("tidewell_port", tidewell_port())
    if CONNECT_MEADOW:
        dump("meadow", patch_meadow())
    print("ok")
