//! 遊戲伺服器：每條連線一個工作負責收發，遊戲狀態全部在一個工作裡照順序處理，不用鎖。

mod auth;
mod game;
mod world;

use std::net::{IpAddr, SocketAddr};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use serde_json::Value;
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{OwnedSemaphorePermit, Semaphore, mpsc};
use tokio_tungstenite::tungstenite::protocol::{CloseFrame, WebSocketConfig};
use tokio_tungstenite::tungstenite::{Error as WsError, Message};

use crate::auth::{Hashed, Throttle};

const MAX_CONNECTIONS: usize = 200;
const NEW_CONNECTIONS_PER_IP: u32 = 30;
const NEW_CONNECTION_WINDOW_MS: i64 = 10_000;
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(5);
// 比協定上限大一些，超過協定上限的還收得進來由遊戲判 too_large 並寫稽核
const MAX_FRAME_BYTES: usize = rof_protocol::MAX_MESSAGE_BYTES * 2;
const MAX_OUTBOX: usize = 4096;
// 客戶端同一次輪詢收到 kick 和關閉訊號時讀不到 kick
const CLOSE_GRACE: Duration = Duration::from_millis(200);
const CLOSE_KICK: u16 = 4000;
const CLOSE_NORMAL: u16 = 1000;

pub struct Settings {
    pub data_dir: PathBuf,
    pub servers: Vec<ServerConfig>,
    pub password_iterations: u32,
    pub login_timeout_ms: i64,
    pub heartbeat_ms: i64,
    pub idle_timeout_ms: i64,
    /// 登入猜錯的計數時間窗，也是鎖多久
    pub lock_ms: i64,
    /// 新角色的職業，正式是初心者；開發時用 --start-job= 直接看某職業的圖
    pub start_job: String,
}

#[derive(Clone, Deserialize)]
pub struct ServerConfig {
    pub id: String,
    pub name: String,
    pub capacity: u32,
    pub maintenance: bool,
}

impl Settings {
    pub fn load(data_dir: PathBuf, config: &Path) -> Result<Self, String> {
        #[derive(Deserialize)]
        struct File {
            servers: Vec<ServerConfig>,
        }
        let file: File = rof_data::read(config)?;
        Ok(Settings {
            data_dir,
            servers: file.servers,
            password_iterations: 600_000,
            login_timeout_ms: 30_000,
            heartbeat_ms: 20_000,
            idle_timeout_ms: 60_000,
            lock_ms: 300_000,
            start_job: "novice".into(),
        })
    }
}

/// 安全稽核，印在標準輸出，最近的留在記憶體給測試看
#[derive(Clone, Default)]
pub struct AuditLog(Arc<Mutex<Vec<Value>>>);

impl AuditLog {
    pub fn entries(&self) -> Vec<Value> {
        self.0.lock().map(|e| e.clone()).unwrap_or_default()
    }

    fn write(&self, entry: Value) {
        println!("{entry}");
        if let Ok(mut entries) = self.0.lock() {
            if entries.len() >= 10_000 {
                entries.drain(..5_000);
            }
            entries.push(entry);
        }
    }
}

