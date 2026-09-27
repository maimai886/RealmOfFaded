//! 自己角色的移動預測和伺服器修正：送出指令的同時用和伺服器同一份碰撞尋路先走，
//! 指令排在伺服器會開始走的那一刻才套用，兩邊路線一樣，收到伺服器位置時只剩很小的誤差。

use std::collections::VecDeque;

use glam::Vec2;
use rof_core::{ARRIVE_DISTANCE, MapCollision, PathBudget, PathFinder, TICK_SECONDS, walk};
use rof_data::MapData;

const MIN_STEP: f32 = 0.000001;
// 排程估錯一個 tick 的誤差約 0.175 公尺，超過 0.12 就要在 0.15 秒內拉回
const CORRECTION_DISTANCE: f32 = 0.12;
const CORRECTION_SECONDS: f32 = 0.15;
const SMALL_CORRECTION_RATE: f32 = 0.15;
const IGNORE_DISTANCE: f32 = 0.02;
const SNAP_DISTANCE: f32 = 4.0;
// 停著時這個距離內一次對齊，短按只走一兩個 tick，平滑拉回看起來像往回退
const IDLE_CORRECT_DISTANCE: f32 = 0.35;
const HISTORY_MS: f64 = 1500.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Correction {
    None,
    Small,
    Smooth,
    Snap,
}

pub struct Prediction {
    pub move_speed: f32,
    position: Vec2,
    velocity: Vec2,
    finder: PathFinder,
    target: Option<Vec2>,
    path: Vec<[f32; 2]>,
    index: usize,
    budget: PathBudget,
    /// 還沒到套用時間的指令，None 是停下
    scheduled: VecDeque<(f64, Option<Vec2>)>,
    history: VecDeque<(f64, Vec2)>,
    pending: Vec2,
    pending_left: f32,
    last_step_ms: f64,
}

impl Prediction {
    pub fn new(map: &MapData, position: [f32; 2], move_speed: f32) -> Self {
        Prediction {
            move_speed,
            position: position.into(),
            velocity: Vec2::ZERO,
            finder: PathFinder::new(&MapCollision::new(map)),
            target: None,
            path: Vec::new(),
            index: 0,
            budget: PathBudget::new(0.0),
            scheduled: VecDeque::new(),
            history: VecDeque::new(),
            pending: Vec2::ZERO,
            pending_left: 0.0,
            last_step_ms: 0.0,
        }
    }

    /// 收齊 world.blockers 時換上；人在牆裡先推出來
    pub fn set_map(&mut self, map: &MapData) {
        self.finder = PathFinder::new(&MapCollision::new(map));
        let collision = self.finder.collision();
        if !collision.is_walkable(self.position.into()) {
            self.position = collision.push_out(self.position.into()).into();
        }
    }

    pub fn position(&self) -> [f32; 2] {
        self.position.into()
    }

    /// 最近一幀的移動速度，不含修正，給動畫用
    pub fn velocity(&self) -> [f32; 2] {
        self.velocity.into()
    }

    pub fn is_moving(&self) -> bool {
        self.target.is_some()
    }

    pub fn reset(&mut self, position: [f32; 2]) {
        self.position = position.into();
        self.velocity = Vec2::ZERO;
        self.target = None;
        self.scheduled.clear();
        self.history.clear();
        self.pending = Vec2::ZERO;
        self.pending_left = 0.0;
    }

    /// apply_at 是本機時間，None 立刻套用
    pub fn move_to(&mut self, point: [f32; 2], apply_at: Option<f64>) {
        let point = self.finder.collision().clamp(point);
        self.schedule(apply_at, Some(point.into()));
    }

    pub fn stop(&mut self, apply_at: Option<f64>) {
        self.schedule(apply_at, None);
    }

    fn schedule(&mut self, apply_at: Option<f64>, target: Option<Vec2>) {
        let Some(at) = apply_at else {
            self.scheduled.clear();
            return self.apply(self.last_step_ms, target);
        };
        while self.scheduled.back().is_some_and(|&(t, _)| t >= at) {
            self.scheduled.pop_back();
        }
        self.scheduled.push_back((at, target));
    }

    fn apply(&mut self, at_ms: f64, target: Option<Vec2>) {
        self.target = target;
        match target {
            Some(to) => {
                let from = self.position.into();
                self.path = self.budget.find_path(&self.finder, from, to.into(), at_ms);
                self.index = 0;
            }
            // 停下時還沒拉完的平滑修正一次做完，免得停住之後還在往回滑
            None => {
                self.shift(self.pending);
                self.pending = Vec2::ZERO;
                self.pending_left = 0.0;
            }
        }
    }

    /// 最後一個指令代表的速度，排程中的也算，面向和走路動畫在按下那一幀就反應
    pub fn intended_velocity(&self) -> [f32; 2] {
        let Some(target) = self.scheduled.back().map_or(self.target, |&(_, t)| t) else {
            return [0.0; 2];
        };
        let to_target = target - self.position;
        if to_target.length() <= ARRIVE_DISTANCE {
            return [0.0; 2];
        }
        // 已經在走就面向路上的下一個點；排程中的路還沒算，先面向目的地
        let next = self.path.get(self.index).filter(|_| self.scheduled.is_empty());
        let toward = next.and_then(|&p| (Vec2::from(p) - self.position).try_normalize());
        (toward.unwrap_or(to_target.normalize()) * self.move_speed).into()
    }

