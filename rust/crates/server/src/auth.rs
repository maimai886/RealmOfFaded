//! 登入：版本、限速、鎖定、並發上限都在丟進背景之前擋；密碼 PBKDF2 在背景算，算完回主迴圈收尾。
//! 鎖定參考 rAthena login_athena.conf 的 dynamic_pass_failure_ban：只鎖帳號加來源和來源本身，帳號永遠不鎖。

use std::collections::{HashMap, HashSet};
use std::net::IpAddr;

use rof_protocol::{CLIENT_VERSION, Login, LoginReply, encode_failure, encode_reply};
use serde_json::json;
use sha2::Sha256;

use crate::Input;
use crate::game::{Game, Outcome};

const ATTEMPTS_PER_SOURCE: u32 = 30;
const ATTEMPT_WINDOW_MS: i64 = 60_000;
const REGISTRATIONS_PER_SOURCE: u32 = 20;
const REGISTRATION_WINDOW_MS: i64 = 3_600_000;
const PAIR_FAILURES: usize = 5;
const SOURCE_FAILURES: usize = 7;
const ATTACK_SOURCES: usize = 3;
const JOBS_PER_SOURCE: usize = 2;

/// 固定時間窗的計數，一個 key 一個窗
pub(crate) struct Throttle {
    limit: u32,
    window_ms: i64,
    entries: HashMap<String, (i64, u32)>,
}

impl Throttle {
    pub(crate) fn new(limit: u32, window_ms: i64) -> Self {
        Throttle { limit, window_ms, entries: HashMap::new() }
    }

    pub(crate) fn allow(&mut self, key: &str, now: i64) -> bool {
        let entry = self.entries.entry(key.to_string()).or_insert((now, 0));
        if now - entry.0 >= self.window_ms {
            *entry = (now, 0);
        }
        entry.1 += 1;
        entry.1 <= self.limit
    }

    pub(crate) fn contains(&self, key: &str) -> bool {
        self.entries.contains_key(key)
    }

    pub(crate) fn prune(&mut self, now: i64) {
        self.entries.retain(|_, e| now - e.0 < self.window_ms);
    }
}

pub(crate) struct Account {
    /// 註冊時的大小寫
    name: String,
    salt: [u8; 16],
    hash: [u8; 32],
    iterations: u32,
}

#[derive(Default)]
struct Strikes {
    failures: Vec<i64>,
    locked_until: i64,
}

pub(crate) struct Auth {
    pairs: HashMap<String, Strikes>,
    sources: HashMap<String, Strikes>,
    /// 帳號被哪些來源猜錯過、什麼時候回報過
    targets: HashMap<String, (HashMap<String, i64>, i64)>,
    attempts: Throttle,
    registrations: Throttle,
    jobs: Vec<String>,
    registering: HashSet<String>,
    max_jobs: usize,
}

pub(crate) struct Hashed {
    conn: u64,
    key: String,
    name: String,
    source: String,
    ip: IpAddr,
    result: HashResult,
}

enum HashResult {
    Registered(Account),
    Verified(bool),
}

fn derive(password: &str, salt: &[u8], iterations: u32) -> [u8; 32] {
    let mut out = [0; 32];
    pbkdf2::pbkdf2_hmac::<Sha256>(password.as_bytes(), salt, iterations, &mut out);
    out
}

fn random<const N: usize>() -> [u8; N] {
    let mut bytes = [0; N];
    // 系統亂數拿不到就整台不能登入，比給出猜得到的鹽和 token 好
    getrandom::fill(&mut bytes).expect("系統亂數");
    bytes
}

fn strike(table: &mut HashMap<String, Strikes>, key: String, limit: usize, now: i64, window: i64) {
    let strikes = table.entry(key).or_default();
    if now < strikes.locked_until {
        return;
    }
    strikes.failures.retain(|&t| now - t < window);
    strikes.failures.push(now);
    if strikes.failures.len() >= limit {
        strikes.locked_until = now + window;
        strikes.failures.clear();
    }
}

impl Auth {
    pub(crate) fn new() -> Self {
        let cores = std::thread::available_parallelism().map_or(2, |n| n.get());
        Auth {
            pairs: HashMap::new(),
            sources: HashMap::new(),
            targets: HashMap::new(),
            attempts: Throttle::new(ATTEMPTS_PER_SOURCE, ATTEMPT_WINDOW_MS),
            registrations: Throttle::new(REGISTRATIONS_PER_SOURCE, REGISTRATION_WINDOW_MS),
            jobs: Vec::new(),
            registering: HashSet::new(),
            // 留一個核心給主迴圈
            max_jobs: cores.saturating_sub(1).max(2),
        }
    }

    fn lock_reason(&self, key: &str, source: &str, now: i64) -> Option<&'static str> {
        let locked = |s: Option<&Strikes>| s.is_some_and(|s| now < s.locked_until);
        if locked(self.sources.get(source)) {
            Some("ip_banned")
        } else if locked(self.pairs.get(&format!("{key}|{source}"))) {
            Some("locked")
        } else {
            None
        }
    }

    /// 回傳這個帳號是不是被三個以上來源一起猜，同一個時間窗只回報一次
    fn fail(&mut self, key: &str, source: &str, now: i64, window: i64) -> bool {
        strike(&mut self.pairs, format!("{key}|{source}"), PAIR_FAILURES, now, window);
        strike(&mut self.sources, source.to_string(), SOURCE_FAILURES, now, window);
        let (sources, reported_until) = self.targets.entry(key.to_string()).or_default();
        sources.retain(|_, &mut t| now - t < window);
        sources.insert(source.to_string(), now);
        let attacked = sources.len() >= ATTACK_SOURCES && now >= *reported_until;
        if attacked {
            *reported_until = now + window;
        }
        attacked
    }

    pub(crate) fn prune(&mut self, now: i64, window: i64) {
        let alive = |s: &mut Strikes| now < s.locked_until || s.failures.iter().any(|&t| now - t < window);
        self.pairs.retain(|_, s| alive(s));
        self.sources.retain(|_, s| alive(s));
        self.targets.retain(|_, (sources, until)| {
            sources.retain(|_, &mut t| now - t < window);
            !sources.is_empty() || now < *until
        });
        self.attempts.prune(now);
        self.registrations.prune(now);
    }
}

