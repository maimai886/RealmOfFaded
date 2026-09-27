# M0 專案骨架與美術管線 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建好 Sproutia 的 Godot 專案骨架和兩套測試器，打通「Blender 腳本 → 5 方向圖集和地形磚 → Godot 裡顯示 8 方向角色」這條管線。

**Architecture:** Blender 在背景跑 Python，組出 Q 版模型、卡通材質和描邊，用正交相機算出 5 方向畫格，再用 numpy 打包成圖集 PNG 和 meta JSON。地形磚輸出 .glb。Godot 端讀 meta 建出 SpriteFrames，依「移動方向減掉相機角度」選 8 方向，右側 3 個方向用水平翻轉。

**Tech Stack:** Godot 4.7.2 GDScript（Mobile 渲染器）、Blender 5.2.1 Python（EEVEE、numpy 2.3）

**Spec:** `docs/歷史/design.md`

**原型來源：** 本計畫的所有程式碼都已經在原型目錄 `/private/tmp/claude-501/-Users-mai-Desktop-project-ohspace/b5d4b66d-5328-46d9-9e11-3094386faffb/scratchpad/proto/` 跑過，測試通過、畫面也截圖確認過。每個 Task 列出的檔案都照原型目錄裡的同名路徑建立，內容不變。

## Global Constraints

- 專案根目錄：`~/Desktop/project/Sproutia`
- Godot 執行檔：`/Applications/Godot.app/Contents/MacOS/Godot`；Blender 執行檔：`/Applications/Blender.app/Contents/MacOS/Blender`
- Blender 一律加 `-b --factory-startup --python-exit-code 1`，否則 Python 出錯時結束碼仍然是 0
- Blender 的色值是線性空間，調色板一律用 `srgb("#RRGGBB")` 填
- 圖集只算圖 5 個方向，順序固定為 `S, SW, W, NW, N`；Godot 方向編號 0~7 從面向鏡頭開始順時針
- 所有尺寸共用 `PX_PER_M = 64`，Blender 相機仰角 35°
- M0 不用 class_name，互相引用一律用 preload，因為 `--script` 模式可能還沒有全域類別快取
- 程式註解不用括號補充，直接白話寫
- commit 只提供訊息文字，不自己執行 git commit

---

### Task 1：Godot 專案骨架和測試器

**Files:**
- Create: `project.godot`、`.gitignore`
- Create: `tests/test_case.gd`、`tests/run_tests.gd`

**Interfaces:**
- Produces：測試檔寫成 `extends "res://tests/test_case.gd"`，方法名稱以 `test_` 開頭。可用的斷言有 `assert_eq(actual, expected, message)`、`assert_true(cond, message)`、`assert_near(a, b, tol, message)`。執行器有失敗時結束碼為 1

- [ ] **Step 1：建立檔案**。`.gitignore` 內容：
```
.godot/
art_pipeline/_build/
__pycache__/
.DS_Store
```
- [ ] **Step 2：確認失敗時會回報**。暫時建立 `tests/test_zz_fail.gd`：
```gdscript
extends "res://tests/test_case.gd"
func test_should_fail() -> void:
	assert_eq(1, 2, "故意失敗")
```
Run: `Godot --headless --path . --script res://tests/run_tests.gd; echo $?`
Expected：`FAIL test_zz_fail.gd.test_should_fail`，結束碼 1
- [ ] **Step 3：刪掉 `tests/test_zz_fail.gd` 再跑一次**。Expected：`0 個測試，0 個失敗`，結束碼 0
- [ ] **Step 4：提供 commit 訊息** `chore: Godot 專案骨架與測試器`

### Task 2：8 方向計算和圖集讀取

**Files:**
- Create: `src/world/facing.gd`、`src/world/sprite_sheet.gd`
- Test: `tests/test_facing.gd`、`tests/test_sprite_sheet.gd`

**Interfaces:**
- Produces：
  - `Facing.direction_index(direction: Vector3, camera_yaw: float) -> int`，回傳 0~7
  - `Facing.sheet_direction(index: int) -> Array`，回傳 `[圖集方向 0~4, flip_h]`
  - `SpriteSheet.SPRITES_DIR = "res://assets/generated/sprites/"`
  - `SpriteSheet.load_meta(sprite_name: String) -> Dictionary`
  - `SpriteSheet.build_frames(meta: Dictionary, texture: Texture2D) -> SpriteFrames`，動畫名稱是 `"<動作>_<方向0~4>"`
  - `SpriteSheet.feet_offset(meta: Dictionary) -> Vector2`
- meta JSON 格式：`{name, atlas, frame_size:[w,h], origin:[x,y], px_per_m, directions:[5 個], animations:{<名稱>:{row, frames, fps, loop}}}`，每個動作占連續 5 列

- [ ] **Step 1：先寫兩個測試檔**，內容照原型
- [ ] **Step 2：跑測試**。Expected：FAIL，因為 preload 的腳本還不存在
- [ ] **Step 3：建立 `facing.gd`、`sprite_sheet.gd`**
- [ ] **Step 4：跑測試**。Expected：`6 個測試，0 個失敗`
- [ ] **Step 5：提供 commit 訊息** `feat: 8 方向計算與圖集 SpriteFrames 建構`

### Task 3：Blender 管線共用模組

**Files:**
- Create: `art_pipeline/.gdignore`（空檔）、`art_pipeline/config.py`、`art_pipeline/{common,characters,monsters,props,tests}/__init__.py`（空檔）
- Create: `art_pipeline/common/projection.py`、`atlas.py`、`scene.py`、`toon.py`、`sprite_render.py`
- Test: `art_pipeline/tests/run.py`、`test_atlas.py`、`test_projection.py`

