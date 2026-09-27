//! 連線和登入，autoload 名字 `Rof`：Godot 的 WebSocketPeer 由這裡每幀驅動，收到 world.enter 換到世界場景。

use std::collections::{HashMap, VecDeque};

use godot::classes::web_socket_peer::State;
use godot::classes::{INode, Json, Node, Time, WebSocketPeer};
use godot::global::randf;
use godot::prelude::*;
use rof_netcore::{ServerClock, TICK_MS};
use rof_protocol::{CLIENT_VERSION, Push, decode, encode};
use serde_json::{Map, Value, json};

use crate::shot::arg;

const REQUEST_TIMEOUT_MS: f64 = 8000.0;
const CONNECT_TIMEOUT_MS: f64 = 3000.0;
// 進地圖先 ping 幾次對好時鐘，第一步才排得到伺服器開始走的那個 tick
const SYNC_PINGS: usize = 4;
const WORLD_SCENE: &str = "res://scenes/world.tscn";
const LOGIN_SCENE: &str = "res://scenes/login.tscn";

pub fn now_ms() -> f64 {
    Time::singleton().get_ticks_usec() as f64 / 1000.0
}

struct Pending {
    sent_ms: f64,
    t: String,
    d: Map<String, Value>,
    /// 伺服器忙碌自動重送時，回應用原本的 id 發給呼叫的人
    reply_as: i64,
}

/// 開發參數 --dev-login、--dev-character，只有 debug 版有
#[derive(Clone, Copy, PartialEq)]
enum Dev {
    Login,
    List,
    Create,
    Enter,
}

#[derive(GodotClass)]
#[class(init, base=Node)]
pub struct RofClient {
    base: Base<Node>,
    peer: Option<Gd<WebSocketPeer>>,
    opened: bool,
    connect_started: f64,
    next_id: i64,
    pending: HashMap<i64, Pending>,
    retries: Vec<(f64, Pending)>,
    kick: Option<String>,
    last_reason: String,
    pub clock: ServerClock,
    pub pushes: VecDeque<Push>,
    dev: HashMap<i64, Dev>,
}

#[godot_api]
impl RofClient {
    #[signal]
    fn connected();

    #[signal]
    fn disconnected(reason: GString);

    #[signal]
    fn replied(id: i64, ok: bool, reason: GString, data: VarDictionary);

    #[func]
    pub fn connect_server(&mut self, host: GString, port: i64) {
        self.disconnect_server();
        let mut peer = WebSocketPeer::new_gd();
        if peer.connect_to_url(&format!("ws://{host}:{port}")) != godot::global::Error::OK {
            return self.lost("connect_failed");
        }
        (self.peer, self.opened, self.connect_started) = (Some(peer), false, now_ms());
    }

    /// 最後一次斷線的原因，新的登入頁拿來顯示
    #[func]
    pub fn last_disconnect_reason(&self) -> String {
        self.last_reason.clone()
    }

    /// 自己斷的不發 disconnected
    #[func]
    pub fn disconnect_server(&mut self) {
        if let Some(mut peer) = self.peer.take() {
            peer.close_ex().code(1000).done();
        }
        self.reset();
    }

    /// 回請求編號，沒連上是 0；auth.login 的 client_version 由這裡補
    #[func]
    pub fn request(&mut self, t: GString, d: VarDictionary) -> i64 {
        let d = serde_json::from_str(&Json::stringify(&d.to_variant()).to_string()).unwrap_or_default();
        self.send(&t.to_string(), d, 0)
    }
}

impl RofClient {
    /// d 是物件；reply_as 大於 0 時回應用那個 id 發
    pub fn send(&mut self, t: &str, d: Value, reply_as: i64) -> i64 {
        let (Some(peer), Value::Object(mut d)) = (self.peer.as_mut().filter(|_| self.opened), d) else { return 0 };
        if t == "auth.login" {
            d.insert("client_version".into(), CLIENT_VERSION.into());
        }
        self.next_id += 1;
        let id = self.next_id;
        peer.send_text(&encode(t, id, d.clone()));
        let reply_as = if reply_as > 0 { reply_as } else { id };
        self.pending.insert(id, Pending { sent_ms: now_ms(), t: t.into(), d, reply_as });
        id
    }

    fn reset(&mut self) {
        (self.opened, self.kick) = (false, None);
        self.pending.clear();
        self.retries.clear();
        self.pushes.clear();
        self.dev.clear();
    }

    fn lost(&mut self, reason: &str) {
        (self.peer, self.last_reason) = (None, reason.into());
        self.reset();
        let mut tree = self.base().get_tree();
        if tree.get_current_scene().is_some_and(|s| s.get_scene_file_path() == WORLD_SCENE) {
            tree.change_scene_to_file(LOGIN_SCENE);
        }
        self.base_mut().emit_signal("disconnected", &[reason.to_variant()]);
    }

    fn reply(&mut self, id: i64, ok: bool, reason: &str, data: &Value) {
        let data = Json::parse_string(&data.to_string()).try_to::<VarDictionary>().unwrap_or_default();
        self.base_mut()
            .emit_signal("replied", &[id.to_variant(), ok.to_variant(), reason.to_variant(), data.to_variant()]);
    }

