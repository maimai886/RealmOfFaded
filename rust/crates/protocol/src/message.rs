//! M1 的客戶端指令、回應和伺服器推送。欄位驗證寫在型別上，由 serde 解析時一起檢查。

use std::collections::BTreeMap;

use rof_data::{Blocker, Bounds};
use serde::de::{DeserializeOwned, Error as _};
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::{Map, Value};

pub const CLIENT_TYPES: [&str; 8] =
    ["auth.login", "server.list", "char.list", "char.create", "char.enter", "move.to", "move.stop", "ping"];
const COORD_LIMIT: f64 = 10000.0;

const ANY: u8 = 0;
const ID: u8 = 1;
const ACCOUNT: u8 = 2;
const NAME: u8 = 3;

/// 字串欄位，長度算字元數
#[derive(Clone, Debug, PartialEq)]
pub struct Text<const MIN: usize, const MAX: usize, const FORMAT: u8>(pub String);
/// 小寫英文、數字、底線
pub type Id = Text<1, 32, ID>;
pub type Account = Text<4, 16, ACCOUNT>;
pub type Password = Text<4, 64, ANY>;
pub type Version = Text<1, 32, ANY>;
/// 英文字母、數字、中日文字，一個中文字算 1
pub type Name = Text<2, 12, NAME>;

impl<'de, const MIN: usize, const MAX: usize, const FORMAT: u8> Deserialize<'de> for Text<MIN, MAX, FORMAT> {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let text = String::deserialize(d)?;
        let length = text.chars().count();
        let reason = if FORMAT != NAME && !(MIN..=MAX).contains(&length) {
            Some("bad_length")
        } else if text.chars().any(is_disallowed) {
            Some("bad_format")
        } else {
            match FORMAT {
                ID if !text.chars().all(|c| matches!(c, 'a'..='z' | '0'..='9' | '_')) => Some("bad_format"),
                ACCOUNT if !text.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') => Some("bad_format"),
                NAME if !(MIN..=MAX).contains(&length) => Some("name_length"),
                NAME if !text.chars().all(is_name_char) => Some("name_invalid"),
                _ => None,
            }
        };
        reason.map_or(Ok(Text(text)), |r| Err(D::Error::custom(r)))
    }
}

/// 控制字元和看不見、會改變排版方向或換行的字元，可以拿來偽造系統訊息
fn is_disallowed(c: char) -> bool {
    let code = c as u32;
    code < 0x20
        || (0x7F..=0x9F).contains(&code)
        || matches!(code, 0x061C | 0x200E | 0x200F | 0x2028 | 0x2029)
        || (0x202A..=0x202E).contains(&code)
        || (0x2066..=0x2069).contains(&code)
        || (0xFFF9..=0xFFFB).contains(&code)
        || (0xFDD0..=0xFDEF).contains(&code)
        || code & 0xFFFE == 0xFFFE
}

fn is_name_char(c: char) -> bool {
    c.is_ascii_alphanumeric()
        || matches!(c, '\u{4E00}'..='\u{9FFF}' | '\u{3400}'..='\u{4DBF}' | '\u{3041}'..='\u{3096}' | '\u{30A1}'..='\u{30FA}')
}

/// 地圖座標，公尺；實際邊界由伺服器再檢查
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Coord(pub f32);

impl<'de> Deserialize<'de> for Coord {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let value = f64::deserialize(d)?;
        if value.abs() > COORD_LIMIT {
            return Err(D::Error::custom("out_of_range"));
        }
        Ok(Coord(value as f32))
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Gender {
    Male,
    Female,
}

impl Gender {
    pub fn as_str(self) -> &'static str {
        match self {
            Gender::Male => "male",
            Gender::Female => "female",
        }
    }
}

pub type Appearance = BTreeMap<String, u32>;

pub enum Request {
    Login(Login),
    ServerList,
    CharList(ServerChoice),
    CharCreate(CharCreate),
    CharEnter(CharacterChoice),
    MoveTo(MoveTo),
    MoveStop,
    Ping,
}

#[derive(Deserialize)]
pub struct Login {
    pub account: Account,
    pub password: Password,
    pub client_version: Version,
}

#[derive(Deserialize)]
pub struct ServerChoice {
    pub server_id: Id,
}

#[derive(Deserialize)]
pub struct CharCreate {
    pub server_id: Id,
    pub name: Name,
    pub gender: Gender,
    /// 選項數量男女不同，伺服器照性別和 appearances.json 檢查
    pub appearance: Map<String, Value>,
}

#[derive(Deserialize)]
pub struct CharacterChoice {
    pub character_id: Id,
}

#[derive(Deserialize)]
pub struct MoveTo {
    pub x: Coord,
    pub z: Coord,
}

