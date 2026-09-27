//! 地圖碰撞：走動的實體是一個點，擋路是矩形和圓；伺服器和客戶端預測共用。

use glam::{IVec2, Vec2};
use rof_data::{Blocker, EDGE_TOLERANCE, MapData};

use crate::path;

const MAX_SLIDES: usize = 3;
pub(crate) const MIN_MOVE: f32 = 0.000001;
const PUSH_OUT_PASSES: usize = 4;
// 推出牆外多留一點，客戶端把座標取到小數第三位才不會又掉回牆裡
const EDGE_MARGIN: f32 = 0.002;
/// 尋路格子的邊長，公尺
pub const CELL: f32 = 0.5;

#[derive(Clone, Debug)]
pub struct MapCollision {
    pub(crate) min: Vec2,
    pub(crate) max: Vec2,
    blockers: Vec<Blocker>,
    pub(crate) columns: i32,
    pub(crate) rows: i32,
}

struct Hit {
    t: f32,
    normal: Vec2,
    contact: Vec2,
}

impl MapCollision {
    pub fn new(map: &MapData) -> Self {
        let (min, max) = (Vec2::from(map.bounds.min), Vec2::from(map.bounds.max));
        let cells = ((max - min) / CELL - EDGE_TOLERANCE).ceil().max(Vec2::ONE);
        MapCollision { min, max, blockers: map.blockers.clone(), columns: cells.x as i32, rows: cells.y as i32 }
    }

    /// 有限數值、在範圍內含邊線、不在擋路裡
    pub fn is_walkable(&self, point: [f32; 2]) -> bool {
        let p = Vec2::from(point);
        p.is_finite() && self.in_bounds(point) && !self.is_blocked(p)
    }

    /// 範圍含邊線
    pub fn in_bounds(&self, point: [f32; 2]) -> bool {
        let p = Vec2::from(point);
        p.cmpge(self.min).all() && p.cmple(self.max).all()
    }

    pub fn clamp(&self, point: [f32; 2]) -> [f32; 2] {
        Vec2::from(point).clamp(self.min, self.max).into()
    }

    pub(crate) fn is_blocked(&self, p: Vec2) -> bool {
        self.blockers.iter().any(|b| b.contains(p.into()))
    }

    /// 碰到擋路就沿邊滑，結果一定在範圍內；起點已經在牆裡直接放行，卡住的人才走得出來
    pub fn move_point(&self, from: [f32; 2], to: [f32; 2]) -> [f32; 2] {
        self.slide(from.into(), to.into()).into()
    }

    pub(crate) fn slide(&self, from: Vec2, to: Vec2) -> Vec2 {
        if !from.is_finite() || !to.is_finite() {
            return from;
        }
        let goal = to.clamp(self.min, self.max);
        if self.blockers.is_empty() || self.is_blocked(from) {
            return goal;
        }
        let (mut position, mut remaining, mut touched) = (from, goal - from, false);
        for _ in 0..MAX_SLIDES {
            if remaining.length_squared() < MIN_MOVE * MIN_MOVE {
                break;
            }
            let Some(hit) = self.first_hit(position, remaining) else {
                // 兩塊擋路交界處，浮點誤差會讓下一段起點貼在另一塊的邊上而被放行
                if !(touched && self.is_blocked(position + remaining)) {
                    position += remaining;
                }
                break;
            };
            if self.is_blocked(hit.contact) {
                break;
            }
            touched = true;
            position = hit.contact;
            let rest = remaining * (1.0 - hit.t);
            remaining = rest - hit.normal * rest.dot(hit.normal).min(0.0);
        }
        position.clamp(self.min, self.max)
    }

    /// 直線走過去會不會進到擋路裡，只擦過邊線不算
    pub(crate) fn segment_clear(&self, from: Vec2, to: Vec2) -> bool {
        let delta = to - from;
        from.is_finite()
            && to.is_finite()
            && (delta.length_squared() < MIN_MOVE * MIN_MOVE || self.first_hit(from, delta).is_none())
    }

    /// 最近站得住的點；客戶端修點擊目標、伺服器夾 move.to 目標都用它，兩邊算出同一個點
    pub fn push_out(&self, point: [f32; 2]) -> [f32; 2] {
        let point = Vec2::from(point);
        if !point.is_finite() {
            return point.into();
        }
        let mut result = self.clamp_inside(point);
        for _ in 0..PUSH_OUT_PASSES {
            let mut moved = false;
            for blocker in &self.blockers {
                if blocker.contains(result.into()) {
                    result = self.clamp_inside(nearest_edge(blocker, result));
                    moved = true;
                }
            }
            if !moved {
                return result.into();
            }
        }
        if !self.is_blocked(result) {
            return result.into();
        }
        // 幾塊擋路疊在一起推不出來，改找最近一整格能走的格子
        let cell = self.cell_of(point);
        let free = |c: IVec2| self.cell_free(c);
        let found = if free(cell) { Some(cell) } else { path::nearest_cell(self, cell, point, point, &free) };
        found.map_or(result, |c| self.cell_center(c)).into()
    }

    fn clamp_inside(&self, p: Vec2) -> Vec2 {
        let margin = EDGE_MARGIN.min((self.max - self.min).min_element() * 0.5);
        p.clamp(self.min + margin, self.max - margin)
    }

    pub(crate) fn cell_of(&self, p: Vec2) -> IVec2 {
        let local = ((p - self.min) / CELL).floor();
        IVec2::new((local.x as i32).clamp(0, self.columns - 1), (local.y as i32).clamp(0, self.rows - 1))
    }

