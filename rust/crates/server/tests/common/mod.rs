//! 測試機器人：開真的伺服器，用 WebSocket 照玩家的方式連進去。
#![allow(dead_code)]

use std::net::{IpAddr, SocketAddr};
use std::path::Path;
use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use rof_server::{Server, Settings};
use serde_json::{Value, json};
use tokio::net::{TcpSocket, TcpStream};
use tokio::time::timeout;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::{MaybeTlsStream, WebSocketStream};

pub use rof_protocol::CLIENT_VERSION;

pub async fn server() -> Server {
    server_with(|_| {}).await
}

pub async fn server_with(change: impl FnOnce(&mut Settings)) -> Server {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let data = rof_data::find_data_dir(root).unwrap();
    let mut settings = Settings::load(data, &root.join("config/servers.json")).unwrap();
    // 測試不用等正式的六十萬輪
    settings.password_iterations = 1000;
    change(&mut settings);
    rof_server::start(settings, 0).await.unwrap()
}

pub struct Bot {
    socket: Option<WebSocketStream<MaybeTlsStream<TcpStream>>>,
    pub next_id: i64,
    pub pushes: Vec<Value>,
    pub kick: Option<String>,
    pub close_code: Option<u16>,
}

impl Bot {
    pub async fn connect(server: &Server) -> Bot {
        Bot::connect_from(server, "127.0.0.1".parse().unwrap()).await.expect("連不上")
    }

    /// 從指定的本機位址連，測不同 IP；被伺服器拒絕時回 None
    pub async fn connect_from(server: &Server, ip: IpAddr) -> Option<Bot> {
        let socket = TcpSocket::new_v4().ok()?;
        socket.bind(SocketAddr::new(ip, 0)).ok()?;
        let stream = socket.connect(server.addr).await.ok()?;
        let url = format!("ws://{}", server.addr);
        let (socket, _) =
            timeout(Duration::from_secs(5), tokio_tungstenite::client_async(url, MaybeTlsStream::Plain(stream)))
                .await
                .ok()?
                .ok()?;
        Some(Bot { socket: Some(socket), next_id: 1, pushes: Vec::new(), kick: None, close_code: None })
    }

    pub async fn send_message(&mut self, message: Message) {
        if let Some(socket) = &mut self.socket {
            let _ = socket.send(message).await;
        }
    }

    pub async fn send_raw(&mut self, text: &str) {
        self.send_message(Message::text(text)).await;
    }

    pub async fn send(&mut self, t: &str, d: Value) -> i64 {
        let id = self.next_id;
        self.next_id += 1;
        self.send_raw(&json!({"v": 1, "t": t, "id": id, "d": d}).to_string()).await;
        id
    }

    /// 下一則訊息；連線關了或等太久是 None
    pub async fn recv(&mut self, wait_ms: u64) -> Option<Value> {
        loop {
            let socket = self.socket.as_mut()?;
            match timeout(Duration::from_millis(wait_ms), socket.next()).await {
                Err(_) => return None,
                Ok(Some(Ok(Message::Text(text)))) => {
                    assert!(text.len() <= rof_protocol::MAX_MESSAGE_BYTES, "伺服器送了 {} 位元組", text.len());
                    let value: Value = serde_json::from_str(&text).unwrap();
                    if value["t"] == "kick" {
                        self.kick = value["d"]["reason"].as_str().map(String::from);
                    }
                    return Some(value);
                }
                Ok(Some(Ok(Message::Close(frame)))) => {
                    self.close_code = frame.map(|f| u16::from(f.code));
                    self.socket = None;
                }
                Ok(Some(Ok(_))) => {}
                _ => self.socket = None,
            }
        }
    }

    pub async fn request(&mut self, t: &str, d: Value) -> Value {
        let id = self.send(t, d).await;
        self.reply_to(id).await
    }

    /// 等這個 id 的回應，中間的推送收進 pushes
    pub async fn reply_to(&mut self, id: i64) -> Value {
        while let Some(message) = self.recv(5000).await {
            if message["t"] == "resp" && message["id"] == id {
                return message["d"].clone();
            }
            self.pushes.push(message);
        }
        Value::Null
    }

    /// 等到某種推送，先看收過的
    pub async fn push(&mut self, t: &str) -> Value {
        if let Some(i) = self.pushes.iter().position(|m| m["t"] == t) {
            return self.pushes.remove(i)["d"].clone();
        }
        while let Some(message) = self.recv(10_000).await {
            if message["t"] == t {
                return message["d"].clone();
            }
            self.pushes.push(message);
        }
        Value::Null
    }

    /// 讀到連線關掉，回傳 kick 的原因
    pub async fn kicked(&mut self) -> String {
        while self.socket.is_some() && self.recv(10_000).await.is_some() {}
        self.kick.clone().unwrap_or_default()
    }

    pub fn is_open(&self) -> bool {
        self.socket.is_some()
    }

    /// 這段時間內沒有收到任何訊息，連線也還開著
    pub async fn silent(&mut self, wait_ms: u64) -> bool {
        self.recv(wait_ms).await.is_none() && self.socket.is_some()
    }

    pub async fn login(&mut self, account: &str) -> Value {
        self.login_with(account, "secret1").await
    }

    pub async fn login_with(&mut self, account: &str, password: &str) -> Value {
        let d = json!({"account": account, "password": password, "client_version": CLIENT_VERSION});
        self.request("auth.login", d).await
    }

    pub async fn create(&mut self, name: &str) -> Value {
        let d = json!({"server_id": "dawn", "name": name, "gender": "female", "appearance": {"hair_style": 1}});
        self.request("char.create", d).await
    }

    /// 登入、建角、進萌芽草原，回傳機器人和自己的實體 id
    pub async fn player(server: &Server, account: &str, name: &str) -> (Bot, u64) {
        let mut bot = Bot::connect(server).await;
        assert_eq!(bot.login(account).await["ok"], true, "{account} 登入");
        let created = bot.create(name).await;
        let character_id = created["character_id"].clone();
        let entered = bot.request("char.enter", json!({"character_id": character_id})).await;
        assert_eq!(entered["ok"], true, "{name} 進地圖 {entered}");
        (bot, entered["self_id"].as_u64().unwrap())
    }

    /// 等自己走起來再停下，回傳停下的位置
    pub async fn wait_until_stopped(&mut self, self_id: u64) -> [f64; 2] {
        let mut moved = false;
        loop {
            let state = self.push("entity.state").await;
            assert!(!state.is_null(), "等不到自己停下");
            let Some(me) = state["entities"].as_array().unwrap().iter().find(|e| e["id"] == self_id).cloned() else {
                continue;
            };
            moved |= me["action"] == "move";
            if moved && me["action"] == "idle" {
                return [me["x"].as_f64().unwrap(), me["z"].as_f64().unwrap()];
            }
        }
    }
}

pub fn audits(server: &Server, event: &str) -> Vec<Value> {
    server.audit.entries().into_iter().filter(|e| e["event"] == event).collect()
}
