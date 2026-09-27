//! 客戶端網路的純邏輯：預測、快照內插、伺服器時鐘。M1 從舊專案的
//! `src/net/prediction.gd`、`snapshot_buffer.gd`、`server_clock.gd` 照行為重寫。

/// 伺服器每秒幾個 tick，和舊專案 battle_world.gd 一樣
pub const TICKS_PER_SECOND: u32 = 20;
pub const TICK_MS: u32 = 1000 / TICKS_PER_SECOND;
