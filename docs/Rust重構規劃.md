# Rust 重構規劃

2026-09-27 使用者拍板兩件事：
- 純邏輯、協定、伺服器改用 Rust，表現層留 GDScript，從零重寫
- 遊戲改名 Realm of Faded，簡稱 ROF，專案另開資料夾和 GitHub 版本庫

舊專案 `../Sproutia` 凍結當對照組。決策原文在 `決策紀錄.md` 同一天那條。這份是現行規劃，做到哪就改到哪。

## 1. 範圍

| 部分 | 語言 | 位置 |
|---|---|---|
| 遊戲資料的型別和驗證 | Rust | `rust/crates/data`，crate 名 `rof-data` |
| 戰鬥、數值、背包裝備、技能、地圖碰撞、尋路、怪物 AI | Rust | `rust/crates/core`，`rof-core` |
| 封包格式和欄位驗證 | Rust | `rust/crates/protocol`，`rof-protocol` |
| 客戶端預測、快照內插、伺服器時鐘 | Rust | `rust/crates/netcore`，`rof-netcore` |
| 伺服器，獨立執行檔，不用 Godot | Rust | `rust/crates/server`，`rof-server` |
| 給 GDScript 呼叫的擴充，唯一依賴 godot 的 crate | Rust | `rust/crates/gdext`，`rof-gdext` |
| 介面、特效、動畫、場景、聲音、輸入 | GDScript | `src/`、`scenes/` |

從舊專案搬過來的：文件、`data/`、`assets/`、`locale/`、美術產線 `art_pipeline/`、美術原圖 `art_source/`、崗位和 skill `.claude/`。
舊的遊戲程式 `src/`、`server/`、`tests/`、`scenes/` 沒有搬，照這份的順序重寫，要看舊行為就去 `../Sproutia` 讀。

## 2. 目錄

```
RealmOfFaded/
  project.godot      Godot 專案在根目錄，美術產線寫出來的路徑不用改
  rof.gdextension    指到 rust/target 裡編好的擴充
  rust/
    .gdignore        Godot 不掃這裡
    Cargo.toml       workspace
    crates/          上面那六個 crate
  src/ scenes/       新的表現層
  tests/smoke.gd     客戶端冒煙測試
  data/ assets/ locale/ docs/ art_pipeline/ art_source/
  server_data/       本機伺服器存檔，不進版本庫
```

`rust/target/` 不進版本庫。開發時 `.gdextension` 直接指到 `res://rust/target/debug/`，不用複製；匯出時才複製。

## 3. 技術決定

- **gdext 0.5.5，功能旗標 `api-4-7`**，Rust 1.94 以上，這台是 1.98.1。2026-09-27 實測 Godot 4.7.2 載得進去、GDScript 呼叫得到
- **`.gdextension` 不能有 BOM**。Windows PowerShell 5.1 的 `Set-Content -Encoding utf8` 會寫 BOM，Godot 就只報「Error loading extension」
- **伺服器完全脫離 Godot**：tokio 加 tokio-tungstenite 收 WebSocket，正常處理關機訊號，可以真的多執行緒，Linux 直接部署
- **協定先維持 JSON 文字**，信封照舊 `{v, t, id, d}`，單則上限 8 KB，檢查順序照舊。舊的惡意客戶端測試是把 JSON 直接餵給連線，
  這樣改寫成對新伺服器的黑箱測試最省事。穩定之後再評估二進位格式
- **客戶端的連線用 Godot 的 WebSocketPeer**，由擴充裡的 Rust 驅動，網頁版也能用；Rust 端不自己開 socket
- **實體改成結構**。舊 `battle_world.gd` 用字典存實體、有兩百多種字串鍵，這是最大的改寫量，不照搬字典
- **資料讀取要寬容**：舊 JSON 的整數常寫成 `1.0`，讀的時候接受小數點後為零的數當整數，`rof_data::lenient_i64`
- **隨機數**用自己寫的 PCG32，`rof_core::rng::Pcg32`，同一個種子任何平台出一樣的序列；舊測試指定種子得到的數字不能照抄，要重算
- **移動要兩邊算出一模一樣**：客戶端預測和伺服器跑同一份 Rust。位置用 f32，三角函數一律走 `libm`，x86 伺服器和 ARM 手機才算得一樣
- **全域快取改成一個 `GameData` 物件**傳進去，不用靜態變數
- **單機模式**改成在客戶端行程裡跑同一套伺服器邏輯，由 cargo 功能旗標 `dev-server` 開，正式版不編進去
- **存檔**照舊：一筆資料一個 JSON 檔、HMAC-SHA256 簽章、先寫暫存再換、版本日誌防回滾；密碼 PBKDF2-HMAC-SHA256 六十萬輪；
  金鑰讀 `ROF_SERVER_SECRET`。舊存檔要不要搬過來等 M3 再問使用者
