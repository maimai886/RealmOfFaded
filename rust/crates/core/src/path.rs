//! 點地尋路：0.5 公尺一格的 A*，規則參考 rAthena path.cpp 的 path_search，只引用規則不抄程式。
//! 伺服器和客戶端預測同一個起點終點算出一模一樣的路，所以 move.to 只送目的地。

use std::cmp::Reverse;
use std::collections::BinaryHeap;

use glam::{IVec2, Vec2};
use rof_data::EDGE_TOLERANCE;

use crate::collision::{CELL, MIN_MOVE, MapCollision};

// 和 rAthena path.hpp 的 MOVE_COST、MOVE_DIAGONAL_COST 一樣
const STRAIGHT: i32 = 10;
const DIAGONAL: i32 = 14;
// data/balance.json 的 pathfinding，兩邊一定要一樣所以不讓人各自調
const MAX_SEARCH: u32 = 2048;
const MAX_PATH_CELLS: i32 = 96;
const NEAREST_RINGS: i32 = 32;
pub const BUDGET_PER_SECOND: f32 = 4096.0;
pub const BUDGET_MAX: f32 = 4096.0;
const WAYPOINT_SNAP: f32 = 0.0001;
const LINE_NUDGE: f32 = 0.0001;

pub struct PathFinder {
    collision: MapCollision,
    // 外面多包一圈不能走的格子，找鄰居不用檢查出界
    free: Vec<bool>,
    region: Vec<u32>,
    width: i32,
}

impl PathFinder {
    pub fn new(collision: &MapCollision) -> Self {
        let width = collision.columns + 2;
        let total = (width * (collision.rows + 2)) as usize;
        let free: Vec<bool> =
            (0..total as i32).map(|i| collision.cell_free(IVec2::new(i % width - 1, i / width - 1))).collect();
        // 四方向相連的格子標成同一塊，編號不同就一定走不到，不用搜
        let mut region = vec![0u32; total];
        let mut label = 0;
        for start in 0..total {
            if !free[start] || region[start] != 0 {
                continue;
            }
            label += 1;
            region[start] = label;
            let mut stack = vec![start];
            while let Some(here) = stack.pop() {
                for offset in [1, -1, width, -width] {
                    let n = (here as i32 + offset) as usize;
                    if free[n] && region[n] == 0 {
                        region[n] = label;
                        stack.push(n);
                    }
                }
            }
        }
        PathFinder { collision: collision.clone(), free, region, width }
    }

    pub fn collision(&self) -> &MapCollision {
        &self.collision
    }

    /// 要經過的點，不含起點，最後一個是終點；budget 是還能展開幾格，用掉的會扣掉
    /// 終點走不進去時改走到同一區離它最近的格子；太遠或一步都走不出去時是空的
    pub fn find_path(&self, from: [f32; 2], to: [f32; 2], budget: &mut f32) -> Vec<[f32; 2]> {
        let path = self.find(from.into(), to.into(), budget);
        path.into_iter().map(Into::into).collect()
    }

    fn find(&self, from: Vec2, to: Vec2, budget: &mut f32) -> Vec<Vec2> {
        let c = &self.collision;
        if !from.is_finite() || !to.is_finite() {
            return Vec::new();
        }
        if from.distance_squared(to) < MIN_MOVE * MIN_MOVE || c.segment_clear(from, to) {
            return vec![to];
        }
        let (start, mut goal) = (c.cell_of(from), c.cell_of(to));
        // 同一格裡還被擋住，格子幫不上忙，交給碰撞沿邊滑
        if start == goal {
            return vec![to];
        }
        let regions = self.regions_around(start);
        if regions.is_empty() {
            return Vec::new();
        }
        let mut end = to;
        if !self.enterable(goal, &regions) {
            let accept = |cell: IVec2| self.is_free(cell) && regions.contains(&self.region[self.index(cell)]);
            match nearest_cell(c, goal, to, from, &accept) {
                Some(cell) if cell != start => goal = cell,
                _ => return Vec::new(),
            }
            end = c.cell_center(goal);
        }
        if estimate(start, goal) > MAX_PATH_CELLS * STRAIGHT {
            return Vec::new();
        }
        let (cells, expanded) = self.search(start, goal, (*budget as u32).clamp(1, MAX_SEARCH));
        *budget = (*budget - expanded as f32).max(0.0);
        let Some(&last) = cells.last().filter(|_| cells.len() >= 2) else {
            return Vec::new();
        };
        if last != goal {
            end = c.cell_center(last);
        }
        self.straighten(from, end, &self.turn_points(&cells, end))
    }

    fn index(&self, c: IVec2) -> usize {
        ((c.y + 1) * self.width + c.x + 1) as usize
    }

    fn cell_at(&self, index: usize) -> IVec2 {
        IVec2::new(index as i32 % self.width - 1, index as i32 / self.width - 1)
    }

    fn is_free(&self, c: IVec2) -> bool {
        c.x >= 0 && c.y >= 0 && c.x < self.collision.columns && c.y < self.collision.rows && self.free[self.index(c)]
    }

