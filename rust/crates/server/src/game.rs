//! 遊戲狀態和每則訊息的處理順序：解碼、頻率、id 遞增、欄位、登入狀態，都過了才交給大廳或地圖。

use std::collections::{HashMap, VecDeque};
use std::net::IpAddr;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use rof_core::TICK_MS;
use rof_data::{Appearances, ReservedNames};
use rof_protocol::*;
use serde::Serialize;
use serde_json::{Value, json};
use tokio::sync::mpsc;

use crate::auth::{Account, Auth};
use crate::world::World;
use crate::{AuditLog, CLOSE_KICK, CLOSE_NORMAL, Input, Out, ServerConfig, Settings, Throttle, source_key};

const MAP: &str = "meadow";
const JOB: &str = "novice";
const SLOTS_PER_SERVER: usize = 3;
const MAX_SESSIONS_PER_IP: usize = 10;
const VIOLATION_WINDOW_MS: i64 = 5_000;
const KICK_VIOLATIONS: usize = 20;
// 正常玩家狂按也會被遊戲規則拒絕，這些只記不踢
const SUSPICIOUS_WINDOW_MS: i64 = 10_000;
const SUSPICIOUS_REJECTS: u32 = 100;
const AUDIT_PER_SOURCE: u32 = 10;
const AUDIT_TOTAL: u32 = 300;
const AUDIT_WINDOW_MS: i64 = 60_000;

pub(crate) struct Session {
    pub(crate) ip: IpAddr,
    pub(crate) source: String,
    out: mpsc::Sender<Out>,
    created_ms: i64,
    last_input_ms: i64,
    heartbeat_sent: bool,
    buckets: HashMap<&'static str, (i64, i64)>,
    violations: VecDeque<i64>,
    last_id: i64,
    pub(crate) account: Option<String>,
    /// 密碼還在背景算的登入請求 id
    pub(crate) login_id: Option<i64>,
    entity: Option<u32>,
    rejects: (i64, u32),
}

impl Session {
    pub(crate) fn send(&self, text: String) -> bool {
        self.out.try_send(Out::Text(text)).is_ok()
    }

    /// token bucket，一開始是滿的；總量桶和類別桶都要有才放行，有一個不夠兩邊都不扣
    fn allow(&mut self, t: &str, now: i64) -> bool {
        let category = match t {
            "auth.login" => Some(("login", 3, 10_000)),
            "char.create" => Some(("character", 5, 10_000)),
            "server.list" => Some(("server_list", 5, 10_000)),
            _ => None,
        };
        let limits: Vec<_> = [Some(("total", 30, 1_000)), category].into_iter().flatten().collect();
        let ready = limits.iter().all(|&(name, count, period)| {
            let bucket = self.buckets.entry(name).or_insert((count * period, now));
            bucket.0 = (bucket.0 + (now - bucket.1).max(0) * count).min(count * period);
            bucket.1 = now;
            bucket.0 >= period
        });
        if ready {
            for (name, _, period) in limits {
                self.buckets.entry(name).and_modify(|b| b.0 -= period);
            }
        }
        ready
    }

    fn should_kick(&mut self, now: i64) -> bool {
        while self.violations.front().is_some_and(|&t| now - t >= VIOLATION_WINDOW_MS) {
            self.violations.pop_front();
        }
        self.violations.len() >= KICK_VIOLATIONS
    }
}

pub(crate) struct Character {
    pub(crate) id: String,
    pub(crate) account: String,
    pub(crate) server_id: String,
    pub(crate) name: String,
    pub(crate) gender: Gender,
    pub(crate) appearance: Appearance,
    created_at: i64,
    map: String,
    pub(crate) position: [f32; 2],
}

