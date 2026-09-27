//! 地圖：範圍、出生點和擋路總表；擺設的擋路形狀照 `props.json` 算。

use std::collections::HashMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

// 邊線上的點算站得住，浮點誤差讓點稍微跑進邊裡也不算卡住
pub const EDGE_TOLERANCE: f32 = 0.0001;
// 和同半徑的圓一樣面積的方塊：根號 π 除以 2
const SQUARE_FIT: f32 = 0.8862;
const MIN_EXTENT: f32 = 0.01;
// 玩家被放下去的點要留 0.8 公尺，NPC 和怪物群中心只留半個身體
const CLEAR_STAND: f32 = 0.8;
const CLEAR_BESIDE: f32 = 0.25;
const PORTAL_RADIUS_MAX: f32 = 5.0;

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct Bounds {
    pub min: [f32; 2],
    pub max: [f32; 2],
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum Blocker {
    Rect { min: [f32; 2], max: [f32; 2] },
    Circle { center: [f32; 2], radius: f32 },
}

impl Blocker {
    pub fn contains(&self, [x, z]: [f32; 2]) -> bool {
        const T: f32 = EDGE_TOLERANCE;
        match *self {
            Blocker::Rect { min, max } => x > min[0] + T && x < max[0] - T && z > min[1] + T && z < max[1] - T,
            Blocker::Circle { center, radius } => {
                let r = (radius - T).max(0.0);
                distance_squared(center, [x, z]) < r * r
            }
        }
    }

    fn overlaps_circle(&self, point: [f32; 2], radius: f32) -> bool {
        match *self {
            Blocker::Rect { min, max } => {
                let closest = [0, 1].map(|i| point[i].clamp(min[i], max[i]));
                distance_squared(closest, point) < radius * radius
            }
            Blocker::Circle { center, radius: own } => {
                distance_squared(center, point) < (own + radius) * (own + radius)
            }
        }
    }

    fn has_area(&self) -> bool {
        match *self {
            Blocker::Rect { min, max } => max[0] > min[0] && max[1] > min[1],
            Blocker::Circle { radius, .. } => radius > 0.0,
        }
    }
}

fn distance_squared(a: [f32; 2], b: [f32; 2]) -> f32 {
    (a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2)
}

#[derive(Clone, Debug)]
pub struct MapData {
    pub id: String,
    pub name: String,
    pub scene: String,
    pub bounds: Bounds,
    pub player_spawn: [f32; 2],
    /// 順序：手寫的 blockers、水域、擺設算出來的形狀
    pub blockers: Vec<Blocker>,
}

#[derive(Deserialize)]
struct RawMap {
    name: String,
    scene: String,
    bounds: Bounds,
    player_spawn: [f32; 2],
    #[serde(default)]
    props: Vec<Prop>,
    #[serde(default)]
    blockers: Vec<Blocker>,
    #[serde(default)]
    water: Vec<Bounds>,
    #[serde(default)]
    portals: Vec<Portal>,
    #[serde(default)]
    npcs: Vec<Spot>,
    #[serde(default)]
    spawns: Vec<Spot>,
}

#[derive(Deserialize)]
struct Prop {
    model: String,
    position: [f32; 2],
    #[serde(default)]
    rotation_y: f32,
    #[serde(default = "one")]
    scale: f32,
}

fn one() -> f32 {
    1.0
}

#[derive(Deserialize)]
struct Portal {
    position: [f32; 2],
    radius: f32,
}

#[derive(Deserialize)]
struct Spot {
    #[serde(alias = "center")]
    position: [f32; 2],
}

#[derive(Deserialize)]
struct PropsFile {
    footprints: HashMap<String, Footprint>,
}

#[derive(Deserialize)]
struct Footprint {
    #[serde(default)]
    blocks: bool,
    #[serde(default)]
    parts: Vec<Part>,
    #[serde(flatten)]
    own: Part,
}

#[derive(Deserialize)]
struct Part {
    #[serde(default)]
    shape: Shape,
    #[serde(default)]
    radius: f32,
    #[serde(default)]
    half: [f32; 2],
    #[serde(default)]
    offset: [f32; 2],
}

#[derive(Deserialize, Default)]
#[serde(rename_all = "lowercase")]
enum Shape {
    #[default]
    Circle,
    Square,
    Rect,
}

impl Footprint {
    fn shapes(&self, prop: &Prop) -> Vec<Blocker> {
        if !self.blocks {
            return Vec::new();
        }
        let parts = if self.parts.is_empty() { std::slice::from_ref(&self.own) } else { &self.parts };
        let scale = prop.scale.max(0.0);
        let angle = prop.rotation_y.to_radians();
        let (sin, cos) = (libm::sinf(angle), libm::cosf(angle));
        parts
            .iter()
            .filter_map(|part| {
                let [x, z] = part.offset.map(|v| v * scale);
                let c = [prop.position[0] + x * cos - z * sin, prop.position[1] + x * sin + z * cos];
                let (half_x, half_z) = match part.shape {
                    Shape::Circle => {
                        let radius = part.radius * scale;
                        return (radius >= MIN_EXTENT).then_some(Blocker::Circle { center: c, radius });
                    }
                    // 方塊是一團圓東西的替身，不跟著轉，轉了外接矩形只會變胖
                    Shape::Square => {
                        let half = part.radius * scale * SQUARE_FIT;
                        (half, half)
                    }
                    Shape::Rect => {
                        let [hx, hz] = part.half.map(|v| v * scale);
                        if hx < MIN_EXTENT || hz < MIN_EXTENT {
                            return None;
                        }
                        let (c, s) = (cos.abs(), sin.abs());
                        (hx * c + hz * s, hx * s + hz * c)
                    }
                };
                (half_x >= MIN_EXTENT).then_some(Blocker::Rect {
                    min: [c[0] - half_x, c[1] - half_z],
                    max: [c[0] + half_x, c[1] + half_z],
                })
            })
            .collect()
    }
}

impl MapData {
    pub fn load(data_dir: &Path, id: &str) -> Result<Self, String> {
        let raw: RawMap = crate::read(&data_dir.join(format!("maps/{id}.json")))?;
        let props: PropsFile = crate::read(&data_dir.join("props.json"))?;
        let bad = |why: &str| Err(format!("地圖 {id}：{why}"));
        let Bounds { min, max } = raw.bounds;
        if !(max[0] > min[0] && max[1] > min[1]) {
            return bad("bounds 的 max 要大於 min");
        }
        let mut blockers = raw.blockers;
        blockers.extend(raw.water.iter().map(|w| Blocker::Rect { min: w.min, max: w.max }));
        if !blockers.iter().all(Blocker::has_area) {
            return bad("blockers 和 water 每一塊都要有面積");
        }
        // 擺設壓到一定要站得住的點就整塊丟掉，傳送點 M1 沒做但擋路要和舊的一樣
        let mut clear = vec![(raw.player_spawn, CLEAR_STAND)];
        clear.extend(raw.portals.iter().map(|p| (p.position, p.radius.clamp(CLEAR_STAND, PORTAL_RADIUS_MAX))));
        clear.extend(raw.npcs.iter().chain(&raw.spawns).map(|s| (s.position, CLEAR_BESIDE)));
        for prop in &raw.props {
            let Some(footprint) = props.footprints.get(&prop.model) else {
                continue;
            };
            blockers.extend(
                footprint.shapes(prop).into_iter().filter(|s| !clear.iter().any(|&(p, r)| s.overlaps_circle(p, r))),
            );
        }
        let [x, z] = raw.player_spawn;
        let inside = (min[0]..=max[0]).contains(&x) && (min[1]..=max[1]).contains(&z);
        if !inside || blockers.iter().any(|b| b.contains(raw.player_spawn)) {
            return bad("player_spawn 要在範圍內而且不在擋路裡");
        }
        Ok(MapData {
            id: id.to_string(),
            name: raw.name,
            scene: raw.scene,
            bounds: raw.bounds,
            player_spawn: raw.player_spawn,
            blockers,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn meadow_props_all_block_and_none_sit_on_spawn_points() {
        let dir = crate::find_data_dir(Path::new(env!("CARGO_MANIFEST_DIR"))).unwrap();
        let raw: RawMap = crate::read(&dir.join("maps/meadow.json")).unwrap();
        let props: PropsFile = crate::read(&dir.join("props.json")).unwrap();
        for prop in &raw.props {
            let footprint = props.footprints.get(&prop.model);
            assert!(footprint.is_some_and(|f| f.blocks), "{} 沒登記擋路", prop.model);
        }
        let map = MapData::load(&dir, "meadow").unwrap();
        let dropped = raw.blockers.len() + raw.props.len() - map.blockers.len();
        assert_eq!(dropped, 0, "草原有 {dropped} 個擺設壓到出生點或怪物群被丟掉");
    }
}
