//! 惡意客戶端：搶別人的角色、跳過登入、重複登入、搶名字、洗註冊、猜密碼、拖慢密碼雜湊。

mod common;

use std::net::IpAddr;
use std::time::{Duration, Instant};

use common::{Bot, audits};
use rof_server::Server;
use serde_json::json;

fn ip(last: u8) -> IpAddr {
    IpAddr::from([127, 0, 0, last])
}

/// 每次開新連線登入一次就關，回傳 reason，成功是空字串
async fn try_login(server: &Server, from: u8, account: &str, password: &str) -> String {
    let mut bot = Bot::connect_from(server, ip(from)).await.expect("連得上");
    let reason = bot.login_with(account, password).await["reason"].as_str().unwrap_or("no_reply").to_string();
    drop(bot);
    tokio::time::sleep(Duration::from_millis(30)).await;
    reason
}

#[tokio::test]
async fn nobody_can_list_or_enter_other_peoples_characters() {
    let server = common::server().await;
    let (_alice, _) = Bot::player(&server, "alice", "阿利").await;
    let mut bob = Bot::connect(&server).await;
    bob.login("bobby").await;
    for (id, reason) in [("c1", "not_found"), ("c999", "not_found"), ("../c1", "bad_format")] {
        assert_eq!(bob.request("char.enter", json!({"character_id": id})).await["reason"], reason, "{id}");
    }
    let list = bob.request("char.list", json!({"server_id": "dawn"})).await;
    assert_eq!(list["characters"], json!([]), "看不到別人的角色");
}

#[tokio::test]
async fn commands_in_the_wrong_state_are_refused_and_pushing_it_gets_kicked() {
    let server = common::server().await;
    let mut stranger = Bot::connect(&server).await;
    let commands = [
        ("char.list", json!({"server_id": "dawn"})),
        ("char.create", json!({"server_id": "dawn", "name": "偷建", "gender": "male", "appearance": {}})),
        ("char.enter", json!({"character_id": "c1"})),
        ("move.to", json!({"x": 0, "z": 0})),
        ("move.stop", json!({})),
    ];
    for (t, d) in &commands {
        assert_eq!(stranger.request(t, d.clone()).await["reason"], "not_logged_in", "沒登入送 {t}");
    }
    while stranger.is_open() && !stranger.request("move.stop", json!({})).await.is_null() {}
    assert_eq!(stranger.kick.as_deref(), Some("violations"), "一直送被踢");

    let (mut alice, _) = Bot::player(&server, "alice", "阿利").await;
    assert_eq!(alice.request("char.list", json!({"server_id": "dawn"})).await["reason"], "in_world");
    assert_eq!(alice.login("alice").await["reason"], "already_logged_in");
}

#[tokio::test]
async fn logging_in_again_kicks_the_first_connection_and_leaves_one_body() {
    let server = common::server().await;
    let (mut first, first_id) = Bot::player(&server, "twin", "雙胞").await;
    let (mut watcher, _) = Bot::player(&server, "watch", "旁觀").await;
    assert_eq!(watcher.push("entity.spawn").await["id"].as_u64(), Some(first_id));
    let mut second = Bot::connect(&server).await;
    assert_eq!(second.login("TWIN").await["ok"], true, "帳號不分大小寫");
    assert_eq!(first.kicked().await, "duplicate_login");
    assert_eq!(watcher.push("entity.despawn").await["id"].as_u64(), Some(first_id), "舊的身體離開");
    let entered = second.request("char.enter", json!({"character_id": "c1"})).await;
    assert_eq!(watcher.push("entity.spawn").await["id"], entered["self_id"], "新的身體進來");
    let servers = second.request("server.list", json!({})).await;
    assert_eq!(servers["servers"][0]["online"], 2, "同一個角色只有一個身體");
}