    fn receive(&mut self, text: &str) {
        let Ok(envelope) = decode(text, |_| true) else { return };
        let now = now_ms();
        if envelope.t == "resp" {
            let Some(pending) = self.pending.remove(&envelope.id) else { return };
            self.clock.record_rtt(now - pending.sent_ms);
            let d = Value::Object(envelope.d);
            let (ok, reason) = (d["ok"] == true, d["reason"].as_str().unwrap_or_default().to_string());
            if pending.t == "ping" && ok {
                self.clock.sample(d["time_ms"].as_f64().unwrap_or(0.0), now);
            }
            // 雜湊名額滿了，等 1 到 2 秒的隨機時間自動重送一次
            if reason == "server_busy" && pending.reply_as == envelope.id {
                self.retries.push((now + 1000.0 + randf() * 1000.0, pending));
                return;
            }
            self.dev_step(pending.reply_as, &d);
            return self.reply(pending.reply_as, ok, &reason, &d);
        }
        let Ok(push) = serde_json::from_value::<Push>(json!({"t": envelope.t, "d": envelope.d})) else { return };
        match &push {
            Push::Kick { reason } => return self.kick = Some(reason.clone()),
            Push::Heartbeat { .. } => {
                self.send("ping", json!({}), 0);
                return;
            }
            Push::EntityState { tick, .. } => self.clock.sample((*tick as i64 * TICK_MS) as f64, now),
            Push::WorldEnter(enter) => {
                self.clock.sample(enter.time_ms as f64, now);
                for _ in 0..SYNC_PINGS {
                    self.send("ping", json!({}), 0);
                }
                self.base().get_tree().change_scene_to_file(WORLD_SCENE);
            }
            _ => {}
        }
        self.pushes.push_back(push);
    }

    /// --dev-login=帳號:密碼 --dev-character=名字：登入、沒有這隻就建、進地圖
    fn dev_step(&mut self, id: i64, d: &Value) {
        let Some(step) = self.dev.remove(&id) else { return };
        let name = arg("--dev-character=").unwrap_or_else(|| "測試員".into());
        let found = d["characters"].as_array().and_then(|list| list.iter().find(|c| c["name"] == name.as_str()));
        let (t, next, d) = match (step, d["ok"] == true) {
            (_, false) => return godot_error!("開發登入失敗：{d}"),
            (Dev::Login, _) => ("char.list", Dev::List, json!({"server_id": "dawn"})),
            (Dev::List, _) if found.is_none() => {
                let d = json!({"server_id": "dawn", "name": name, "gender": "female", "appearance": {}});
                ("char.create", Dev::Create, d)
            }
            (Dev::List, _) => ("char.enter", Dev::Enter, json!({"character_id": found.map(|c| c["id"].clone())})),
            (Dev::Create, _) => ("char.enter", Dev::Enter, json!({"character_id": d["character_id"]})),
            (Dev::Enter, _) => return,
        };
        let id = self.send(t, d, 0);
        self.dev.insert(id, next);
    }
}

#[godot_api]
impl INode for RofClient {
    fn ready(&mut self) {
        let Some(login) = arg("--dev-login=").filter(|_| cfg!(debug_assertions)) else { return };
        let server = arg("--server=").unwrap_or_else(|| "127.0.0.1:7780".into());
        let (host, port) = server.rsplit_once(':').unwrap_or((&server, "7780"));
        self.connect_server(host.into(), port.parse().unwrap_or(7780));
        self.dev.insert(0, Dev::Login);
        let (account, password) = login.split_once(':').unwrap_or((&login, ""));
        self.retries.push((
            0.0,
            Pending {
                sent_ms: 0.0,
                t: "auth.login".into(),
                d: json!({"account": account, "password": password}).as_object().cloned().unwrap_or_default(),
                reply_as: 0,
            },
        ));
    }

    fn process(&mut self, _delta: f64) {
        let Some(mut peer) = self.peer.clone() else { return };
        peer.poll();
        let now = now_ms();
        match peer.get_ready_state() {
            State::OPEN if !self.opened => {
                self.opened = true;
                self.base_mut().emit_signal("connected", &[]);
            }
            State::CONNECTING if now - self.connect_started > CONNECT_TIMEOUT_MS => return self.lost("connect_failed"),
            State::CLOSED => {
                let reason = if self.opened {
                    self.kick.clone().unwrap_or("disconnected".into())
                } else {
                    "connect_failed".into()
                };
                return self.lost(&reason);
            }
            _ => {}
        }
        while peer.get_available_packet_count() > 0 {
            let packet = peer.get_packet();
            self.receive(&String::from_utf8_lossy(packet.as_slice()));
        }
        let open = self.opened;
        let due: Vec<_> = self.retries.extract_if(.., |(at, _)| open && *at <= now).collect();
        for (_, pending) in due {
            let first = pending.reply_as == 0;
            let id = self.send(&pending.t, Value::Object(pending.d), pending.reply_as);
            if first && let Some(step) = self.dev.remove(&0) {
                self.dev.insert(id, step);
            }
        }
        let expired: Vec<i64> =
            self.pending.iter().filter(|(_, p)| now - p.sent_ms > REQUEST_TIMEOUT_MS).map(|(&id, _)| id).collect();
        for id in expired {
            if let Some(pending) = self.pending.remove(&id) {
                self.reply(pending.reply_as, false, "timeout", &json!({}));
            }
        }
    }
}
