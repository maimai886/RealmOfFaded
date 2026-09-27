# 等級 99 兩輪制的半成品

2026-09-27 雲端對話收尾時 Marcus 做到一半、退回工作區前存下來的改動，照 `docs/決策紀錄.md` 2026-09-19 那條做。
沒有跑過全套測試，套回去之後很多測試會壞，要照下面補完才能提交。

## 檔案

- `level99_code.patch`：程式和經驗表的改動，在 repo 根目錄 `git apply docs/交接/等級99半成品/level99_code.patch`
- `skill_pools.gd.txt`：新檔，改名成 `src/core/skill_pools.gd` 放回去
- `balance_levels_new.json.txt`：`data/balance.json` 的 `levels` 新內容，只換 `levels` 這一段，其他段不要動

## 做到哪

- `exp_tables.json` 的 `base` 照 `round(30 × Lv^1.85 + 70 × Lv)` 補到 98 筆，原本 59 筆不變；`job_tier1` 截成 29 筆、`job_tier2` 截成 49 筆
- `balance.json` 的 `levels`：`base_max` 99，`job_max` 10、30、50、70，逢五多一點的鍵刪掉，換成 `starting_skill_points: 1`
- `formulas.gd` 升一級固定 1 點；`skill_pools.gd` 每一階一個點池，技能扣它 `job` 那一階的池；
  `character_data.gd` 存檔多寫 `skill_pools`，讀檔照規則重算不信存檔的數字
- `job_change.gd` 新的一階先給 1 點，二轉直接轉三轉一律拒絕、要先轉生
- 回應多帶 `skill_pools`，`CLIENT_VERSION` 升 0.9.9；技能視窗每一頁只顯示那一階的點

## 下一步

1. 套回之後改會壞的測試：很多測試寫 `skill_points = 999` 再跨階學技能，要改成呼叫補丁裡的 `fill_skill_pools`。
   至少有 `test_balance`、`test_formulas`、`test_leveling`、`test_registry`、`test_job_paths` 第 104 行、
   `test_server_skills`、`test_battle_skills`、`test_ascetic`、`test_faith_skills`、`test_squire_skills`，
   還有 `battle_session.gd` 的 `dev_apply_job`
2. 補搬遷測試和惡意客戶端測試：各階點數超過、職業等級壓回、用別階的點學這一階
3. `docs/伺服器架構.md` 記 0.9.9 和點池規則；`data/npcs.json` 三轉選項的 `min_job_level:40` 拿掉
4. 轉生本身還沒做

## 要使用者決定

- 舊存檔某一階花超過新點數時，這個半成品是那一階和之後的階全部退回重點，前面的階不動，決策沒寫這條
- 「轉職前這一階的點要全部點完」會卡死初心者：初心者 10 點只有基本技能 9 級能花，要改成沒東西可學就不擋，或給第 10 點一個去處
