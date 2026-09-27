//! 給 GDScript 呼叫的擴充。表現層只透過這裡碰 Rust 的邏輯。

use godot::prelude::*;

struct RofExtension;

#[gdextension]
unsafe impl ExtensionLibrary for RofExtension {}

/// 版本資訊，客戶端冒煙測試用它確認擴充有載進來
#[derive(GodotClass)]
#[class(init, base=RefCounted)]
struct RofInfo;

#[godot_api]
impl RofInfo {
    #[func]
    fn version() -> GString {
        env!("CARGO_PKG_VERSION").into()
    }

    #[func]
    fn protocol_version() -> i64 {
        rof_protocol::VERSION
    }

    #[func]
    fn tick_ms() -> i64 {
        rof_netcore::TICK_MS as i64
    }
}
