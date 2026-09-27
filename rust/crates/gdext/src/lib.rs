//! Godot 擴充。

use godot::prelude::*;

struct RofExtension;

#[gdextension]
unsafe impl ExtensionLibrary for RofExtension {}

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