    /// 推進 delta_s 秒；排程時間落在這一段裡的指令先走到那一刻再套用，和伺服器在 tick 邊界換向一樣
    pub fn step(&mut self, delta_s: f32, now_ms: f64) {
        let before = self.position;
        self.last_step_ms = now_ms;
        let mut from = now_ms - delta_s.max(0.0) as f64 * 1000.0;
        while let Some(&(at, target)) = self.scheduled.front().filter(|c| c.0 <= now_ms) {
            self.scheduled.pop_front();
            let at = at.clamp(from, now_ms);
            self.integrate(((at - from) / 1000.0) as f32);
            from = at;
            self.apply(at, target);
        }
        self.integrate(((now_ms - from) / 1000.0) as f32);
        self.velocity = if delta_s > 0.0 { (self.position - before) / delta_s } else { Vec2::ZERO };
        self.apply_pending(delta_s);
        self.history.push_back((now_ms, self.position));
        while self.history.len() > 2 && now_ms - self.history[0].0 > HISTORY_MS {
            self.history.pop_front();
        }
    }

    /// 伺服器位置是 lag_ms 以前的結果，拿那一刻的預測來比
    pub fn reconcile(&mut self, server: [f32; 2], now_ms: f64, lag_ms: f64) -> Correction {
        let server = Vec2::from(server);
        let past = self.position_at(now_ms - lag_ms);
        let error = server - (past + self.pending);
        let distance = error.length();
        if distance > SNAP_DISTANCE {
            self.reset(server.into());
            self.history.push_back((now_ms, server));
            return Correction::Snap;
        }
        let idle = self.target.is_none() && self.scheduled.is_empty();
        if idle && distance > CORRECTION_DISTANCE && distance <= IDLE_CORRECT_DISTANCE {
            self.pending = Vec2::ZERO;
            self.pending_left = 0.0;
            self.shift(server - past);
            return Correction::Small;
        }
        if distance > CORRECTION_DISTANCE {
            self.pending += error;
            self.pending_left = CORRECTION_SECONDS;
            return Correction::Smooth;
        }
        if distance > IGNORE_DISTANCE {
            self.shift(error * SMALL_CORRECTION_RATE);
            return Correction::Small;
        }
        Correction::None
    }

    pub(crate) fn position_at(&self, time_ms: f64) -> Vec2 {
        let after = self.history.iter().position(|&(t, _)| t >= time_ms);
        match after {
            None => self.position,
            Some(0) => self.history[0].1,
            Some(i) => {
                let ((ta, a), (tb, b)) = (self.history[i - 1], self.history[i]);
                a.lerp(b, ((time_ms - ta) / (tb - ta)) as f32)
            }
        }
    }

    fn integrate(&mut self, travel_s: f32) {
        if travel_s <= 0.0 || self.target.is_none() {
            return;
        }
        let collision = self.finder.collision();
        let max_step = (self.move_speed * TICK_SECONDS).max(MIN_STEP);
        let travel = self.move_speed * travel_s;
        let pos = self.position.into();
        let walked = walk(collision, pos, &self.path, self.index, travel, ARRIVE_DISTANCE, max_step);
        (self.position, self.index) = (walked.position.into(), walked.index);
        if walked.arrived || walked.stuck {
            self.target = None;
        }
    }

    fn apply_pending(&mut self, delta_s: f32) {
        if self.pending_left <= 0.0 {
            return;
        }
        let mut chunk = self.pending * (delta_s / self.pending_left).clamp(0.0, 1.0);
        self.pending -= chunk;
        self.pending_left -= delta_s;
        if self.pending_left <= 0.0 {
            chunk += self.pending;
            self.pending = Vec2::ZERO;
        }
        self.shift(chunk);
    }

    /// 修正照樣撞牆，歷史紀錄一起平移，同一段誤差不會被修兩次
    fn shift(&mut self, offset: Vec2) {
        if offset.length_squared() < MIN_STEP * MIN_STEP {
            return;
        }
        let collision = self.finder.collision();
        let (mut here, goal) = (self.position, self.position + offset);
        // 切成伺服器一個 tick 的步長，大幀和小幀走出的路才不會差一截
        let max_step = (self.move_speed * TICK_SECONDS).max(MIN_STEP);
        for _ in 0..64 {
            let remaining = goal - here;
            if remaining.length() < MIN_STEP {
                break;
            }
            let next: Vec2 =
                collision.move_point(here.into(), (here + remaining.clamp_length_max(max_step)).into()).into();
            if next.distance_squared(here) < MIN_STEP * MIN_STEP {
                break;
            }
            here = next;
        }
        if !collision.is_walkable(here.into()) {
            here = collision.push_out(here.into()).into();
        }
        let actual = here - self.position;
        self.position = here;
        for entry in &mut self.history {
            entry.1 += actual;
        }
    }
}
