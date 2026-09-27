# Sproutia：類 RO 的 2.5D 手機 + 電腦 RPG（第一階段：單機可玩版）

**這是 2026-09-13 的原始設計，只留著看當初的起點。** M0 到 M5 已經做完而且做法早就不一樣了，
現行規格看 `docs/遊戲總規格.md`，現況看 `docs/進度.md`，M6 以後的規劃看 `docs/未來方向.md`。
這份裡的頭身比、鏡頭、三條職業線、單機優先全部已經被推翻。

## Context

使用者想做一款玩法和風格類似仙境傳說（RO）的 2.5D 遊戲，手機和電腦都能玩。已確認的決定：

- **引擎**：Godot 4.7.2（剛升級），一套程式碼輸出 Mac / Windows / Android / iOS
- **連線**：第一階段先做單機，程式架構預留之後接伺服器
- **美術**：用 Blender 5.2.1 腳本自動產生。流程是 3D 低多邊形 Q 版模型 → 卡通描邊算圖 → 2D 多方向圖片。地圖道具輸出 .glb
- **玩法**：手動戰鬥（沒有自動掛機）、基本等級和職業等級分開、一轉二轉、屬性點、背包裝備、技能樹、城鎮與 NPC
- **職業**：初心者 → 劍侍→聖劍士、術士→巫師、斥候→獵人
- **操作**：電腦用滑鼠點地移動、點怪攻擊、F1~F9 放技能。手機用左下虛擬搖桿，右下攻擊鍵和技能鍵，點怪鎖定目標
- **位置**：`~/Desktop/project/Sproutia`，全新的獨立專案

環境：Xcode、Android SDK、Java 19 都已經有了。**Godot 輸出模板還沒裝**，到 M6 需要下載時先徵求使用者同意。
版權：不用任何 RO 原版素材或專有名詞（波利、普隆德拉等），怪物和城鎮都自己取名。

---

## 架構原則

1. **邏輯層和表現層分開**：`src/core/` 放純邏輯（數值、戰鬥公式、背包、技能樹），只繼承 RefCounted，不依賴場景節點。之後做連線版時，伺服器（Godot headless）可以直接沿用這份邏輯。
2. **所有操作都是指令**：電腦輸入和手機輸入都轉成同一組指令（`MoveTo` / `MoveDir` / `Attack` / `UseSkill` / `PickUp` / `Interact`），交給角色控制器執行。之後連線版只要把指令改成送往伺服器。
3. **資料驅動**：職業、技能、道具、怪物、掉落表、地圖、NPC 對話和商店都寫在 `data/*.json`。之後加內容只要改資料檔，不用改程式。
4. **存檔格式就是未來資料庫的格式**：存到 `user://save.json`，結構照「帳號 → 角色 → 背包 / 裝備 / 技能 / 倉庫」設計。

## 專案結構

```
Sproutia/
  project.godot            # Mobile 渲染器、canvas_items 縮放、手機橫向
  docs/歷史/design.md           # 本設計的正式版
  art_pipeline/            # Blender Python 腳本，放 .gdignore 讓 Godot 不匯入
    common/                # 卡通材質、描邊、算圖相機、打光、圖集打包
    characters/            # Q 版人形參數化產生器 + 各職業外觀 + 動作關鍵格
    monsters/              # 各怪物產生器
    props/                 # 地形磚、樹、石頭、房屋、城牆、地城磚
    icons/                 # 道具和技能圖示
    build_all.py           # 一鍵產生全部素材
  assets/generated/        # sprites/（圖集 PNG + meta JSON）、models/（.glb）、icons/
  data/                    # jobs, skills, items, monsters, drops, exp_tables, elements, maps/, npcs/
  src/
    core/                  # registry、stats、formulas、leveling、inventory、equipment、skill_tree、combat、job_change、save_system
    world/                 # map_loader、entity、player、monster(AI)、npc、ground_item、portal、spawner、actors/（sprite_actor、model_actor、actor_factory）、camera_rig
    input/                 # commands、pc_input、touch_input、virtual_joystick
    ui/                    # hud、hotbar、status、inventory、equipment、skill_tree、shop、storage、dialog、job_change
    effects/               # 技能特效（CPUParticles3D，手機相容）、傷害數字
  tests/                   # run_tests.gd 自製輕量測試器 + test_*.gd
```

## 關鍵系統設計

### 2.5D 表現
- 世界是 3D 的：地圖用 Blender 做的 .glb 零件依 `data/maps/*.json` 擺出來，NavigationRegion3D 在執行時烘焙導航網格
- 相機固定斜俯角約 45°、透視投影，跟著玩家移動。電腦版可以用右鍵拖曳旋轉視角，手機版固定
- 角色和怪物用 `Sprite3D` 紙片，由 `actors/sprite_actor.gd` 依「面向減掉相機角度」挑 8 方向中的一格；圖集格式見 docs/精靈圖規格.md，還沒有圖的角色由 `actor_factory.gd` 退回 3D 模型
- **只算圖 5 個方向**（下、左下、左、左上、上），右側 3 個方向用水平翻轉。這是 RO 的做法，可以省 40% 美術量