#[derive(Debug, PartialEq)]
pub struct FieldError {
    pub reason: String,
    pub field: String,
}

/// 多的欄位丟掉，全部必填
pub fn parse_request(t: &str, d: Map<String, Value>) -> Result<Request, FieldError> {
    let d = Value::Object(d);
    Ok(match t {
        "auth.login" => Request::Login(fields(d)?),
        "server.list" => Request::ServerList,
        "char.list" => Request::CharList(fields(d)?),
        "char.create" => Request::CharCreate(fields(d)?),
        "char.enter" => Request::CharEnter(fields(d)?),
        "move.to" => Request::MoveTo(fields(d)?),
        "move.stop" => Request::MoveStop,
        "ping" => Request::Ping,
        _ => {
            return Err(FieldError { reason: "unknown_type".into(), field: String::new() });
        }
    })
}

fn fields<T: DeserializeOwned>(d: Value) -> Result<T, FieldError> {
    serde_path_to_error::deserialize(d).map_err(|e| {
        let field = e.path().to_string();
        let message = e.inner().to_string();
        let (reason, field) = if let Some(name) = message.strip_prefix("missing field `") {
            ("missing_field".into(), name.trim_end_matches('`').into())
        } else if message.starts_with("invalid type") {
            ("bad_type".into(), field)
        } else if message.starts_with("unknown variant") {
            ("bad_value".into(), field)
        } else {
            (message, field)
        };
        FieldError { reason, field }
    })
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct LoginReply {
    pub token: String,
    /// 註冊時的大小寫
    pub account: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ServerStatus {
    Smooth,
    Busy,
    Full,
    Maintenance,
    Offline,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ServerInfo {
    pub id: String,
    pub name: String,
    pub online: u32,
    pub capacity: u32,
    pub status: ServerStatus,
    /// 登入後才有，這個帳號在這台的角色數
    pub characters: u32,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ServerListReply {
    pub servers: Vec<ServerInfo>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CharacterSummary {
    pub id: String,
    pub name: String,
    pub job_id: String,
    pub base_level: u32,
    pub job_level: u32,
    pub map: String,
    pub appearance: Appearance,
    pub gender: Gender,
    pub created_at: i64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CharListReply {
    pub characters: Vec<CharacterSummary>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CreateReply {
    pub character_id: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct EnterReply {
    pub character_id: String,
    pub map: String,
    pub self_id: u32,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct PingReply {
    pub time_ms: i64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "t", content = "d")]
pub enum Push {
    #[serde(rename = "world.enter")]
    WorldEnter(WorldEnter),
    /// 擋路總表分批送，offset 是這批第一塊在總表的位置
    #[serde(rename = "world.blockers")]
    WorldBlockers { offset: usize, total: usize, blockers: Vec<Blocker> },
    #[serde(rename = "entity.spawn")]
    EntitySpawn(EntitySpawn),
    #[serde(rename = "entity.despawn")]
    EntityDespawn { id: u32, kind: EntityKind },
    /// 只含視野內和上次比有變的實體
    #[serde(rename = "entity.state")]
    EntityState { tick: u64, entities: Vec<Motion> },
    #[serde(rename = "self.stats")]
    SelfStats { move_speed: f32, alive: bool },
    #[serde(rename = "heartbeat")]
    Heartbeat { time_ms: i64 },
    #[serde(rename = "kick")]
    Kick { reason: String },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct WorldEnter {
    pub map: String,
    pub map_name: String,
    pub scene: String,
    pub bounds: Bounds,
    pub tick: u64,
    pub tick_ms: i64,
    /// 地圖的模擬時間，不是牆上時間
    pub time_ms: i64,
    pub self_id: u32,
    #[serde(rename = "self")]
    pub me: SelfView,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SelfView {
    pub character_id: String,
    pub name: String,
    pub gender: Gender,
    pub appearance: Appearance,
    pub x: f32,
    pub z: f32,
    pub character: CharacterView,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CharacterView {
    pub job_id: String,
    pub base_level: u32,
    pub job_level: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum EntityKind {
    Player,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct EntitySpawn {
    pub id: u32,
    pub kind: EntityKind,
    pub x: f32,
    pub z: f32,
    pub hp_ratio: f32,
    pub alive: bool,
    pub facing: [f32; 2],
    pub name: String,
    pub job_id: String,
    pub gender: Gender,
    pub appearance: Appearance,
    pub equipment: Map<String, Value>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Action {
    Idle,
    Move,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Motion {
    pub id: u32,
    pub x: f32,
    pub z: f32,
    pub vx: f32,
    pub vz: f32,
    pub action: Action,
}
