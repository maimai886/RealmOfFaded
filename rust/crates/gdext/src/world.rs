//! 進地圖後的世界：蓋地圖、放角色、鏡頭跟著自己、點地先預測再送 move.to，別人用快照內插。

use std::collections::HashMap;

use godot::classes::{INode3D, Input, InputEventMouseButton, InputEventMouseMotion};
use godot::global::MouseButton;
use godot::prelude::*;
use rof_data::MapData;
use rof_netcore::{MOVE_SPEED, MapCollision, Prediction, SnapshotBuffer, TICK_MS};
use rof_protocol::{Appearance, Gender, Push};
use serde_json::json;

use crate::actors::Actor;
use crate::camera::RofCamera;
use crate::client::{RofClient, now_ms};
use crate::input::GroundPicker;
use crate::shot::arg;

// 兩則移動指令至少隔 50 毫秒，目標差不到 0.25 公尺不送
const MOVE_INTERVAL_MS: f64 = 50.0;
const MOVE_MIN_CHANGE: f32 = 0.25;
// 自己和伺服器都停著時每 100 毫秒再對一次，剩下的小誤差才會修掉
const IDLE_RECONCILE_MS: f64 = 100.0;
// 開發點地前等鏡頭跟上、時鐘對好
const DEV_WALK_FRAMES: i32 = 30;

fn spot(point: [f32; 2]) -> Vector3 {
    Vector3::new(point[0], 0.0, point[1])
}

fn ground(velocity: [f32; 2]) -> Vector2 {
    Vector2::new(velocity[0], velocity[1])
}

#[derive(GodotClass)]
#[class(init, base=Node3D)]
pub struct RofWorld {
    base: Base<Node3D>,
    client: Option<Gd<RofClient>>,
    map: Option<MapData>,
    collision: Option<MapCollision>,
    prediction: Option<Prediction>,
    self_id: u32,
    me: Option<Gd<Actor>>,
    others: HashMap<u32, (Gd<Actor>, SnapshotBuffer)>,
    /// 伺服器上自己最後的位置和是不是停著
    server_self: Option<([f32; 2], bool)>,
    idle_checked: f64,
    wanted: Option<[f32; 2]>,
    sent: Option<[f32; 2]>,
    sent_ms: f64,
    move_ids: Vec<i64>,
    dev_walk: Option<(Vector3, i32)>,
}

#[godot_api]
impl RofWorld {
    #[func]
    fn on_hovered(&mut self, x: f32, z: f32) {
        let walkable = self.collision.as_ref().is_some_and(|c| c.is_walkable([x, z]));
        self.base().get_node_as::<GroundPicker>("Picker").bind_mut().set_walkable(walkable);
    }

    #[func]
    fn on_clicked(&mut self, x: f32, z: f32) {
        let Some(collision) = &self.collision else { return };
        self.wanted = Some(collision.push_out([x, z]).map(|v| (v * 1000.0).round() / 1000.0));
    }

    /// 伺服器回失敗時下一則移動一定重送
    #[func]
    fn on_replied(&mut self, id: i64, ok: bool, _reason: GString, _data: VarDictionary) {
        if let Some(i) = self.move_ids.iter().position(|&m| m == id) {
            self.move_ids.swap_remove(i);
            if !ok {
                self.sent = None;
            }
        }
    }
}

impl RofWorld {
    fn actor(&mut self, gender: Gender, job: &str, appearance: &Appearance, at: [f32; 2]) -> Gd<Actor> {
        let mut actor = Actor::new_alloc();
        let mut look = VarDictionary::new();
        for (key, value) in appearance {
            look.set(key.as_str(), *value);
        }
        actor.bind_mut().setup(gender.as_str().into(), job.into(), look);
        actor.set_position(spot(at));
        self.base_mut().add_child(&actor);
        actor
    }

    fn apply(&mut self, push: Push, clock: &rof_netcore::ServerClock, now: f64) {
        match push {
            Push::WorldEnter(enter) => {
                let me = [enter.me.x, enter.me.z];
                let map = MapData {
                    id: enter.map.clone(),
                    name: enter.map_name,
                    scene: enter.scene,
                    bounds: enter.bounds,
                    player_spawn: me,
                    blockers: Vec::new(),
                };
                let built = crate::map::build(&enter.map);
                self.base_mut().add_child(&built);
                Actor::light_from(built.clone().upcast());
                let mut actor = self.actor(enter.me.gender, &enter.me.character.job_id, &enter.me.appearance, me);
                actor.bind_mut().set_display_name(enter.me.name, true);
                self.me = Some(actor);
                self.self_id = enter.self_id;
                // 收齊擋路之前預測只看範圍
                self.prediction = Some(Prediction::new(&map, me, MOVE_SPEED));
                self.map = Some(map);
            }
            Push::WorldBlockers { offset, total, blockers } => {
                let Some(map) = self.map.as_mut() else { return };
                map.blockers.truncate(offset);
                map.blockers.extend(blockers);
                if map.blockers.len() == total {
                    self.collision = Some(MapCollision::new(map));
                    if let Some(prediction) = self.prediction.as_mut() {
                        prediction.set_map(map);
                    }
                }
            }
            Push::SelfStats { move_speed, .. } => {
                if let Some(prediction) = self.prediction.as_mut() {
                    prediction.move_speed = move_speed;
                }
            }
            Push::EntitySpawn(s) if s.id != self.self_id => {
                let mut actor = self.actor(s.gender, &s.job_id, &s.appearance, [s.x, s.z]);
                actor.bind_mut().set_display_name(s.name, false);
                self.others.insert(s.id, (actor, SnapshotBuffer::new(clock.server_now(now), [s.x, s.z])));
            }
            Push::EntityDespawn { id, .. } => {
                if let Some((mut actor, _)) = self.others.remove(&id) {
                    actor.queue_free();
                }
            }
            Push::EntityState { tick, entities } => {
                let server_ms = (tick as i64 * TICK_MS) as f64;
                for m in entities {
                    let (at, velocity) = ([m.x, m.z], [m.vx, m.vz]);
                    if m.id == self.self_id {
                        if let Some(prediction) = self.prediction.as_mut() {
                            prediction.reconcile(at, now, clock.lag_ms(now, server_ms));
                        }
                        self.server_self = Some((at, velocity == [0.0; 2]));
                    } else if let Some((_, buffer)) = self.others.get_mut(&m.id) {
                        buffer.push(server_ms, at, velocity);
                    }
                }
            }
            _ => {}
        }
    }