    fn neighbours(&self, c: IVec2) -> [usize; 4] {
        let i = self.index(c) as i32;
        [1, -1, self.width, -self.width].map(|o| (i + o) as usize)
    }

    /// 只有一部分能走的格子，看上下左右能走的格子各是哪一塊
    fn regions_around(&self, c: IVec2) -> Vec<u32> {
        let i = self.index(c);
        if self.free[i] {
            return vec![self.region[i]];
        }
        let mut result = Vec::new();
        for n in self.neighbours(c) {
            if self.free[n] && !result.contains(&self.region[n]) {
                result.push(self.region[n]);
            }
        }
        result
    }

    fn enterable(&self, c: IVec2, regions: &[u32]) -> bool {
        let i = self.index(c);
        if self.free[i] {
            return regions.contains(&self.region[i]);
        }
        self.neighbours(c).iter().any(|&n| self.free[n] && regions.contains(&self.region[n]))
    }

    /// 沒搜到終點時走到搜過的格子裡離終點最近的那格
    fn search(&self, start: IVec2, goal: IVec2, limit: u32) -> (Vec<IVec2>, u32) {
        let (w, total) = (self.width, self.free.len());
        let (start_index, goal_index) = (self.index(start), self.index(goal));
        let mut free = self.free.clone();
        // 終點格就算只有一部分能走也進得去
        free[goal_index] = true;
        let mut g = vec![i32::MAX; total];
        let mut parent = vec![usize::MAX; total];
        let mut closed = vec![false; total];
        let h = |i: usize| estimate(self.cell_at(i), goal);
        g[start_index] = 0;
        // 依序比總成本、離終點多近、格子編號，結果固定
        let mut open = BinaryHeap::from([Reverse((h(start_index), h(start_index), start_index))]);
        let (mut best, mut best_h, mut expanded) = (start_index, h(start_index), 0);
        while let Some(Reverse((_, here_h, index))) = open.pop() {
            if closed[index] {
                continue;
            }
            closed[index] = true;
            expanded += 1;
            if here_h < best_h || (here_h == best_h && g[index] < g[best]) {
                (best, best_h) = (index, here_h);
            }
            if index == goal_index || expanded >= limit {
                break;
            }
            let at = |offset: i32| free[(index as i32 + offset) as usize];
            let (right, left, down, up) = (at(1), at(-1), at(w), at(-w));
            // 斜走要旁邊兩格都能走，和 rAthena 一樣不切牆角
            let steps = [
                (right, 1, STRAIGHT),
                (left, -1, STRAIGHT),
                (down, w, STRAIGHT),
                (up, -w, STRAIGHT),
                (right && down && at(w + 1), w + 1, DIAGONAL),
                (right && up && at(1 - w), 1 - w, DIAGONAL),
                (left && down && at(w - 1), w - 1, DIAGONAL),
                (left && up && at(-w - 1), -w - 1, DIAGONAL),
            ];
            for (open_step, offset, cost) in steps {
                let next = (index as i32 + offset) as usize;
                let next_g = g[index] + cost;
                if open_step && !closed[next] && next_g <= MAX_PATH_CELLS * STRAIGHT && next_g < g[next] {
                    g[next] = next_g;
                    parent[next] = index;
                    open.push(Reverse((next_g + h(next), h(next), next)));
                }
            }
        }
        let mut cells = Vec::new();
        let mut walk = best;
        while walk != usize::MAX {
            cells.push(self.cell_at(walk));
            walk = parent[walk];
        }
        cells.reverse();
        (cells, expanded)
    }

    /// 只留轉彎的格子，起點那格不算，最後一個換成 end
    fn turn_points(&self, cells: &[IVec2], end: Vec2) -> Vec<Vec2> {
        let mut points: Vec<Vec2> =
            cells.windows(3).filter(|w| w[1] - w[0] != w[2] - w[1]).map(|w| self.collision.cell_center(w[1])).collect();
        points.push(end);
        points
    }

    /// 從目前的點往後看，看得到就跳過中間的轉彎點
    fn straighten(&self, from: Vec2, end: Vec2, points: &[Vec2]) -> Vec<Vec2> {
        let (mut result, mut anchor, mut i) = (Vec::new(), from, 0);
        while i < points.len() {
            let mut reach = i;
            while reach + 1 < points.len() && self.line_clear(anchor, points[reach + 1]) {
                reach += 1;
            }
            result.push(points[reach]);
            anchor = points[reach];
            i = reach + 1;
        }
        if result.last() != Some(&end) {
            result.push(end);
        }
        result
    }