impl Game {
    pub(crate) fn login(&mut self, conn: u64, id: i64, login: Login, now: i64) -> Outcome {
        let session = &self.sessions[&conn];
        if session.account.is_some() {
            return Outcome::Failed("already_logged_in");
        }
        if session.login_id.is_some() {
            return Outcome::Failed("login_pending");
        }
        if login.client_version.0 != CLIENT_VERSION {
            return Outcome::Failed("bad_version");
        }
        let (ip, source, name) = (session.ip, session.source.clone(), login.account.0);
        let key = name.to_lowercase();
        let auth = &mut self.auth;
        let stored = self.accounts.get(&key).map(|a| (a.salt, a.hash, a.iterations));
        let refused = if !auth.attempts.allow(&source, now) {
            Some("rate_limited")
        } else if let Some(reason) = auth.lock_reason(&key, &source, now) {
            Some(reason)
        } else if auth.jobs.len() >= auth.max_jobs
            || auth.jobs.iter().filter(|s| **s == source).count() >= JOBS_PER_SOURCE
            // 同名的註冊還在算
            || (stored.is_none() && auth.registering.contains(&key))
        {
            Some("server_busy")
        } else if stored.is_none() && !auth.registrations.allow(&source, now) {
            Some("rate_limited")
        } else {
            None
        };
        if let Some(reason) = refused {
            self.security(conn, json!({"event": "auth.login_failed", "reason": reason, "target": key}));
            return Outcome::Failed(reason);
        }
        if stored.is_none() {
            self.auth.registering.insert(key.clone());
        }
        self.auth.jobs.push(source.clone());
        if let Some(session) = self.sessions.get_mut(&conn) {
            session.login_id = Some(id);
        }
        let (inputs, iterations, password) = (self.inputs.clone(), self.settings.password_iterations, login.password.0);
        tokio::task::spawn_blocking(move || {
            let result = match stored {
                Some((salt, hash, rounds)) => {
                    // 比對不隨第一個不同的位元組提早結束，不能從回應時間猜雜湊
                    let got = derive(&password, &salt, rounds);
                    HashResult::Verified(got.iter().zip(hash).fold(0, |d, (a, b)| d | (a ^ b)) == 0)
                }
                None => {
                    let salt = random::<16>();
                    let hash = derive(&password, &salt, iterations);
                    HashResult::Registered(Account { name: name.clone(), salt, hash, iterations })
                }
            };
            if let Some(inputs) = inputs {
                let _ = inputs.blocking_send(Input::Hashed(Hashed { conn, key, name, source, ip, result }));
            }
        });
        Outcome::Pending
    }

    /// 算到一半斷線的結果丟掉、註冊不建立，猜錯照樣累計鎖定
    pub(crate) fn finish_login(&mut self, done: Hashed) {
        let now = self.now_ms();
        if let Some(i) = self.auth.jobs.iter().position(|s| *s == done.source) {
            self.auth.jobs.swap_remove(i);
        }
        let Hashed { conn, key, name, source, ip, result } = done;
        let alive = self.sessions.get(&conn).is_some_and(|s| s.login_id.is_some());
        let outcome = match result {
            HashResult::Registered(account) => {
                self.auth.registering.remove(&key);
                if self.accounts.contains_key(&key) {
                    Err("server_busy")
                } else {
                    if alive {
                        self.accounts.insert(key.clone(), account);
                    }
                    Ok(())
                }
            }
            HashResult::Verified(true) => Ok(()),
            HashResult::Verified(false) => {
                if self.auth.fail(&key, &source, now, self.settings.lock_ms) {
                    let entry = json!({"event": "auth.account_under_attack", "target": key, "ip": ip.to_string()});
                    self.audit_source(&key, entry);
                }
                Err("wrong_password")
            }
        };
        let Some(id) = self.sessions.get_mut(&conn).and_then(|s| s.login_id.take()) else { return };
        let reply = match outcome {
            Err(reason) => {
                self.security(conn, json!({"event": "auth.login_failed", "reason": reason, "target": key}));
                self.note_reject(conn, now);
                encode_failure(id, reason, None)
            }
            Ok(()) => {
                self.auth.pairs.remove(&format!("{key}|{source}"));
                if let Some(&previous) = self.online.get(&key).filter(|&&c| c != conn) {
                    self.kick(previous, "duplicate_login");
                }
                self.online.insert(key.clone(), conn);
                if let Some(session) = self.sessions.get_mut(&conn) {
                    session.account = Some(key.clone());
                }
                let token = random::<24>().iter().map(|b| format!("{b:02x}")).collect();
                let account = self.accounts.get(&key).map_or(name, |a| a.name.clone());
                encode_reply(id, &LoginReply { token, account })
            }
        };
        self.reply(conn, reply);
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn password_hash_matches_rfc_7914_vector() {
        let out = super::derive("passwd", b"salt", 1);
        let hex: String = out.iter().map(|b| format!("{b:02x}")).collect();
        assert_eq!(hex, "55ac046e56e3089fec1691c22544b605f94185216dde0465e68b9d57c20dacbc");
    }
}