**Interfaces:**
- Produces：
  - `projection.feet_pixel(frame_px, target_height, px_per_m, elevation_deg) -> [x, y]`
  - `projection.facing_angle_deg(direction_index) -> float`，每個方向 -45°
  - `atlas.pack_grid(rows) -> ndarray`、`atlas.load_png(path)`、`atlas.save_png(array, path)`
  - `scene.reset_scene()`、`scene.add_lights()`（太陽光關閉陰影）、`scene.setup_sprite_camera(frame_px, target_height) -> origin`、`scene.add_empty(name, parent, location)`、`scene.add_sphere(name, parent, location, scale, material, segments, rings)`、`scene.add_cylinder(name, parent, location, radius, depth, material, vertices)`
  - `toon.srgb(hex) -> (r,g,b,1)`、`toon.toon_material(name, color, shadow=0.55)`、`toon.add_outline(obj)`、`toon.outline_all(objects)`
  - `sprite_render.render_sprite_set(name, facing, poser, animations, frame_px, target_height) -> meta`

- [ ] **Step 1：先寫測試檔和 `tests/run.py`**
- [ ] **Step 2：跑測試** `Blender -b --factory-startup --python-exit-code 1 -P art_pipeline/tests/run.py`。Expected：FAIL，因為找不到 common 模組
- [ ] **Step 3：建立 config 和 common 各模組**
- [ ] **Step 4：再跑一次**。Expected：`4 個測試，0 個失敗`，結束碼 0
- [ ] **Step 5：提供 commit 訊息** `feat: Blender 美術管線共用模組`

### Task 4：初心者、果凍球、地形磚產生器

**Files:**
- Create: `art_pipeline/characters/humanoid.py`、`characters/novice.py`、`monsters/jelly.py`、`props/terrain_tiles.py`、`build_all.py`
- Output: `assets/generated/sprites/novice.{png,json}`、`jelly.{png,json}`；`assets/generated/models/tile_{grass,dirt,stone}.glb`

**Interfaces:**
- Consumes：Task 3 的所有 common 函式
- Produces：
  - `humanoid.build_humanoid(name, palette) -> rig`，rig 的鍵有 `facing, root, neck, arm_L, arm_R, leg_L, leg_R`
  - `humanoid.pose(rig, anim, t)`，支援 `idle`、`walk`
  - 初心者：128px，動作 idle 4 格 6fps、walk 8 格 12fps
  - 果凍球：96px，動作同上，walk 10fps
  - 地形磚 2×2 公尺，頂面在高度 0，內部頂點隨機起伏但邊緣平整
  - `build_all.py -- --only <目標>` 可以重複指定，目標名稱打錯會列出可用清單並結束

- [ ] **Step 1：建立四個產生器和 `build_all.py`**
- [ ] **Step 2：確認打錯目標會報錯** `Blender ... -P art_pipeline/build_all.py -- --only nope; echo $?`。Expected：列出可用目標，結束碼不是 0
- [ ] **Step 3：完整產生** `Blender ... -P art_pipeline/build_all.py`。Expected：`[build] done`，大約 1 分鐘，輸出上面列的 7 個檔案
- [ ] **Step 4：用 Read 看 `novice.png` 和 `jelly.png`**。確認 5 列 idle 加 5 列 walk、方向依序是下、左下、左、左上、上、有描邊、背景透明、表面沒有塊狀髒斑
- [ ] **Step 5：跑 Task 3 的管線測試**，確認沒有被影響
- [ ] **Step 6：提供 commit 訊息** `feat: 初心者、果凍球圖集與地形磚產生器`

### Task 5：Godot 預覽場景

**Files:**
- Create: `src/world/directional_sprite.gd`、`src/dev/sprite_viewer.gd`、`scenes/dev/sprite_viewer.tscn`

**Interfaces:**
- Consumes：Task 2 的 `Facing`、`SpriteSheet`；Task 4 的素材
- Produces：`DirectionalSprite` 繼承 AnimatedSprite3D，必須放在角色 Node3D 底下當子節點
  - `setup(sprite_name: String)`
  - `play_action(action: String, direction: int)`，只換方向時會接續原本的畫格
  - `face_towards(move_direction: Vector3, camera_yaw: float)`
  - 每幀把自己放在「父節點位置 + 鏡頭方向 × `DEPTH_NUDGE` 0.6」，避免腳尖陷進地面

- [ ] **Step 1：建立三個檔案**
- [ ] **Step 2：匯入素材** `Godot --headless --path . --import`。Expected：沒有 error
- [ ] **Step 3：跑單元測試**。Expected：`6 個測試，0 個失敗`
- [ ] **Step 4：截圖** `Godot --path . --resolution 1280x720 --write-movie <暫存區>/shots/viewer.png --fixed-fps 30 --quit-after 15`
- [ ] **Step 5：用 Read 看最後一張截圖**。確認有草地、泥土、石板地面，8 個初心者在圓周上都面朝外走，右側 3 個是翻轉圖，2 隻果凍球，腳底沒有被切掉，顏色飽和
- [ ] **Step 6：提供 commit 訊息** `feat: M0 素材預覽場景`

### Task 6：開發指令文件

**Files:**
- Create: `docs/開發指令.md`

- [ ] **Step 1：寫下以下指令和用途**：產生全部或單項素材、跑管線測試、匯入素材、跑 Godot 測試、Movie Maker 截圖、用編輯器開專案（`open -a Godot --args --path ~/Desktop/project/Sproutia -e`）
- [ ] **Step 2：從頭依文件跑一遍**。Expected：管線測試 4 過、Godot 測試 6 過、截圖正常
- [ ] **Step 3：提供 commit 訊息** `docs: 開發指令`
