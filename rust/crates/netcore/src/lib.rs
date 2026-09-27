//! 客戶端的預測、快照內插、伺服器時鐘，純邏輯，擴充接進來用。

mod clock;
mod prediction;
mod snapshot;

pub use clock::{INTERPOLATION_DELAY_MS, ServerClock};
pub use prediction::{Correction, Prediction};
pub use rof_core::TICK_MS;
pub use snapshot::{Sample, SnapshotBuffer};

#[cfg(test)]
mod tests {
    use super::*;
    use rof_core::{MOVE_SPEED, MapCollision, PathFinder, Walker};
    use rof_data::MapData;

    #[test]
    fn prediction_and_server_walk_the_same_clicks_to_the_same_spot() {
        let dir = rof_data::find_data_dir(std::path::Path::new(env!("CARGO_MANIFEST_DIR"))).unwrap();
        let map = MapData::load(&dir, "meadow").unwrap();
        let finder = PathFinder::new(&MapCollision::new(&map));
        let spawn = map.player_spawn;
        // 點樹後面、走到一半改點別處、停下、再點一次；數字是伺服器開始照做的 tick
        let clicks = [(3, Some([-4.1, -33.3])), (15, Some([8.0, -30.0])), (31, None), (36, Some([-3.0, -30.5]))];
        let mut server = Walker::new(spawn);
        let mut client = Prediction::new(&map, spawn, MOVE_SPEED);
        // 本機時鐘比伺服器快 1234 毫秒，畫面 60 幀有一點抖動
        let offset = 1234.0;
        let (mut local, mut frame) = (offset, 0);
        let mut worst: f32 = 0.0;
        for tick in 1..200u64 {
            // 指令比套用早兩個 tick 送出，和真的連線一樣排在未來
            for &(at, target) in clicks.iter().filter(|c| c.0 == tick + 2) {
                server.command(at, target);
                let apply = (at - 1) as f64 * 50.0 + offset;
                match target {
                    Some(point) => client.move_to(point, Some(apply)),
                    None => client.stop(Some(apply)),
                }
            }
            server.tick(&finder, MOVE_SPEED, tick);
            let label = tick as f64 * 50.0 + offset;
            while local < label {
                frame += 1;
                let delta = 1000.0 / 60.0 + if frame % 3 == 0 { 4.0 } else { -2.0 };
                local += delta;
                client.step((delta / 1000.0) as f32, local);
            }
            let [x, z] = server.position;
            worst = worst.max(client.position_at(label).distance(glam::vec2(x, z)));
        }
        assert!(!server.is_moving() && !client.is_moving());
        assert!(worst < 0.02, "預測和伺服器最多差 {worst} 公尺，會被拉回");
    }
}