#[tokio::test]
async fn names_are_unique_ignoring_case_and_creating_is_limited() {
    let server = common::server().await;
    let (mut a, mut b) = (Bot::connect(&server).await, Bot::connect(&server).await);
    a.login("racer1").await;
    b.login("racer2").await;
    let create = |name: &str| json!({"server_id": "dawn", "name": name, "gender": "male", "appearance": {}});
    let (id_a, id_b) = (a.send("char.create", create("Hero")).await, b.send("char.create", create("hERO")).await);
    let results = [a.reply_to(id_a).await, b.reply_to(id_b).await];
    assert_eq!(results.iter().filter(|r| r["ok"] == true).count(), 1, "同時搶同名只有一個成功");
    assert!(results.iter().any(|r| r["reason"] == "name_taken"));

    let mut c = Bot::connect(&server).await;
    c.login("maker").await;
    let expected = [
        ("小一", ""),
        ("小二", ""),
        ("GM", "name_reserved"),
        ("小三", ""),
        ("小四", "slots_full"),
        ("小五", "rate_limited"),
    ];
    for (name, reason) in expected {
        assert_eq!(c.request("char.create", create(name)).await["reason"], reason, "{name}");
    }
    let mut d = Bot::connect(&server).await;
    d.login("dresser").await;
    let bad = json!({"server_id": "dawn", "name": "亂穿", "gender": "male", "appearance": {"hair_style": 4}});
    assert_eq!(d.request("char.create", bad).await["reason"], "bad_appearance", "男生只有 4 種髮型");
}

#[tokio::test]
async fn one_ip_can_register_at_most_twenty_accounts_an_hour() {
    let server = common::server().await;
    for i in 0..20 {
        assert_eq!(try_login(&server, 1, &format!("bulk{i}"), "secret1").await, "", "第 {i} 個");
    }
    assert_eq!(try_login(&server, 1, "bulk20", "secret1").await, "rate_limited");
    assert_eq!(try_login(&server, 2, "bulk20", "secret1").await, "", "別的 IP 照常註冊");
}

#[tokio::test]
async fn guessing_passwords_locks_only_the_guesser_and_unlocks_later() {
    let server = common::server_with(|s| s.lock_ms = 1500).await;
    assert_eq!(try_login(&server, 1, "victim", "right1").await, "");
    assert_eq!(try_login(&server, 3, "other1", "right1").await, "");
    for _ in 0..5 {
        assert_eq!(try_login(&server, 1, "victim", "wrong1").await, "wrong_password");
    }
    assert_eq!(try_login(&server, 1, "victim", "wrong1").await, "locked", "錯 5 次這個 IP 鎖這個帳號，不再比對");
    assert_eq!(try_login(&server, 1, "victim", "right1").await, "locked");
    assert_eq!(try_login(&server, 2, "victim", "right1").await, "", "陌生人鎖不住別人的帳號");
    assert_eq!(try_login(&server, 1, "other1", "wrong1").await, "wrong_password");
    assert_eq!(try_login(&server, 1, "other1", "wrong1").await, "wrong_password");
    assert_eq!(try_login(&server, 1, "other1", "right1").await, "ip_banned", "同一個 IP 錯 7 次整個封");
    tokio::time::sleep(Duration::from_millis(1600)).await;
    assert_eq!(try_login(&server, 1, "victim", "right1").await, "", "時間到解除");

    for from in [4, 5, 6] {
        assert_eq!(try_login(&server, from, "other1", "guess1").await, "wrong_password");
    }
    assert_eq!(audits(&server, "auth.account_under_attack").len(), 1, "三個 IP 一起猜只寫一筆");
}

#[tokio::test]
async fn password_hashing_never_stalls_the_server() {
    let server = common::server_with(|s| s.password_iterations = 600_000).await;
    let mut slow = Bot::connect(&server).await;
    let login =
        |account: &str| json!({"account": account, "password": "secret1", "client_version": common::CLIENT_VERSION});
    let hashing = slow.send("auth.login", login("slowpoke")).await;
    let mut other = Bot::connect(&server).await;
    let started = Instant::now();
    other.request("ping", json!({})).await;
    assert!(started.elapsed() < Duration::from_millis(100), "雜湊中 ping 不用等");
    assert_eq!(slow.request("auth.login", login("slowpoke")).await["reason"], "login_pending");
    assert_eq!(slow.reply_to(hashing).await["ok"], true);

    // 算到一半斷線，結果丟掉、帳號不建立
    let mut ghost = Bot::connect(&server).await;
    ghost.send("auth.login", login("ghost")).await;
    drop(ghost);
    tokio::time::sleep(Duration::from_secs(2)).await;
    assert_eq!(try_login(&server, 1, "ghost", "another1").await, "", "斷線的註冊沒有留下來");

    // 同一個來源同時最多 2 個在算
    let mut crowd = Vec::new();
    for i in 0..3 {
        let mut bot = Bot::connect(&server).await;
        let id = bot.send("auth.login", login(&format!("crowd{i}"))).await;
        crowd.push((bot, id));
    }
    let mut busy = 0;
    for (bot, id) in &mut crowd {
        busy += (bot.reply_to(*id).await["reason"] == "server_busy") as u32;
    }
    assert_eq!(busy, 1, "第三個回忙碌");
}
