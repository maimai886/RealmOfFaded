//! 點地移動，伺服器每 tick 推一步；客戶端預測在 rof-netcore 照同一套規則走。

use std::collections::VecDeque;

use crate::path::{BUDGET_MAX, BUDGET_PER_SECOND, PathFinder, walk};

pub const TICK_MS: i64 = 50;
pub const TICK_SECONDS: f32 = TICK_MS as f32 / 1000.0;
pub const ARRIVE_DISTANCE: f32 = 0.1;
// 初心者在 jobs.json 和角色資料都沒寫 move_speed 時的預設值
pub const MOVE_SPEED: f32 = 3.5;

/// 算路額度，擋連送很遠的目的地拖慢整張地圖；正常點地用不完
#[derive(Clone, Debug)]
pub struct PathBudget {
    left: f32,
    at_ms: f64,
}

impl PathBudget {
    pub fn new(now_ms: f64) -> Self {
        PathBudget { left: BUDGET_MAX, at_ms: now_ms }
    }

    pub fn find_path(&mut self, finder: &PathFinder, from: [f32; 2], to: [f32; 2], now_ms: f64) -> Vec<[f32; 2]> {
        let refill = (now_ms - self.at_ms) as f32 * BUDGET_PER_SECOND / 1000.0;
        self.left = (self.left + refill).min(BUDGET_MAX);
        self.at_ms = now_ms;
        finder.find_path(from, to, &mut self.left)
    }
}

pub struct Walker {
    pub position: [f32; 2],
    /// 上一個 tick 實際的位移乘 20，被擋住時是 0
    pub velocity: [f32; 2],
    pub facing: [f32; 2],
    target: Option<[f32; 2]>,
    queued: VecDeque<(u64, Option<[f32; 2]>)>,
    path: Vec<[f32; 2]>,
    index: usize,
    budget: PathBudget,
}

impl Walker {
    pub fn new(position: [f32; 2]) -> Self {
        Walker {
            position,
            velocity: [0.0; 2],
            facing: [0.0, 1.0],
            target: None,
            queued: VecDeque::new(),
            path: Vec::new(),
            index: 0,
            budget: PathBudget::new(0.0),
        }
    }

    /// 第 apply_tick 個 tick 開始照做，None 是停下；蓋掉排在它之後還沒套用的
    pub fn command(&mut self, apply_tick: u64, target: Option<[f32; 2]>) {
        while self.queued.back().is_some_and(|&(at, _)| at >= apply_tick) {
            self.queued.pop_back();
        }
        self.queued.push_back((apply_tick, target));
    }

    pub fn is_moving(&self) -> bool {
        self.target.is_some() || !self.queued.is_empty()
    }

    /// 走第 tick 個 tick，它涵蓋的時間是 (tick − 1) × 50 到 tick × 50 毫秒
    pub fn tick(&mut self, finder: &PathFinder, speed: f32, tick: u64) {
        let before = self.position;
        let now_ms = (tick - 1) as f64 * TICK_MS as f64;
        while let Some(&(_, target)) = self.queued.front().filter(|&&(at, _)| at <= tick) {
            self.queued.pop_front();
            self.target = target;
            // 路在真的開始走的這個 tick 才算，起點和客戶端預測套用指令時一樣
            if let Some(target) = target {
                self.path = self.budget.find_path(finder, self.position, target, now_ms);
                self.index = 0;
            }
        }
        if self.target.is_some() {
            let step = speed * TICK_SECONDS;
            let collision = finder.collision();
            let walked = walk(collision, self.position, &self.path, self.index, step, ARRIVE_DISTANCE, step);
            (self.position, self.index) = (walked.position, walked.index);
            if walked.arrived || walked.stuck {
                self.target = None;
            }
        }
        self.velocity = [0, 1].map(|i| (self.position[i] - before[i]) / TICK_SECONDS);
        let [x, z] = self.velocity;
        if x * x + z * z > 0.01 {
            let length = (x * x + z * z).sqrt();
            self.facing = [x / length, z / length];
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::MapCollision;
    use rof_data::MapData;

    fn meadow() -> PathFinder {
        let dir = rof_data::find_data_dir(std::path::Path::new(env!("CARGO_MANIFEST_DIR"))).unwrap();
        PathFinder::new(&MapCollision::new(&MapData::load(&dir, "meadow").unwrap()))
    }

    fn walk_until_stopped(walker: &mut Walker, finder: &PathFinder) -> Vec<[f32; 2]> {
        let mut trail = vec![walker.position];
        for tick in 1..2000 {
            walker.tick(finder, MOVE_SPEED, tick);
            trail.push(walker.position);
            if !walker.is_moving() {
                break;
            }
        }
        trail
    }

    #[test]
    fn clicking_behind_a_tree_walks_around_it_and_stops_there() {
        let finder = meadow();
        let collision = finder.collision();
        // 出生點西南邊那棵樹的正後方 1.5 公尺
        let (spawn, tree) = (glam::vec2(4.0, -39.0), glam::vec2(-2.87, -34.19));
        let behind = (tree + (tree - spawn).normalize() * 1.5).into();
        let spawn = spawn.into();
        assert!(collision.is_walkable(behind));
        let path = finder.find_path(spawn, behind, &mut BUDGET_MAX.clone());
        assert!(path.len() >= 2, "要繞路，路是 {path:?}");
        let mut walker = Walker::new(spawn);
        walker.command(1, Some(behind));
        let trail = walk_until_stopped(&mut walker, &finder);
        assert!(trail.iter().all(|&p| collision.is_walkable(p)), "路上穿進了擋路");
        let [dx, dz] = [walker.position[0] - behind[0], walker.position[1] - behind[1]];
        assert!((dx * dx + dz * dz).sqrt() <= ARRIVE_DISTANCE, "停在 {:?}", walker.position);
    }

    #[test]
    fn clicking_inside_a_tree_stops_at_the_nearest_standing_spot() {
        let finder = meadow();
        let collision = finder.collision();
        let tree = [-2.87, -34.19];
        let target = collision.push_out(tree);
        assert!(collision.is_walkable(target) && target != tree);
        let mut walker = Walker::new([4.0, -39.0]);
        walker.command(1, Some(target));
        walk_until_stopped(&mut walker, &finder);
        let [dx, dz] = [walker.position[0] - target[0], walker.position[1] - target[1]];
        assert!((dx * dx + dz * dz).sqrt() <= ARRIVE_DISTANCE, "停在 {:?}", walker.position);
    }
}