pub(crate) enum Outcome {
    Done(Value),
    Failed(&'static str),
    Pending,
}

fn done(reply: impl Serialize) -> Outcome {
    Outcome::Done(serde_json::to_value(reply).unwrap_or_default())
}

pub(crate) struct Game {
    pub(crate) settings: Settings,
    appearances: Appearances,
    reserved: ReservedNames,
    world: World,
    pub(crate) sessions: HashMap<u64, Session>,
    pub(crate) accounts: HashMap<String, Account>,
    characters: Vec<Character>,
    /// 帳號小寫對應登入中的連線
    pub(crate) online: HashMap<String, u64>,
    pub(crate) auth: Auth,
    audit: AuditLog,
    audit_limit: Throttle,
    audit_total: Throttle,
    suppressed: HashMap<String, u32>,
    clock: Instant,
    pub(crate) inputs: Option<mpsc::Sender<Input>>,
    next_check_ms: i64,
}

impl Game {
    pub(crate) fn new(settings: Settings, audit: AuditLog) -> Result<Self, String> {
        let dir = &settings.data_dir;
        Ok(Game {
            appearances: Appearances::load(dir)?,
            reserved: ReservedNames::load(dir)?,
            world: World::new(rof_data::MapData::load(dir, MAP)?),
            settings,
            sessions: HashMap::new(),
            accounts: HashMap::new(),
            characters: Vec::new(),
            online: HashMap::new(),
            auth: Auth::new(),
            audit,
            audit_limit: Throttle::new(AUDIT_PER_SOURCE, AUDIT_WINDOW_MS),
            audit_total: Throttle::new(AUDIT_TOTAL, AUDIT_WINDOW_MS),
            suppressed: HashMap::new(),
            clock: Instant::now(),
            inputs: None,
            next_check_ms: 0,
        })
    }

    pub(crate) async fn run(mut self, mut receiver: mpsc::Receiver<Input>, inputs: mpsc::Sender<Input>) {
        self.inputs = Some(inputs);
        let mut ticker = tokio::time::interval(Duration::from_millis(TICK_MS as u64));
        loop {
            tokio::select! {
                input = receiver.recv() => match input {
                    None | Some(Input::Shutdown) => break,
                    Some(input) => {
                        // 先跑完到期的 tick，指令才知道自己排在哪個 tick
                        self.advance();
                        self.handle(input);
                    }
                },
                _ = ticker.tick() => self.advance(),
            }
            self.flush();
        }
        for session in self.sessions.values() {
            let _ = session.out.try_send(Out::Close(CLOSE_NORMAL));
        }
    }

    pub(crate) fn now_ms(&self) -> i64 {
        self.clock.elapsed().as_millis() as i64
    }

    fn advance(&mut self) {
        let now = self.now_ms();
        self.world.advance_to(now);
        self.flush();
        if now >= self.next_check_ms {
            self.next_check_ms = now + 1000;
            self.check_sessions(now);
            self.auth.prune(now, self.settings.lock_ms);
            self.summarize_audit(now);
        }
    }

    /// 地圖產生的推送送給各自的連線；收太慢塞滿的踢掉
    fn flush(&mut self) {
        for (conn, text) in std::mem::take(&mut self.world.outbox) {
            if self.sessions.get(&conn).is_some_and(|s| !s.send(text)) {
                self.close(conn, "slow_client", false);
            }
        }
    }

    fn handle(&mut self, input: Input) {
        match input {
            Input::Open { conn, ip, out } => {
                let now = self.now_ms();
                let source = source_key(ip);
                let crowded = self.sessions.values().filter(|s| s.source == source).count() >= MAX_SESSIONS_PER_IP;
                let session = Session {
                    ip,
                    source,
                    out,
                    created_ms: now,
                    last_input_ms: now,
                    heartbeat_sent: false,
                    buckets: HashMap::new(),
                    violations: VecDeque::new(),
                    last_id: 0,
                    account: None,
                    login_id: None,
                    entity: None,
                    rejects: (now, 0),
                };
                self.sessions.insert(conn, session);
                if crowded {
                    self.kick(conn, "too_many_connections");
                }
            }
            Input::Text(conn, text) => self.receive(conn, &text),
            Input::Kick(conn, reason) => self.kick(conn, reason),
            Input::Closed(conn) => self.close(conn, "", false),
            Input::Hashed(done) => self.finish_login(done),
            Input::Shutdown => {}
        }
    }

