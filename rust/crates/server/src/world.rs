//! 一張地圖：每秒 20 tick 推進移動，16 公尺一格的視野，把變化轉成給每個玩家的推送。

use std::collections::{BTreeMap, BTreeSet};

use rof_core::{MOVE_SPEED, MapCollision, PathFinder, TICK_MS, Walker};
use rof_data::MapData;
use rof_protocol::*;
use serde::Serialize;

use crate::game::Character;

// 主迴圈卡住時最多補跑幾個 tick，再多就丟掉那段時間
const MAX_CATCHUP: i64 = 20;
// 鏡頭最遠看到約 15 公尺，3×3 格至少 16 公尺；rAthena 的 AREA_SIZE 14 格約 7 公尺，這裡看得比 RO 遠
const AOI_CELL: f32 = 16.0;
const AOI_LEAVE_MARGIN: f32 = 4.0;
const BLOCKERS_PER_PUSH: usize = 100;

struct Player {
    conn: u64,
    character_id: String,
    server_id: String,
    name: String,
    gender: Gender,
    appearance: Appearance,
    job_id: String,
    walker: Walker,
    seen: BTreeSet<u32>,
    last_motion: Option<Motion>,
}

pub(crate) struct World {
    pub(crate) map: MapData,
    finder: PathFinder,
    tick: u64,
    last_ms: i64,
    players: BTreeMap<u32, Player>,
    next_entity: u32,
    pub(crate) outbox: Vec<(u64, String)>,
}

// 送出前取到公分，也用這個精度判斷有沒有變
fn snap(v: f32) -> f32 {
    (v * 100.0).round() / 100.0
}

fn in_view(viewer: [f32; 2], other: [f32; 2], was_visible: bool) -> bool {
    let cell = |p: [f32; 2]| p.map(|v| (v / AOI_CELL).floor() as i32);
    let (a, b) = (cell(viewer), cell(other));
    if (a[0] - b[0]).abs() <= 1 && (a[1] - b[1]).abs() <= 1 {
        return true;
    }
    // 已經看到的要再遠一點才消失，站在格線上才不會一直出現消失
    was_visible && (viewer[0] - other[0]).abs().max((viewer[1] - other[1]).abs()) <= AOI_CELL + AOI_LEAVE_MARGIN
}

/// 切成每則不超過協定上限，數量也不超過 per
fn batches<T: Serialize + Clone>(items: &[T], per: usize, make: impl Fn(usize, Vec<T>) -> Push) -> Vec<String> {
    // offset 會變長，多留幾個位元組
    let header = encode_push(&make(0, Vec::new())).len() + 8;
    let (mut texts, mut start) = (Vec::new(), 0);
    while start < items.len() || texts.is_empty() {
        let (mut end, mut size) = (start, header);
        while end < items.len() && end - start < per {
            let item = serde_json::to_string(&items[end]).map_or(0, |s| s.len()) + 1;
            if end > start && size + item > MAX_MESSAGE_BYTES {
                break;
            }
            (end, size) = (end + 1, size + item);
        }
        texts.push(encode_push(&make(start, items[start..end].to_vec())));
        start = end;
    }
    texts
}

impl World {
    pub(crate) fn new(map: MapData) -> Self {
        let finder = PathFinder::new(&MapCollision::new(&map));
        World { map, finder, tick: 0, last_ms: 0, players: BTreeMap::new(), next_entity: 0, outbox: Vec::new() }
    }

    pub(crate) fn online_on(&self, server_id: &str) -> u32 {
        self.players.values().filter(|p| p.server_id == server_id).count() as u32
    }

    pub(crate) fn has_character(&self, character_id: &str) -> bool {
        self.players.values().any(|p| p.character_id == character_id)
    }

    /// 這一刻的地圖時間，客戶端拿它對時鐘；取到 tick 的話會差到 50 毫秒
    pub(crate) fn time_ms(&self, now: i64) -> i64 {
        self.tick as i64 * TICK_MS + now - self.last_ms
    }

    pub(crate) fn advance_to(&mut self, now: i64) {
        let mut due = (now - self.last_ms) / TICK_MS;
        if due > MAX_CATCHUP {
            self.last_ms = now - MAX_CATCHUP * TICK_MS;
            due = MAX_CATCHUP;
        }
        for _ in 0..due {
            self.last_ms += TICK_MS;
            self.run_tick();
        }
    }