    pub(crate) fn cell_center(&self, c: IVec2) -> Vec2 {
        self.min + (c.as_vec2() + 0.5) * CELL
    }

    /// 整格都沒碰到擋路內部才能走，只貼邊線不算；超出範圍的半格不能走
    pub(crate) fn cell_free(&self, c: IVec2) -> bool {
        if c.x < 0 || c.y < 0 || c.x >= self.columns || c.y >= self.rows {
            return false;
        }
        let low = self.min + c.as_vec2() * CELL;
        let high = low + CELL;
        high.cmple(self.max + EDGE_TOLERANCE).all() && !self.blockers.iter().any(|b| touches(b, low, high))
    }

    fn first_hit(&self, position: Vec2, delta: Vec2) -> Option<Hit> {
        let mut best: Option<Hit> = None;
        for blocker in &self.blockers {
            let hit = match *blocker {
                Blocker::Rect { min, max } => hit_rect(min.into(), max.into(), position, delta),
                Blocker::Circle { center, radius } => hit_circle(center.into(), radius, position, delta),
            };
            // 一樣近選編號小的
            if let Some(hit) = hit
                && best.as_ref().is_none_or(|b| hit.t < b.t)
            {
                best = Some(hit);
            }
        }
        best
    }
}

fn touches(blocker: &Blocker, low: Vec2, high: Vec2) -> bool {
    const T: f32 = EDGE_TOLERANCE;
    match *blocker {
        Blocker::Rect { min, max } => {
            low.x < max[0] - T && high.x > min[0] + T && low.y < max[1] - T && high.y > min[1] + T
        }
        Blocker::Circle { center, radius } => {
            let (c, r) = (Vec2::from(center), (radius - T).max(0.0));
            c.clamp(low, high).distance_squared(c) < r * r
        }
    }
}

/// slab 法；只擦過邊線或從裡面往外走不算碰到
fn hit_rect(min: Vec2, max: Vec2, position: Vec2, delta: Vec2) -> Option<Hit> {
    let (mut enter, mut exit, mut normal) = (f32::NEG_INFINITY, f32::INFINITY, Vec2::ZERO);
    for axis in 0..2 {
        let (low, high, start, speed) = (min[axis], max[axis], position[axis], delta[axis]);
        if speed.abs() < MIN_MOVE {
            if start <= low + EDGE_TOLERANCE || start >= high - EDGE_TOLERANCE {
                return None;
            }
            continue;
        }
        let (near, far) = if speed > 0.0 {
            ((low - start) / speed, (high - start) / speed)
        } else {
            ((high - start) / speed, (low - start) / speed)
        };
        if near > enter {
            enter = near;
            normal = Vec2::ZERO;
            normal[axis] = -speed.signum();
        }
        exit = exit.min(far);
    }
    if enter >= exit || enter < -EDGE_TOLERANCE || enter > 1.0 {
        return None;
    }
    let t = enter.clamp(0.0, 1.0);
    let mut contact = position + delta * t;
    // 接觸點放在邊線上，浮點誤差才不會讓它跑進矩形裡
    let axis = if normal.x != 0.0 { 0 } else { 1 };
    contact[axis] = if normal[axis] < 0.0 { min[axis] } else { max[axis] };
    Some(Hit { t, normal, contact })
}

fn hit_circle(center: Vec2, radius: f32, position: Vec2, delta: Vec2) -> Option<Hit> {
    let offset = position - center;
    let (a, b) = (delta.dot(delta), 2.0 * offset.dot(delta));
    let c = offset.dot(offset) - radius * radius;
    if a < MIN_MOVE * MIN_MOVE || b >= 0.0 {
        return None;
    }
    // 貼著圓周切線滑動、沒真的進到圓裡不算碰到
    let closest = (-b / (2.0 * a)).clamp(0.0, 1.0);
    let inner = (radius - EDGE_TOLERANCE).max(0.0);
    if (offset + delta * closest).length_squared() >= inner * inner {
        return None;
    }
    let mut t = 0.0;
    // 起點剛好停在圓周上時從這一刻就擋住，不然貼著圓周走兩步就穿進去
    if c > 0.0 {
        let discriminant = b * b - 4.0 * a * c;
        if discriminant <= 0.0 {
            return None;
        }
        t = (-b - discriminant.sqrt()) / (2.0 * a);
        if t > 1.0 {
            return None;
        }
        t = t.max(0.0);
    }
    let normal = (position + delta * t - center).try_normalize().unwrap_or(-delta.normalize());
    Some(Hit { t, normal, contact: center + normal * radius })
}

fn nearest_edge(blocker: &Blocker, p: Vec2) -> Vec2 {
    const M: f32 = EDGE_MARGIN;
    match *blocker {
        Blocker::Rect { min, max } => {
            let choices = [
                (p.x - min[0], Vec2::new(min[0] - M, p.y)),
                (max[0] - p.x, Vec2::new(max[0] + M, p.y)),
                (p.y - min[1], Vec2::new(p.x, min[1] - M)),
                (max[1] - p.y, Vec2::new(p.x, max[1] + M)),
            ];
            let nearest = choices.into_iter().reduce(|a, b| if b.0 < a.0 { b } else { a });
            nearest.map_or(p, |(_, edge)| edge)
        }
        Blocker::Circle { center, radius } => {
            let c = Vec2::from(center);
            c + (p - c).try_normalize().unwrap_or(Vec2::X) * (radius + M)
        }
    }
}