- **開發伺服器的埠用 7780**，不撞舊專案的 7777、7778、7779

## 4. 里程碑

每一個做完都要：Rust 測試全過、截圖給使用者看、提交推送。

| 里程碑 | 做完的樣子 | 狀態 |
|---|---|---|
| M0 骨架 | 六個 crate 編得過，客戶端載得到擴充，一條指令跑全部 Rust 測試 | 2026-09-27 完成 |
| M1 走路 | 登入、選角、進萌芽草原、點地走路會繞牆，兩個客戶端互相看得到對方走；移動類惡意測試搬過來 | |
| M2 打一隻 | 打死萊姆拿經驗和掉落，傷害數字和打擊感照 `打擊感規格.md`；加速和協定兩類惡意測試搬過來 | |
| M3 初心者 | 初心者完整一輪：南門四隻怪、找 NPC 學三招、背包裝備、升級、存檔登出再進來都在 | |
| M4 對齊 | 使用者玩過 M3 同意後，照舊專案的規格補二轉、隊伍、交易、社交、任務、奪色系統 | |

範圍照 09-24 使用者定的「初心者和四隻怪做到完美」。

## 5. 搬移順序，照依賴由下往上

1. `rof-data`：jobs、skills、items、monsters、balance、exp_tables、maps 的結構和驗證，附驗證資料的命令列工具
2. `rof-core` 葉子：formulas、leveling、combat、combat_stats、move_grid、colour_effects
3. 地圖碰撞、尋路、移動
4. `rof-protocol` 和 `rof-server`：登入、記憶體資料庫、地圖 tick，每秒 20 tick
5. `rof-netcore` 和 `rof-gdext`：預測、內插、時鐘；擴充發的訊號名稱和字典形狀盡量照舊的 43 個，表現層照舊的寫法重寫時比較好對
6. 戰鬥世界、怪物 AI
7. 背包裝備、簽章存檔
8. 技能

舊程式的位置，都在 `../Sproutia`，2026-09-27 盤點：

| 看什麼 | 舊檔 |
|---|---|
| 協定、訊息清單 66 種指令、22 種推送 | `src/net/protocol.gd` |
| 伺服器主迴圈 | `server/main.gd`、`server/game_server.gd` |
| 地圖 tick、視野 | `server/world/map_instance.gd` |
| 指令驗證 | `server/world/player_commands.gd` |
| 戰鬥，5298 行 | `src/core/battle_world.gd` |
| 預測和校正 | `src/net/prediction.gd` |
| 客戶端事件分派 | `src/world/net_session.gd` 的 `_on_push` |
| 惡意客戶端測試 | `tests/test_security_*.gd`，共用 `tests/security_case.gd` |

## 6. 指令

- 全部 Rust 測試：在 `rust/` 跑 `cargo test --workspace`
- 編擴充：在 `rust/` 跑 `cargo build -p rof-gdext`
- 開伺服器：在 `rust/` 跑 `cargo run -p rof-server -- --port=7780`
- 客戶端冒煙：在根目錄跑 `godot --headless --path . --script res://tests/smoke.gd`

## 7. 風險

- 手機：Android 用 cargo-ndk 編 arm64 可行；iOS 要在 Mac 上編，實例少，M3 前要實測一次
- 網頁：gdext 的網頁支援還是實驗性，要 nightly 和版本對得上的 emscripten；現在沒有網頁匯出，先不處理
- 熱重載：Windows 會鎖 DLL，改 Rust 常常要重開 Godot；邏輯靠 cargo 測試驗，少開編輯器
- 編譯時間：godot 綁定第一次編一分多鐘，所以只有 `rof-gdext` 依賴 godot，其他 crate 跑測試不用編它
