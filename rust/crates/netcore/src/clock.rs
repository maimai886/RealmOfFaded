//! 估計伺服器地圖時間和本機時間的差，決定內插顯示哪一刻、移動指令排在本機哪一刻。

use rof_core::TICK_MS;

// 樣本比目前估計大時每次只往上調差距的 2%，偶爾一則慢到的不會讓畫面突然多延遲
const RISE_RATE: f64 = 0.02;
const RTT_SMOOTHING: f64 = 0.2;
const DEFAULT_RTT_MS: f64 = 30.0;
/// 別人顯示得比伺服器晚這麼多：一個 tick 加到達抖動
pub const INTERPOLATION_DELAY_MS: f64 = 60.0;

#[derive(Default)]
pub struct ServerClock {
    offset: Option<f64>,
    rtt: Option<f64>,
}

impl ServerClock {
    /// server_ms 是 entity.state 的 tick 乘 50，local_ms 是本機收到的時間；傳得最快的樣本最準
    pub fn sample(&mut self, server_ms: f64, local_ms: f64) {
        let value = local_ms - server_ms;
        self.offset = Some(match self.offset {
            Some(offset) if value > offset => offset + (value - offset) * RISE_RATE,
            _ => value,
        });
    }

    pub fn record_rtt(&mut self, sample_ms: f64) {
        self.rtt = Some(self.rtt.map_or(sample_ms, |r| r + (sample_ms - r) * RTT_SMOOTHING));
    }

    pub fn rtt(&self) -> f64 {
        self.rtt.unwrap_or(DEFAULT_RTT_MS)
    }

    pub fn is_synced(&self) -> bool {
        self.offset.is_some()
    }

    pub fn server_now(&self, local_ms: f64) -> f64 {
        local_ms - self.offset.unwrap_or(0.0)
    }

    /// 內插取樣的伺服器時間
    pub fn render_time(&self, local_ms: f64) -> f64 {
        self.server_now(local_ms) - INTERPOLATION_DELAY_MS
    }

    /// 現在送出的移動指令，伺服器從收到之後的下一個 tick 邊界開始走，回傳那一刻的本機時間；沒同步時是 None，立刻套用
    pub fn command_apply_time(&self, local_ms: f64) -> Option<f64> {
        let offset = self.offset?;
        // server_now 已經晚了伺服器單程，指令再花單程才到，所以加整個來回
        let arrive = self.server_now(local_ms) + self.rtt();
        Some((arrive / TICK_MS as f64).ceil() * TICK_MS as f64 + offset)
    }

    /// 伺服器 server_ms 的位置對應到本機多久以前的預測
    pub fn lag_ms(&self, local_ms: f64, server_ms: f64) -> f64 {
        match self.offset {
            Some(offset) => (local_ms - server_ms - offset).max(0.0),
            None => self.rtt() + TICK_MS as f64 * 0.5,
        }
    }
}
