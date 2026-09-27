//! 別人的位置快照，時間是伺服器地圖時間；顯示時取比伺服器晚一點的時刻，前後兩個快照之間內插。

use std::collections::VecDeque;

use glam::Vec2;
use rof_core::TICK_MS;

const TELEPORT_DISTANCE: f32 = 3.0;
const MAX_SNAPSHOTS: usize = 40;
const MAX_EXTRAPOLATE_MS: f64 = 100.0;

#[derive(Clone, Copy)]
struct Snapshot {
    time: f64,
    position: Vec2,
    velocity: Vec2,
    /// 從前一個快照瞬移過來
    jump: bool,
}

pub struct SnapshotBuffer {
    snapshots: VecDeque<Snapshot>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Sample {
    pub position: [f32; 2],
    /// 取樣區段的平均速度，給動畫和面向用
    pub velocity: [f32; 2],
}

impl SnapshotBuffer {
    /// 從 spawn 的位置和最新的伺服器時間開始
    pub fn new(time_ms: f64, position: [f32; 2]) -> Self {
        let first = Snapshot { time: time_ms, position: position.into(), velocity: Vec2::ZERO, jump: false };
        SnapshotBuffer { snapshots: VecDeque::from([first]) }
    }

    pub fn push(&mut self, time_ms: f64, position: [f32; 2], velocity: [f32; 2]) {
        let (position, velocity) = (Vec2::from(position), Vec2::from(velocity));
        let Some(last) = self.snapshots.back_mut() else { return };
        if time_ms < last.time {
            return;
        }
        if time_ms == last.time {
            (last.position, last.velocity) = (position, velocity);
            return;
        }
        let last = *last;
        let jump = last.position.distance(position) > TELEPORT_DISTANCE;
        // 伺服器只送有變的，隔很久代表中間一直停著，補一個停在原地的快照，起步才不會從很久以前滑過來
        let tick = TICK_MS as f64;
        if !jump && time_ms - last.time > tick * 1.5 {
            let still = Snapshot { time: time_ms - tick, velocity: Vec2::ZERO, ..last };
            self.snapshots.push_back(still);
        }
        self.snapshots.push_back(Snapshot { time: time_ms, position, velocity, jump });
        while self.snapshots.len() > MAX_SNAPSHOTS {
            self.snapshots.pop_front();
        }
    }

    pub fn sample(&mut self, time_ms: f64) -> Sample {
        while self.snapshots.len() >= 2 && self.snapshots[1].time < time_ms {
            self.snapshots.pop_front();
        }
        let first = self.snapshots[0];
        let (position, velocity) = match self.snapshots.get(1) {
            _ if time_ms <= first.time => (first.position, Vec2::ZERO),
            Some(b) if b.jump => (if time_ms < b.time { first.position } else { b.position }, Vec2::ZERO),
            Some(b) => {
                let span = b.time - first.time;
                let t = ((time_ms - first.time) / span) as f32;
                (first.position.lerp(b.position, t), (b.position - first.position) / (span as f32 / 1000.0))
            }
            // 超過最新的快照用最後的速度外推，最多 100 毫秒，之後停住
            None => {
                let late = time_ms - first.time;
                let ahead = (late.min(MAX_EXTRAPOLATE_MS) / 1000.0) as f32;
                let moving = late <= MAX_EXTRAPOLATE_MS;
                (first.position + first.velocity * ahead, if moving { first.velocity } else { Vec2::ZERO })
            }
        };
        Sample { position: position.into(), velocity: velocity.into() }
    }
}