    /// 直線經過的格子都能走；兩端格只有一部分能走時再用碰撞確認
    fn line_clear(&self, a: Vec2, b: Vec2) -> bool {
        let c = &self.collision;
        // 端點剛好在格線上時照線段真的經過的那一格算
        let nudge = (b - a).normalize_or_zero() * CELL * LINE_NUDGE;
        let (first, last) = (c.cell_of(a + nudge), c.cell_of(b - nudge));
        if (!self.is_free(first) || !self.is_free(last)) && !c.segment_clear(a, b) {
            return false;
        }
        let pa = (a - c.min) / CELL;
        let delta = (b - c.min) / CELL - pa;
        let step = IVec2::new(if delta.x > 0.0 { 1 } else { -1 }, if delta.y > 0.0 { 1 } else { -1 });
        let span = |d: f32| if d.abs() < MIN_MOVE { f32::INFINITY } else { 1.0 / d.abs() };
        let first_edge = |d: f32, cell: i32, p: f32| match () {
            _ if d.abs() < MIN_MOVE => f32::INFINITY,
            _ if d > 0.0 => (cell as f32 + 1.0 - p) * span(d),
            _ => (p - cell as f32) * span(d),
        };
        let (span_x, span_y) = (span(delta.x), span(delta.y));
        let mut next_x = first_edge(delta.x, first.x, pa.x);
        let mut next_y = first_edge(delta.y, first.y, pa.y);
        let blocked = |p: IVec2| p != first && p != last && !self.is_free(p);
        let mut cell = first;
        for _ in 0..c.columns + c.rows + 2 {
            if blocked(cell) {
                return false;
            }
            if cell == last {
                return true;
            }
            if (next_x - next_y).abs() < 0.000001 {
                // 剛好穿過格角，兩旁都要能走，和 A* 不切牆角同一條規則
                let sides = [IVec2::new(cell.x + step.x, cell.y), IVec2::new(cell.x, cell.y + step.y)];
                if sides.into_iter().any(blocked) {
                    return false;
                }
                cell += step;
                next_x += span_x;
                next_y += span_y;
            } else if next_x < next_y {
                cell.x += step.x;
                next_x += span_x;
            } else {
                cell.y += step.y;
                next_y += span_y;
            }
        }
        true
    }
}

/// 八方向距離，不會高估
fn estimate(a: IVec2, b: IVec2) -> i32 {
    let d = (b - a).abs();
    STRAIGHT * (d.x + d.y) + (DIAGONAL - 2 * STRAIGHT) * d.x.min(d.y)
}

/// 由近到遠一圈圈找 accept 的格子裡離 point 最近的
pub(crate) fn nearest_cell(
    c: &MapCollision,
    center: IVec2,
    point: Vec2,
    from: Vec2,
    accept: &dyn Fn(IVec2) -> bool,
) -> Option<IVec2> {
    let (mut best, mut best_distance, mut best_from) = (None, f32::INFINITY, f32::INFINITY);
    let (mut ring, mut stop_after) = (1, NEAREST_RINGS);
    while ring <= stop_after {
        for y in center.y - ring..=center.y + ring {
            let edge = y == center.y - ring || y == center.y + ring;
            let mut x = center.x - ring;
            while x <= center.x + ring {
                let cell = IVec2::new(x, y);
                if accept(cell) {
                    let middle = c.cell_center(cell);
                    let (distance, from_distance) = (middle.distance_squared(point), middle.distance_squared(from));
                    // 一樣近選離起點近的，院子四面一樣近時停在人這一邊
                    if distance < best_distance - EDGE_TOLERANCE
                        || (distance < best_distance + EDGE_TOLERANCE && from_distance < best_from)
                    {
                        (best, best_distance, best_from) = (Some(cell), distance, from_distance);
                    }
                }
                x += if edge { 1 } else { ring * 2 };
            }
        }
        // 找到的那一圈再多看一圈，斜角的格子可能比較近
        if best.is_some() && stop_after > ring + 1 {
            stop_after = ring + 1;
        }
        ring += 1;
    }
    best
}

pub struct Walked {
    pub position: [f32; 2],
    pub index: usize,
    /// 站上終點
    pub arrived: bool,
    /// 一步都沒動
    pub stuck: bool,
}

/// 沿著路走 travel 公尺，每段碰撞最多走 max_step；一次走多遠、分幾次走，路線都一樣
pub fn walk(
    collision: &MapCollision,
    position: [f32; 2],
    path: &[[f32; 2]],
    mut index: usize,
    travel: f32,
    max_step: f32,
) -> Walked {
    let start = Vec2::from(position);
    let (mut here, mut left) = (start, travel);
    let step_cap = max_step.max(MIN_MOVE);
    let mut guard = path.len() + (travel / step_cap).ceil() as usize + 2;
    while left > MIN_MOVE && index < path.len() && guard > 0 {
        guard -= 1;
        let goal = Vec2::from(path[index]);
        let (distance, span) = (here.distance(goal), left.min(step_cap));
        let next = if distance <= span { goal } else { here + (goal - here) / distance * span };
        let moved = collision.slide(here, next);
        let used = here.distance(moved);
        if used < MIN_MOVE {
            break;
        }
        left -= used;
        here = moved;
        if here.distance_squared(goal) <= WAYPOINT_SNAP * WAYPOINT_SNAP {
            here = goal;
            if index + 1 < path.len() {
                index += 1;
                continue;
            }
            break;
        }
        // 往中途點走卻沒走到，是被牆擋住在滑，這次就停
        if distance <= span {
            break;
        }
    }
    let arrived = index + 1 >= path.len() && path.last().is_some_and(|&end| Vec2::from(end) == here);
    Walked { position: here.into(), index, arrived, stuck: here == start && travel > MIN_MOVE }
}