    fn receive(&mut self, conn: u64, text: &str) {
        let now = self.now_ms();
        let Some(session) = self.sessions.get_mut(&conn) else { return };
        session.last_input_ms = now;
        session.heartbeat_sent = false;
        let envelope = match decode(text, |t| CLIENT_TYPES.contains(&t)) {
            Ok(envelope) if envelope.id >= 1 => envelope,
            // 沒辦法回應的只記違規
            Ok(envelope) => return self.violation(conn, "bad_id", &envelope.t),
            Err(DecodeError::UnknownType) => return self.violation(conn, "unknown_type", ""),
            Err(error) => return self.kick(conn, error.code()),
        };
        let (id, t) = (envelope.id, envelope.t);
        let allowed = session.allow(&t, now);
        let fresh = id > session.last_id;
        if allowed && fresh {
            session.last_id = id;
        }
        // 先回應再記違規，違規到門檻的人還是收得到最後這則回應
        let (reply, violation) = if !allowed {
            (encode_failure(id, "rate_limited", None), Some("rate_limited".to_string()))
        } else if !fresh {
            (encode_failure(id, "bad_id", None), Some("bad_id".into()))
        } else {
            match parse_request(&t, envelope.d) {
                Err(e) => (encode_failure(id, &e.reason, Some(&e.field)), Some(e.reason)),
                Ok(request) => match self.dispatch(conn, id, request, now) {
                    Outcome::Done(data) => (encode_reply(id, &data), None),
                    Outcome::Failed("not_logged_in") => {
                        (encode_failure(id, "not_logged_in", None), Some("not_logged_in".into()))
                    }
                    Outcome::Failed(reason) => {
                        self.note_reject(conn, now);
                        (encode_failure(id, reason, None), None)
                    }
                    Outcome::Pending => return,
                },
            }
        };
        self.reply(conn, reply);
        if let Some(reason) = violation {
            self.violation(conn, &reason, &t);
        }
    }

    /// 送回應，之後才送這則處理中產生的推送
    pub(crate) fn reply(&mut self, conn: u64, text: String) {
        if let Some(session) = self.sessions.get(&conn) {
            session.send(text);
        }
        self.flush();
    }

    fn violation(&mut self, conn: u64, reason: &str, t: &str) {
        let now = self.now_ms();
        let Some(session) = self.sessions.get_mut(&conn) else { return };
        session.violations.push_back(now);
        let entry = json!({"event": "net.violation", "reason": reason, "type": t});
        self.security(conn, entry);
        if self.sessions.get_mut(&conn).is_some_and(|s| s.should_kick(now)) {
            self.kick(conn, "violations");
        }
    }

    /// 被遊戲規則拒絕不算違規，10 秒內 100 次寫一筆可疑稽核
    pub(crate) fn note_reject(&mut self, conn: u64, now: i64) {
        let Some(session) = self.sessions.get_mut(&conn) else { return };
        if now - session.rejects.0 >= SUSPICIOUS_WINDOW_MS {
            session.rejects = (now, 0);
        }
        session.rejects.1 += 1;
        if session.rejects.1 >= SUSPICIOUS_REJECTS {
            session.rejects = (now, 0);
            self.security(conn, json!({"event": "net.suspicious", "count": SUSPICIOUS_REJECTS}));
        }
    }

    /// 安全稽核帶這條連線的 IP 和帳號，每個來源每分鐘 10 筆、全部 300 筆，被擋的之後補總數
    pub(crate) fn security(&mut self, conn: u64, mut entry: Value) {
        let Some(session) = self.sessions.get(&conn) else { return };
        entry["ip"] = json!(session.ip.to_string());
        entry["account"] = json!(session.account.clone().unwrap_or_default());
        let source = session.source.clone();
        self.audit_source(&source, entry);
    }

    /// 同一種事件、同一個來源每分鐘 10 筆，全部 300 筆
    pub(crate) fn audit_source(&mut self, source: &str, mut entry: Value) {
        let now = self.now_ms();
        let key = format!("{}|{source}", entry["event"].as_str().unwrap_or_default());
        if !self.audit_limit.allow(&key, now) || !self.audit_total.allow("", now) {
            *self.suppressed.entry(key).or_default() += 1;
            return;
        }
        if let Some(count) = self.suppressed.remove(&key) {
            entry["suppressed"] = json!(count);
        }
        self.audit.write(entry);
    }

