//! Godot 擴充。

use godot::prelude::*;

// 每個模組一個擁有者，分工在 docs/M1介面.md
mod actors;
mod camera;
mod client;
mod input;
mod map;
mod shot;
mod world;

struct RofExtension;

#[gdextension]
unsafe impl ExtensionLibrary for RofExtension {
    fn on_stage_deinit(stage: InitStage) {
        if stage == InitStage::MainLoop {
            actors::release();
        }
    }
}

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
