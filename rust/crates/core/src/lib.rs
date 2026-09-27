//! 純邏輯，伺服器和客戶端共用，不依賴 godot。

mod collision;
mod path;
pub mod rng;
mod walker;

pub use collision::{CELL, MapCollision};
pub use path::{PathFinder, Walked, walk};
pub use walker::{ARRIVE_DISTANCE, MOVE_SPEED, PathBudget, TICK_MS, TICK_SECONDS, Walker};
