//! 帶 `--shot=路徑` 時截圖存檔並結束，`--shot-wait=秒` 等光照和霧穩定再截，驗收色調用 6 秒。

use godot::classes::{INode, Node, Os};
use godot::prelude::*;

// 等幾幀讓貼圖和字型載完
const SETTLE_FRAMES: u32 = 10;

#[derive(GodotClass)]
#[class(init, base=Node)]
pub struct ShotTaker {
    base: Base<Node>,
    path: String,
    frames: u32,
    wait: f64,
}

#[godot_api]
impl INode for ShotTaker {
    fn ready(&mut self) {
        self.path = arg("--shot=").unwrap_or_default();
        self.wait = arg("--shot-wait=").and_then(|s| s.parse().ok()).unwrap_or(0.0);
        let active = !self.path.is_empty();
        self.base_mut().set_process(active);
    }

    fn process(&mut self, delta: f64) {
        self.frames += 1;
        self.wait -= delta;
        if self.frames < SETTLE_FRAMES || self.wait > 0.0 {
            return;
        }
        let image = self.base().get_viewport().and_then(|v| v.get_texture()).and_then(|t| t.get_image());
        let ok = image.is_some_and(|img| img.save_png(&self.path) == godot::global::Error::OK);
        godot_print!("截圖 {} {}", self.path, if ok { "OK" } else { "失敗" });
        self.base().get_tree().quit_ex().exit_code(if ok { 0 } else { 1 }).done();
    }
}

/// 從命令列找 `prefix` 開頭的參數，`--` 前後都找
pub fn arg(prefix: &str) -> Option<String> {
    let os = Os::singleton();
    let mut args = os.get_cmdline_user_args().to_vec();
    args.extend(os.get_cmdline_args().to_vec());
    args.iter().map(|a| a.to_string()).find_map(|a| a.strip_prefix(prefix).map(str::to_owned))
}