    fn send_move(&mut self, now: f64) {
        let Some(target) = self.wanted.filter(|_| now - self.sent_ms >= MOVE_INTERVAL_MS) else { return };
        self.wanted = None;
        let near = |s: [f32; 2]| (s[0] - target[0]).hypot(s[1] - target[1]) < MOVE_MIN_CHANGE;
        let (Some(client), Some(prediction)) = (self.client.as_mut(), self.prediction.as_mut()) else { return };
        if self.sent.is_some_and(near) {
            return;
        }
        let mut client = client.bind_mut();
        let id = client.send("move.to", json!({"x": target[0], "z": target[1]}), 0);
        prediction.move_to(target, client.clock.command_apply_time(now));
        (self.sent, self.sent_ms) = (Some(target), now);
        self.move_ids.push(id);
    }

    /// --dev-walk=x,z：照玩家的方式把滑鼠移過去按一下，游標格子和點地都走真的流程
    fn dev_click(&mut self) {
        let Some((target, frames)) = self.dev_walk.as_mut().filter(|_| self.collision.is_some()) else { return };
        *frames -= 1;
        let (target, frames) = (*target, *frames);
        if !(-1..=0).contains(&frames) {
            return;
        }
        let Some(camera) = self.base().get_viewport().and_then(|v| v.get_camera_3d()) else { return };
        let screen = camera.unproject_position(target);
        let mut motion = InputEventMouseMotion::new_gd();
        motion.set_position(screen);
        let mut button = InputEventMouseButton::new_gd();
        button.set_position(screen);
        button.set_button_index(MouseButton::LEFT);
        button.set_pressed(frames == 0);
        let mut input = Input::singleton();
        input.parse_input_event(&motion);
        input.parse_input_event(&button);
    }
}

#[godot_api]
impl INode3D for RofWorld {
    fn ready(&mut self) {
        self.client = self.base().try_get_node_as::<RofClient>("/root/Rof");
        let this = self.to_gd();
        let mut picker = self.base().get_node_as::<Node>("Picker");
        picker.connect("hovered", &Callable::from_object_method(&this, "on_hovered"));
        picker.connect("clicked", &Callable::from_object_method(&this, "on_clicked"));
        if let Some(client) = self.client.as_mut() {
            client.connect("replied", &Callable::from_object_method(&this, "on_replied"));
        }
        let walk = arg("--dev-walk=").filter(|_| cfg!(debug_assertions));
        let walk: Vec<f32> = walk.unwrap_or_default().split(',').filter_map(|n| n.parse().ok()).collect();
        if let [x, z] = walk[..] {
            self.dev_walk = Some((Vector3::new(x, 0.0, z), DEV_WALK_FRAMES));
        }
    }

    fn process(&mut self, delta: f64) {
        let Some(mut client) = self.client.clone() else { return };
        let now = now_ms();
        let pushes: Vec<Push> = client.bind_mut().pushes.drain(..).collect();
        let client_ref = client.bind();
        for push in pushes {
            self.apply(push, &client_ref.clock, now);
        }
        let render_ms = client_ref.clock.render_time(now);
        drop(client_ref);
        let mut camera = self.base().get_node_as::<RofCamera>("Camera");
        let yaw = camera.bind().yaw();
        let (Some(prediction), Some(me)) = (self.prediction.as_mut(), self.me.as_mut()) else { return };
        prediction.step(delta as f32, now);
        if let Some((at, true)) = self.server_self
            && !prediction.is_moving()
            && now - self.idle_checked >= IDLE_RECONCILE_MS
        {
            self.idle_checked = now;
            prediction.reconcile(at, now, 0.0);
        }
        let position = spot(prediction.position());
        me.set_position(position);
        me.bind_mut().set_motion(ground(prediction.intended_velocity()), yaw);
        camera.bind_mut().follow(position);
        for (actor, buffer) in self.others.values_mut() {
            let sample = buffer.sample(render_ms);
            actor.set_position(spot(sample.position));
            actor.bind_mut().set_motion(ground(sample.velocity), yaw);
        }
        self.send_move(now);
        self.dev_click();
    }
}