enum Input {
    Open { conn: u64, ip: IpAddr, out: mpsc::Sender<Out> },
    Text(u64, String),
    Kick(u64, &'static str),
    Closed(u64),
    Hashed(Hashed),
    Shutdown,
}

enum Out {
    Text(String),
    Close(u16),
}

pub struct Server {
    pub addr: SocketAddr,
    pub audit: AuditLog,
    inputs: mpsc::Sender<Input>,
}

impl Server {
    /// 所有連線用 1000 關掉
    pub async fn shutdown(&self) {
        let _ = self.inputs.send(Input::Shutdown).await;
        tokio::time::sleep(CLOSE_GRACE * 2).await;
    }
}

/// port 給 0 由系統挑
pub async fn start(settings: Settings, port: u16) -> Result<Server, String> {
    let audit = AuditLog::default();
    let game = game::Game::new(settings, audit.clone())?;
    let listener = TcpListener::bind(("127.0.0.1", port)).await.map_err(|e| format!("開不了埠 {port}：{e}"))?;
    let addr = listener.local_addr().map_err(|e| e.to_string())?;
    let (inputs, receiver) = mpsc::channel(MAX_OUTBOX);
    tokio::spawn(game.run(receiver, inputs.clone()));
    tokio::spawn(accept(listener, inputs.clone()));
    Ok(Server { addr, audit, inputs })
}

/// IPv4 是位址本身；IPv6 一戶人家拿到一整段 /64，照前 64 位元算同一個來源
fn source_key(ip: IpAddr) -> String {
    match ip.to_canonical() {
        IpAddr::V4(v4) => v4.to_string(),
        IpAddr::V6(v6) => {
            let s = v6.segments();
            format!("{:x}:{:x}:{:x}:{:x}::/64", s[0], s[1], s[2], s[3])
        }
    }
}

async fn accept(listener: TcpListener, inputs: mpsc::Sender<Input>) {
    let slots = Arc::new(Semaphore::new(MAX_CONNECTIONS));
    let mut fresh = Throttle::new(NEW_CONNECTIONS_PER_IP, NEW_CONNECTION_WINDOW_MS);
    let clock = Instant::now();
    let mut next_conn = 0;
    loop {
        let Ok((stream, peer)) = listener.accept().await else { continue };
        let now = clock.elapsed().as_millis() as i64;
        fresh.prune(now);
        let ip = peer.ip().to_canonical();
        // 滿了或一直斷線重連的直接關掉，不握手
        let Ok(slot) = slots.clone().try_acquire_owned() else { continue };
        if !fresh.allow(&source_key(ip), now) {
            continue;
        }
        next_conn += 1;
        tokio::spawn(connection(stream, ip, next_conn, inputs.clone(), slot));
    }
}

async fn connection(
    stream: TcpStream,
    ip: IpAddr,
    conn: u64,
    inputs: mpsc::Sender<Input>,
    _slot: OwnedSemaphorePermit,
) {
    let config =
        WebSocketConfig::default().max_message_size(Some(MAX_FRAME_BYTES)).max_frame_size(Some(MAX_FRAME_BYTES));
    let handshake = tokio_tungstenite::accept_async_with_config(stream, Some(config));
    let Ok(Ok(socket)) = tokio::time::timeout(HANDSHAKE_TIMEOUT, handshake).await else { return };
    let (mut sink, mut frames) = socket.split();
    let (out, mut outbox) = mpsc::channel(MAX_OUTBOX);
    if inputs.send(Input::Open { conn, ip, out }).await.is_err() {
        return;
    }
    let writer = async move {
        while let Some(message) = outbox.recv().await {
            match message {
                Out::Text(text) => {
                    if sink.send(Message::text(text)).await.is_err() {
                        return;
                    }
                }
                Out::Close(code) => {
                    tokio::time::sleep(CLOSE_GRACE).await;
                    let _ = sink.send(Message::Close(Some(CloseFrame { code: code.into(), reason: "".into() }))).await;
                    return;
                }
            }
        }
    };
    let reader = async {
        while let Some(frame) = frames.next().await {
            let input = match frame {
                Ok(Message::Text(text)) => Input::Text(conn, text.to_string()),
                Ok(Message::Binary(_)) => Input::Kick(conn, "binary_frame"),
                Err(WsError::Capacity(_)) => Input::Kick(conn, "too_large"),
                Err(WsError::Utf8(_)) => Input::Kick(conn, "bad_utf8"),
                Ok(Message::Close(_)) | Err(_) => return false,
                Ok(_) => continue,
            };
            let kicked = matches!(input, Input::Kick(..));
            if inputs.send(input).await.is_err() || kicked {
                return kicked;
            }
        }
        false
    };
    tokio::pin!(writer);
    tokio::select! {
        _ = &mut writer => {}
        // 被踢的等遊戲送完 kick 和關閉訊號
        kicked = reader => if kicked { writer.await },
    }
    let _ = inputs.send(Input::Closed(conn)).await;
    // 等客戶端回應關閉再斷；太早斷的話客戶端再送東西會收到 RST，還沒讀的 kick 就被丟掉
    let drain = async { while let Some(Ok(_)) = frames.next().await {} };
    let _ = tokio::time::timeout(CLOSE_GRACE * 5, drain).await;
}