### 美術管線（Blender 背景執行）
- 執行方式：`blender -b -P art_pipeline/build_all.py -- --only characters/swordman`
- **Q 版人形**：用基本形體組出 2.5 頭身角色，加簡單骨架。各職業換配色、服裝零件和武器（劍、法杖、弓）
- **動作**：用程式寫關鍵格，包含站立、走路、攻擊（揮砍 / 施法 / 射箭）、受傷、死亡、坐下
- **卡通風格**：EEVEE 算圖，Color Ramp 做 2～3 階色，反轉外殼做描邊，正交相機，透明背景
- **輸出**：每格 128px，用 Blender 內建的 numpy 打包成圖集 PNG 加 meta JSON。Godot 執行時從 meta 建出 SpriteFrames
- **怪物**約 12 種（果凍球、蘑菇怪、野狼、毒蜂、哥布林、骷髏兵、蝙蝠、食人花、石像鬼等，外加一隻地城 Boss），同樣是 5 方向加翻轉
- **地圖零件**：草地 / 石板 / 泥土磚、樹、石頭、柵欄、房屋、城牆、地城牆壁與地板、傳送陣，輸出 .glb
- **圖示**：道具和技能圖示 64px
- 第一階段裝備不會改變角色外觀，外觀只看職業
- 第一階段沒有音效

### 數值與成長（類 RO，數字自訂）
- 六項屬性 STR / AGI / VIT / INT / DEX / LUK。每升一級基本等級給屬性點，屬性越高加點越貴
- 衍生數值：HP、SP、ATK、MATK、DEF、MDEF、HIT、FLEE、CRIT、ASPD，公式集中寫在 `formulas.gd`
- 基本等級上限 99。職業等級上限：初心者 10、一轉 50、二轉 50。每升一級職業等級給 1 技能點
- 轉職條件：初心者職業等級 10 → 一轉；一轉職業等級 40 以上 → 二轉。轉職 NPC 另有收集道具的任務
- 死亡後回到存檔點，扣當前等級經驗的一定比例

### 戰鬥
- 手動戰鬥：點怪或按攻擊鍵之後會一直攻擊鎖定的目標，攻擊間隔由 ASPD 決定。命中看 HIT 對 FLEE，另外有爆擊判定
- 屬性：無、水、地、火、風、聖、暗，用屬性相剋表。巫師的主軸就是屬性
- 技能類型：指定目標、地面範圍、自身增益、被動。有詠唱時間、冷卻、SP 消耗、前置技能
- 技能數量約 35 個：初心者 2 個、每個一轉 5～6 個、每個二轉 5～6 個
- 怪物 AI 狀態機：閒晃 → 發現 → 追擊 → 攻擊 → 脫戰返回。分主動怪和被動怪，在區域內重生
- 掉落：怪物死後依掉落表機率掉在地上，點擊或走過去撿起

### 道具與介面
- 道具種類：消耗品、裝備（武器、盔甲、頭飾、盾、披風、鞋、飾品×2）、雜物。有負重上限，裝備有職業和等級限制
- 介面：HUD（HP/SP、基本和職業經驗條）、快捷列、狀態（加點）、背包、裝備、技能樹、商店、倉庫、對話、轉職
- 電腦快捷鍵：Alt+A 狀態、Alt+E 背包、Alt+Q 裝備、Alt+S 技能
- 介面依螢幕大小縮放。手機上的視窗改成全螢幕分頁

### 地圖內容
- 城鎮「晨曦鎮」：道具商、武器防具商、倉庫、治療和存檔 NPC、傳送員、三位轉職 NPC
- 野外 3 張：新手平原、森林、山谷。怪物強度逐張提高
- 地城 1 座（2 層）加 Boss
- 地圖之間用傳送陣連接，切換時顯示讀取畫面

---

## 里程碑（每一個都能實際玩到）

| # | 內容 | 完成時可以做什麼 |
|---|---|---|
| M0 | 專案骨架、測試器、Blender 管線驗證 | 產生 1 個初心者角色 5 方向走路圖、1 隻果凍球、一組地形磚，並在 Godot 裡顯示 |
| M1 | 移動與鏡頭 | 在平原上電腦點地走、手機用搖桿走，8 方向動畫正確，鏡頭跟隨 |
| M2 | 戰鬥核心 | 打果凍球：怪物 AI、傷害數字、經驗、基本和職業等級、死亡重生、掉落撿取 |
| M3 | 角色養成 | 屬性加點、背包、穿脫裝備、藥水快捷列、存檔讀檔 |
| M4 | 職業與技能 | 初心者 → 三條一轉 → 三條二轉，技能樹、技能特效、屬性相剋 |
| M5 | 城鎮與世界 | 晨曦鎮 NPC、商店、倉庫、轉職任務、3 張野外、地城和 Boss、傳送 |
| M6 | 手機打磨與輸出 | 介面縮放、觸控手感、效能調整，輸出 Mac、Android APK、iOS（需先下載輸出模板） |

每個里程碑開始前，再把它展開成一份細部實作步驟。

## 驗證方式

- **邏輯單元測試**：`godot --headless --path Sproutia --script tests/run_tests.gd`。涵蓋公式、升級、轉職條件、背包負重、裝備限制、技能前置、傷害和屬性相剋、存檔往返
- **美術管線**：跑 `build_all.py` 之後，檢查輸出檔案和 meta 是否齊全，並用 Read 直接看算出來的圖集，確認方向、描邊和透明背景
- **遊戲畫面**：用 Godot Movie Maker 模式跑自動腳本場景（`--write-movie ... --fixed-fps 30 --quit-after N`），自動移動、打怪、升級，輸出截圖來檢查
- **實機**：M6 輸出 Android APK 在模擬器上跑，iOS 輸出 Xcode 專案在 iOS 模擬器上跑，並截圖確認觸控介面

## 注意

- 專案會用 `git init` 建立版本庫。依使用者習慣，**commit 只提供訊息文字，不自己執行 git commit**
- 程式註解不用括號補充，直接白話寫