    /// 送 world.enter、擋路總表、數值，再同步視野：他收到看得到的人，看得到他的人收到他
    pub(crate) fn add_player(&mut self, conn: u64, character: &Character, now: i64) -> u32 {
        let collision = self.finder.collision();
        let saved = character.position;
        let position = if collision.is_walkable(saved) { saved } else { self.map.player_spawn };
        self.next_entity += 1;
        let id = self.next_entity;
        let enter = WorldEnter {
            map: self.map.id.clone(),
            map_name: self.map.name.clone(),
            scene: self.map.scene.clone(),
            bounds: self.map.bounds,
            tick: self.tick,
            tick_ms: TICK_MS,
            time_ms: self.time_ms(now),
            self_id: id,
            me: SelfView {
                character_id: character.id.clone(),
                name: character.name.clone(),
                gender: character.gender,
                appearance: character.appearance.clone(),
                x: snap(position[0]),
                z: snap(position[1]),
                character: CharacterView { job_id: character.job_id.clone(), base_level: 1, job_level: 1 },
            },
        };
        self.outbox.push((conn, encode_push(&Push::WorldEnter(enter))));
        let total = self.map.blockers.len();
        for text in batches(&self.map.blockers, BLOCKERS_PER_PUSH, |offset, blockers| Push::WorldBlockers {
            offset,
            total,
            blockers,
        }) {
            self.outbox.push((conn, text));
        }
        self.outbox.push((conn, encode_push(&Push::SelfStats { move_speed: MOVE_SPEED, alive: true })));
        let player = Player {
            conn,
            character_id: character.id.clone(),
            server_id: character.server_id.clone(),
            name: character.name.clone(),
            gender: character.gender,
            appearance: character.appearance.clone(),
            job_id: character.job_id.clone(),
            walker: Walker::new(position),
            seen: BTreeSet::new(),
            last_motion: None,
        };
        self.players.insert(id, player);
        self.sync_views();
        id
    }

    /// 回傳角色 id 和最後的位置，看得到他的人收到 despawn
    pub(crate) fn remove_player(&mut self, id: u32) -> Option<(String, [f32; 2])> {
        let player = self.players.remove(&id)?;
        let text = encode_push(&Push::EntityDespawn { id, kind: EntityKind::Player });
        for other in self.players.values_mut() {
            if other.seen.remove(&id) {
                self.outbox.push((other.conn, text.clone()));
            }
        }
        Some((player.character_id, player.walker.position))
    }

    /// target 是 None 時停下；伺服器從收到之後的下一個 tick 邊界開始照做，客戶端預測排在同一刻
    pub(crate) fn command(&mut self, id: u32, target: Option<[f32; 2]>, now: i64) -> Result<(), &'static str> {
        let collision = self.finder.collision();
        let target = match target {
            Some(point) if !collision.in_bounds(point) => return Err("out_of_bounds"),
            // 落在擋路裡不拒絕，拒絕的話客戶端已經照預測走出去，會被彈回原地
            Some(point) => Some(collision.push_out(point)),
            None => None,
        };
        let apply_tick = self.tick + if now > self.last_ms { 2 } else { 1 };
        if let Some(player) = self.players.get_mut(&id) {
            player.walker.command(apply_tick, target);
        }
        Ok(())
    }

    fn spawn_data(&self, id: u32) -> Option<Push> {
        let p = self.players.get(&id)?;
        let [x, z] = p.walker.position;
        Some(Push::EntitySpawn(EntitySpawn {
            id,
            kind: EntityKind::Player,
            x: snap(x),
            z: snap(z),
            hp_ratio: 1.0,
            alive: true,
            facing: p.walker.facing,
            name: p.name.clone(),
            job_id: p.job_id.clone(),
            gender: p.gender,
            appearance: p.appearance.clone(),
            equipment: Default::default(),
        }))
    }

    fn sync_views(&mut self) {
        let mut changes = Vec::new();
        for (&viewer_id, viewer) in &self.players {
            for (&other_id, other) in &self.players {
                let was = viewer.seen.contains(&other_id);
                if other_id != viewer_id && in_view(viewer.walker.position, other.walker.position, was) != was {
                    changes.push((viewer_id, other_id, !was));
                }
            }
        }
        for (viewer_id, other_id, visible) in changes {
            let push = match visible {
                true => self.spawn_data(other_id),
                false => Some(Push::EntityDespawn { id: other_id, kind: EntityKind::Player }),
            };
            let Some((viewer, push)) = self.players.get_mut(&viewer_id).zip(push) else { continue };
            if visible {
                viewer.seen.insert(other_id);
            } else {
                viewer.seen.remove(&other_id);
            }
            self.outbox.push((viewer.conn, encode_push(&push)));
        }
    }

    /// 先推進移動，再更新視野，最後送有變的位置；自己一定收得到自己的
    fn run_tick(&mut self) {
        self.tick += 1;
        for player in self.players.values_mut() {
            player.walker.tick(&self.finder, MOVE_SPEED, self.tick);
        }
        self.sync_views();
        let mut changed = Vec::new();
        for (&id, player) in &mut self.players {
            let (w, v) = (player.walker.position, player.walker.velocity);
            let motion = Motion {
                id,
                x: snap(w[0]),
                z: snap(w[1]),
                vx: snap(v[0]),
                vz: snap(v[1]),
                action: if v == [0.0; 2] { Action::Idle } else { Action::Move },
            };
            if player.last_motion.as_ref() != Some(&motion) {
                player.last_motion = Some(motion.clone());
                changed.push(motion);
            }
        }
        let tick = self.tick;
        for (&id, player) in &self.players {
            let mine: Vec<Motion> =
                changed.iter().filter(|m| m.id == id || player.seen.contains(&m.id)).cloned().collect();
            if !mine.is_empty() {
                for text in batches(&mine, usize::MAX, |_, entities| Push::EntityState { tick, entities }) {
                    self.outbox.push((player.conn, text));
                }
            }
        }
    }
}