    fn summarize_audit(&mut self, now: i64) {
        self.audit_limit.prune(now);
        for (key, count) in std::mem::take(&mut self.suppressed) {
            if self.audit_limit.contains(&key) {
                self.suppressed.insert(key, count);
            } else {
                self.audit.write(json!({"event": "audit.suppressed", "key": key, "count": count}));
            }
        }
    }

    /// 送 kick 之後用 4000 關掉，寫稽核
    pub(crate) fn kick(&mut self, conn: u64, reason: &str) {
        self.security(conn, json!({"event": "net.kick", "reason": reason}));
        self.close(conn, reason, true);
    }

    /// 斷線就是登出：存位置、離開地圖、看得到他的人收到 despawn
    fn close(&mut self, conn: u64, reason: &str, notify: bool) {
        let Some(session) = self.sessions.remove(&conn) else { return };
        if notify {
            session.send(encode_push(&Push::Kick { reason: reason.into() }));
            let _ = session.out.try_send(Out::Close(CLOSE_KICK));
        }
        if let Some(entity) = session.entity
            && let Some((character_id, position)) = self.world.remove_player(entity)
            && let Some(character) = self.characters.iter_mut().find(|c| c.id == character_id)
        {
            character.position = position;
        }
        if let Some(account) = session.account
            && self.online.get(&account) == Some(&conn)
        {
            self.online.remove(&account);
        }
        self.flush();
    }

    fn check_sessions(&mut self, now: i64) {
        let settings = &self.settings;
        let mut kicks = Vec::new();
        for (&conn, session) in &mut self.sessions {
            let idle = now - session.last_input_ms;
            if session.account.is_none() {
                if now - session.created_ms >= settings.login_timeout_ms {
                    kicks.push((conn, "login_timeout"));
                }
            } else if idle >= settings.idle_timeout_ms {
                kicks.push((conn, "idle_timeout"));
            } else if idle >= settings.heartbeat_ms && !session.heartbeat_sent {
                session.heartbeat_sent = true;
                session.send(encode_push(&Push::Heartbeat { time_ms: now }));
            }
        }
        for (conn, reason) in kicks {
            self.kick(conn, reason);
        }
    }

    fn dispatch(&mut self, conn: u64, id: i64, request: Request, now: i64) -> Outcome {
        let session = &self.sessions[&conn];
        let (account, entity) = (session.account.clone(), session.entity);
        let lobby = matches!(request, Request::CharList(_) | Request::CharCreate(_) | Request::CharEnter(_));
        match (request, account) {
            (Request::Ping, _) => done(PingReply { time_ms: self.world.time_ms(now) }),
            (Request::ServerList, account) => done(ServerListReply { servers: self.server_list(account.as_deref()) }),
            (Request::Login(login), _) => self.login(conn, id, login, now),
            (_, None) => Outcome::Failed("not_logged_in"),
            _ if lobby && entity.is_some() => Outcome::Failed("in_world"),
            (Request::CharList(choice), Some(account)) => self.char_list(&account, &choice.server_id.0),
            (Request::CharCreate(create), Some(account)) => self.char_create(account, create),
            (Request::CharEnter(choice), Some(account)) => self.char_enter(conn, &account, &choice.character_id.0),
            (request, _) => {
                let Some(entity) = entity else { return Outcome::Failed("not_in_world") };
                let target = match request {
                    Request::MoveTo(to) => Some([to.x.0, to.z.0]),
                    _ => None,
                };
                match self.world.command(entity, target, now) {
                    Ok(()) => done(json!({})),
                    Err(reason) => Outcome::Failed(reason),
                }
            }
        }
    }

    fn server_config(&self, server_id: &str) -> Option<(&ServerConfig, ServerStatus)> {
        let config = self.settings.servers.iter().find(|s| s.id == server_id)?;
        let online = self.world.online_on(server_id);
        let status = match () {
            _ if config.maintenance => ServerStatus::Maintenance,
            _ if config.capacity == 0 => ServerStatus::Offline,
            _ if online >= config.capacity => ServerStatus::Full,
            _ if online * 10 >= config.capacity * 6 => ServerStatus::Busy,
            _ => ServerStatus::Smooth,
        };
        Some((config, status))
    }

    fn server_list(&self, account: Option<&str>) -> Vec<ServerInfo> {
        let servers = self.settings.servers.iter().filter_map(|s| self.server_config(&s.id));
        servers
            .map(|(config, status)| ServerInfo {
                id: config.id.clone(),
                name: config.name.clone(),
                online: self.world.online_on(&config.id),
                capacity: config.capacity,
                status,
                characters: account.map_or(0, |a| self.characters_of(a, &config.id).count() as u32),
            })
            .collect()
    }

    fn characters_of<'a>(&'a self, account: &'a str, server_id: &'a str) -> impl Iterator<Item = &'a Character> {
        self.characters.iter().filter(move |c| c.account == account && c.server_id == server_id)
    }

    fn char_list(&self, account: &str, server_id: &str) -> Outcome {
        match self.server_config(server_id) {
            None => return Outcome::Failed("server_not_found"),
            Some((_, ServerStatus::Maintenance)) => return Outcome::Failed("server_maintenance"),
            _ => {}
        }
        let characters = self
            .characters_of(account, server_id)
            .map(|c| CharacterSummary {
                id: c.id.clone(),
                name: c.name.clone(),
                job_id: JOB.into(),
                base_level: 1,
                job_level: 1,
                map: c.map.clone(),
                appearance: c.appearance.clone(),
                gender: c.gender,
                created_at: c.created_at,
            })
            .collect();
        done(CharListReply { characters })
    }

    fn char_create(&mut self, account: String, create: CharCreate) -> Outcome {
        let server_id = create.server_id.0;
        match self.server_config(&server_id) {
            None => return Outcome::Failed("server_not_found"),
            Some((_, ServerStatus::Maintenance)) => return Outcome::Failed("server_maintenance"),
            Some((_, ServerStatus::Full)) => return Outcome::Failed("server_full"),
            _ => {}
        }
        let name = create.name.0;
        if self.characters_of(&account, &server_id).count() >= SLOTS_PER_SERVER {
            return Outcome::Failed("slots_full");
        }
        if self.reserved.contains(&name) {
            return Outcome::Failed("name_reserved");
        }
        let Some(appearance) = self.appearances.normalize(create.gender.as_str(), &create.appearance) else {
            return Outcome::Failed("bad_appearance");
        };
        let lower = name.to_lowercase();
        if self.characters.iter().any(|c| c.server_id == server_id && c.name.to_lowercase() == lower) {
            return Outcome::Failed("name_taken");
        }
        let id = format!("c{}", self.characters.len() + 1);
        let created_at = SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |d| d.as_secs() as i64);
        let (map, position) = (MAP.to_string(), self.world.map.player_spawn);
        let character =
            Character { id, account, server_id, name, gender: create.gender, appearance, created_at, map, position };
        let reply = CreateReply { character_id: character.id.clone() };
        self.characters.push(character);
        done(reply)
    }

    fn char_enter(&mut self, conn: u64, account: &str, character_id: &str) -> Outcome {
        // 別人的和不存在的一樣回 not_found，不透露存不存在
        let Some(index) = self.characters.iter().position(|c| c.id == character_id && c.account == account) else {
            return Outcome::Failed("not_found");
        };
        if self.world.has_character(character_id) {
            return Outcome::Failed("character_online");
        }
        match self.server_config(&self.characters[index].server_id) {
            Some((_, ServerStatus::Maintenance)) => return Outcome::Failed("server_maintenance"),
            Some((_, ServerStatus::Full)) => return Outcome::Failed("server_full"),
            _ => {}
        }
        let character = &self.characters[index];
        let entity = self.world.add_player(conn, character, self.now_ms());
        let reply = EnterReply { character_id: character.id.clone(), map: MAP.into(), self_id: entity };
        if let Some(session) = self.sessions.get_mut(&conn) {
            session.entity = Some(entity);
        }
        done(reply)
    }
}
