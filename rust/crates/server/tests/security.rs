//! 惡意客戶端：改封包、洗頻、搶別人的帳號角色、加速移動、占連線，全部對真的伺服器黑箱送。

mod common;

use common::{Bot, audits};
use futures_util::future::join_all;
use serde_json::{Value, json};
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::tungstenite::protocol::frame::Frame;
use tokio_tungstenite::tungstenite::protocol::frame::coding::{Data, OpCode};

fn ping(id: Value) -> String {
    json!({"v": 1, "t": "ping", "id": id, "d": {}}).to_string()
}

#[tokio::test]
async fn broken_packets_are_kicked_with_the_reason_and_audited() {
    let server = common::server().await;
    let move_to = |x: &str| format!(r#"{{"v":1,"t":"move.to","id":1,"d":{{"x":{x},"z":0}}}}"#);
    let cases = [
        (format!(r#"{{"v":1,"t":"ping","id":1,"d":{{"x":"{}"}}}}"#, "a".repeat(8200)), "too_large"),
        (format!(r#"{{"v":1,"t":"ping","id":1,"d":{{"x":"{}"}}}}"#, "萌".repeat(3000)), "too_large"),
        ("{not json".into(), "bad_json"),
        (format!("{} {}", ping(json!(1)), r#"{"v":1}"#), "bad_json"),
        (String::new(), "bad_json"),
        (format!(r#"{{"v":1,"t":"ping","id":1,"d":{{"a":{}{}}}}}"#, "[".repeat(2000), "]".repeat(2000)), "bad_json"),
        (r#"{"v":1,"t":"ping","id":1,"d":{"s":"a\ud800b"}}"#.into(), "bad_json"),
        (r#"{"v":1,"t":"ping","id":1,"d":{"s":"a\u0000b"}}"#.into(), "bad_json"),
        (move_to("NaN"), "bad_json"),
        (move_to("Infinity"), "bad_json"),
        (move_to("1e999999"), "bad_json"),
        (move_to("1e400"), "bad_json"),
        (move_to(&"9".repeat(400)), "bad_json"),
        (r#"{"v":2,"t":"ping","id":1,"d":{}}"#.into(), "bad_version"),
        (r#"{"v":"1","t":"ping","id":1,"d":{}}"#.into(), "bad_version"),
        (r#"{"t":"ping","id":1,"d":{}}"#.into(), "bad_envelope"),
        ("[1,2,3]".into(), "bad_envelope"),
        (r#"{"v":1,"t":"ping","id":1,"d":{},"admin":true}"#.into(), "bad_envelope"),
        (r#"{"v":1,"t":"ping","id":1,"d":[]}"#.into(), "bad_envelope"),
        (r#"{"v":1,"t":7,"id":1,"d":{}}"#.into(), "bad_envelope"),
        (ping(json!("1")), "bad_envelope"),
        (ping(json!(1.5)), "bad_envelope"),
        (r#"{"v":1,"t":"ping","id":1e300,"d":{}}"#.into(), "bad_envelope"),
    ];
    for (text, reason) in &cases {
        let mut bot = Bot::connect(&server).await;
        bot.send_raw(text).await;
        assert_eq!(bot.kicked().await, *reason, "{text:.60}");
        assert_eq!(bot.close_code, Some(4000), "{reason} 的關閉代碼");
    }
    let kicks = audits(&server, "net.kick");
    assert_eq!(kicks.len(), 10, "同一個來源每分鐘只寫 10 筆，攻擊者灌不爆日誌");
    assert!(kicks.iter().all(|k| k["ip"] == "127.0.0.1" && k["reason"].is_string()), "稽核帶 IP 和原因");
}

#[tokio::test]
async fn raw_frames_are_kicked() {
    let server = common::server().await;
    let mut binary = Bot::connect(&server).await;
    binary.send_message(Message::binary(ping(json!(1)).into_bytes())).await;
    assert_eq!((binary.kicked().await.as_str(), binary.close_code), ("binary_frame", Some(4000)));
    let mut huge = Bot::connect(&server).await;
    huge.send_raw(&"a".repeat(20_000)).await;
    assert_eq!((huge.kicked().await.as_str(), huge.close_code), ("too_large", Some(4000)));
    let mut broken = Bot::connect(&server).await;
    let bytes = vec![0x7B, 0x22, 0xC0, 0xAF, 0x22, 0x7D];
    broken.send_message(Message::Frame(Frame::message(bytes, OpCode::Data(Data::Text), true))).await;
    broken.kicked().await;
    assert!(matches!(broken.close_code, Some(4000 | 1007)), "壞 UTF-8 的關閉代碼 {:?}", broken.close_code);
}

#[tokio::test]
async fn unknown_types_and_bad_ids_get_no_reply_and_count_as_violations() {
    let server = common::server().await;
    let mut bot = Bot::connect(&server).await;
    for (i, t) in ["admin.give_item", "resp", "kick", "world.enter", "move.dir", ""].iter().enumerate() {
        bot.send_raw(&json!({"v": 1, "t": t, "id": i + 1, "d": {}}).to_string()).await;
    }
    bot.send_raw(&ping(json!(0))).await;
    bot.send_raw(&ping(json!(-5))).await;
    assert!(bot.silent(300).await, "沒辦法回應的不回應");
    assert!(audits(&server, "net.violation").iter().any(|v| v["reason"] == "unknown_type"));

    let mut replay = Bot::connect(&server).await;
    assert_eq!(replay.request("ping", json!({})).await["ok"], true);
    replay.send_raw(&ping(json!(100))).await;
    assert_eq!(replay.reply_to(100).await["ok"], true, "id 可以跳號");
    for id in [100, 99, 1] {
        replay.send_raw(&ping(json!(id))).await;
        assert_eq!(replay.reply_to(id).await["reason"], "bad_id", "重放或倒退的 id {id}");
    }
    let max = 9_007_199_254_740_991i64;
    replay.send_raw(&ping(json!(max))).await;
    assert_eq!(replay.reply_to(max).await["ok"], true, "最大的安全整數 id");
    replay.send_raw(&ping(json!(201))).await;
    assert_eq!(replay.reply_to(201).await["reason"], "bad_id", "之後的小 id 全部拒絕");

    // 重放一則成功的建角不會多建一隻
    let mut player = Bot::connect(&server).await;
    player.login("replayer").await;
    let create = json!({"v": 1, "t": "char.create", "id": 50, "d": {"server_id": "dawn", "name": "重放", "gender": "male", "appearance": {}}});
    player.send_raw(&create.to_string()).await;
    assert_eq!(player.reply_to(50).await["ok"], true);
    player.send_raw(&create.to_string()).await;
    assert_eq!(player.reply_to(50).await["reason"], "bad_id");
    player.next_id = 51;
    let list = player.request("char.list", json!({"server_id": "dawn"})).await;
    assert_eq!(list["characters"].as_array().map(Vec::len), Some(1), "重放沒有多建一隻");
}

#[tokio::test]
async fn wrong_field_types_and_invisible_characters_are_rejected_without_kicking() {
    let server = common::server().await;
    let mut bot = Bot::connect(&server).await;
    let mut cases: Vec<(&str, Value, &str, &str)> =
        [json!({"a": 1}), json!(["a"]), json!(12345), Value::Null, json!(true)]
            .into_iter()
            .map(|id| ("char.list", json!({"server_id": id}), "bad_type", "server_id"))
            .collect();
    for text in [
        "a\nb",
        "a\u{1}b",
        "a\u{1b}b",
        "a\u{7f}b",
        "a\u{85}b",
        "\u{202e}gm",
        "a\u{2066}b",
        "a\u{2028}b",
        "a\u{200f}b",
        "a\u{ffff}b",
        "a\u{fdd0}b",
        "../c1",
    ] {
        cases.push(("char.list", json!({"server_id": text}), "bad_format", "server_id"));
    }
    cases.push(("char.list", json!({}), "missing_field", "server_id"));
    for (t, d, reason, field) in cases {
        let reply = bot.request(t, d.clone()).await;
        assert_eq!((reply["reason"].as_str(), reply["field"].as_str()), (Some(reason), Some(field)), "{d}");
    }
    assert!(bot.silent(200).await, "零星的型別錯誤只記違規不踢");
    // 角色名的雙向覆寫、零寬空白、全形英文、半形和全形空白都建不了
    let mut maker = Bot::connect(&server).await;
    maker.login("namer").await;
    for name in ["\u{202e}abc", "a\u{200b}b", "ＡＢＣ", "a b", "a　b"] {
        assert_eq!(maker.create(name).await["ok"], false, "{name:?} 建不了");
    }
}

#[tokio::test]
async fn flooding_is_rate_limited_then_kicked() {
    let server = common::server().await;
    let mut bot = Bot::connect(&server).await;
    let mut limited = 0;
    for _ in 0..40 {
        let reply = bot.request("ping", json!({})).await;
        limited += (reply["reason"] == "rate_limited") as u32;
    }
    assert!(limited >= 5, "每秒超過 30 則被擋，擋了 {limited} 則");
    while bot.kick.is_none() && !bot.request("ping", json!({})).await.is_null() {}
    assert_eq!(bot.kick.as_deref(), Some("violations"), "一直洗被踢");
    assert!(audits(&server, "net.violation").iter().any(|v| v["reason"] == "rate_limited"));
}

#[tokio::test]
async fn rejected_game_commands_do_not_kick_but_are_audited_as_suspicious() {
    let server = common::server().await;
    let (mut bot, _) = Bot::player(&server, "pusher", "推牆").await;
    for _ in 0..110 {
        assert_eq!(bot.request("move.to", json!({"x": 48.5, "z": 0})).await["reason"], "out_of_bounds");
        tokio::time::sleep(std::time::Duration::from_millis(40)).await;
    }
    assert!(bot.kick.is_none(), "被遊戲規則拒絕不算違規");
    assert_eq!(audits(&server, "net.suspicious").len(), 1, "寫一筆可疑稽核");
}

#[tokio::test]
async fn a_tick_full_of_moves_only_moves_one_step_and_spamming_gets_kicked() {
    let server = common::server().await;
    let (mut bot, me) = Bot::player(&server, "speeder", "加速").await;
    let spawn = [4.0, -39.0];
    let sends =
        (0..40).map(|i| json!({"v": 1, "t": "move.to", "id": i + 10, "d": {"x": 4.0 + (i % 5) as f64, "z": -35.0}}));
    for text in sends {
        bot.send_raw(&text.to_string()).await;
    }
    let mut limited = 0;
    let mut first_step = None;
    while first_step.is_none() {
        let message = bot.recv(2000).await.expect("收得到訊息");
        limited += (message["d"]["reason"] == "rate_limited") as u32;
        let entities = message["d"]["entities"].as_array().cloned().unwrap_or_default();
        first_step = entities.iter().find(|e| e["id"] == me && e["action"] == "move").cloned();
    }
    let step = first_step.unwrap();
    let moved =
        ((step["x"].as_f64().unwrap() - spawn[0]).powi(2) + (step["z"].as_f64().unwrap() - spawn[1]).powi(2)).sqrt();
    assert!(moved <= 0.176, "一個 tick 只走一步 0.175 公尺，走了 {moved}");
    assert!(limited >= 5, "超過每秒 30 則被擋");
    while bot.kick.is_none() && bot.is_open() {
        bot.send("move.to", json!({"x": 5.0, "z": -36.0})).await;
        bot.recv(5).await;
    }
    assert_eq!(bot.kicked().await, "violations");
    assert!(audits(&server, "net.kick").iter().any(|k| k["reason"] == "violations"));
}

#[tokio::test]
async fn move_targets_outside_the_map_are_refused_and_the_edge_is_fine() {
    let server = common::server().await;
    let (mut bot, me) = Bot::player(&server, "walker", "邊界").await;
    let refused = [
        (json!({"x": 48.01, "z": -39}), "out_of_bounds", ""),
        (json!({"x": -9999, "z": -39}), "out_of_bounds", ""),
        (json!({"x": 10000.5, "z": -39}), "out_of_range", "x"),
        (json!({"x": 1e300, "z": -39}), "out_of_range", "x"),
        (json!({"x": "4", "z": -39}), "bad_type", "x"),
        (json!({"x": [4], "z": -39}), "bad_type", "x"),
        (json!({"x": {"v": 4}, "z": -39}), "bad_type", "x"),
        (json!({"x": 4}), "missing_field", "z"),
    ];
    for (d, reason, field) in refused {
        let reply = bot.request("move.to", d.clone()).await;
        assert_eq!(reply["reason"], reason, "{d}");
        assert_eq!(reply["field"].as_str().unwrap_or(""), field, "{d}");
    }
    assert!(
        bot.pushes.iter().all(|p| p["t"] != "entity.state" || p["d"]["entities"][0]["action"] == "idle"),
        "被拒的移動沒動"
    );
    assert_eq!(bot.request("move.to", json!({"x": 4, "z": -48})).await["ok"], true, "邊界上的點合法");
    let [x, z] = bot.wait_until_stopped(me).await;
    assert!((-48.0..=48.0).contains(&x) && (-48.0..=48.0).contains(&z), "停在範圍內 {x} {z}");
}

#[tokio::test]
async fn silent_connections_time_out_and_live_ones_stay() {
    let server =
        common::server_with(|s| (s.login_timeout_ms, s.heartbeat_ms, s.idle_timeout_ms) = (1500, 1000, 2500)).await;
    let mut lurker = Bot::connect(&server).await;
    let mut pinger = Bot::connect(&server).await;
    pinger.login("pinger").await;
    let (mut sleeper, me) = Bot::player(&server, "sleeper", "睡覺").await;
    sleeper.request("move.to", json!({"x": 6, "z": -38})).await;
    let parked = sleeper.wait_until_stopped(me).await;
    for _ in 0..8 {
        lurker.request("ping", json!({})).await;
        pinger.request("ping", json!({})).await;
        tokio::time::sleep(std::time::Duration::from_millis(400)).await;
    }
    assert_eq!(lurker.kicked().await, "login_timeout", "沒登入一直 ping 也會被踢");
    assert!(pinger.kick.is_none(), "有回 ping 的一直留著");
    assert!(!sleeper.push("heartbeat").await.is_null(), "裝死先收到一次 heartbeat");
    assert_eq!(sleeper.kicked().await, "idle_timeout");
    let mut back = Bot::connect(&server).await;
    back.login("sleeper").await;
    back.request("char.enter", json!({"character_id": "c1"})).await;
    let enter = back.push("world.enter").await;
    assert_eq!([enter["self"]["x"].as_f64().unwrap(), enter["self"]["z"].as_f64().unwrap()], parked, "踢線前存了位置");
}

#[tokio::test]
async fn one_ip_gets_at_most_ten_sessions_and_new_connections_are_throttled() {
    let server = common::server().await;
    let mut bots = join_all((0..10).map(|_| Bot::connect(&server))).await;
    let mut extra = Bot::connect(&server).await;
    assert_eq!(extra.kicked().await, "too_many_connections");
    let mut other = Bot::connect_from(&server, "127.0.0.2".parse().unwrap()).await.unwrap();
    assert_eq!(other.request("ping", json!({})).await["ok"], true, "別的 IP 不受影響");
    bots.pop();
    tokio::time::sleep(std::time::Duration::from_millis(200)).await;
    let mut again = Bot::connect(&server).await;
    assert_eq!(again.request("ping", json!({})).await["ok"], true, "關掉一條可以再連");
    let mut opened = 12;
    for _ in 0..30 {
        opened += Bot::connect_from(&server, "127.0.0.1".parse().unwrap()).await.is_some() as u32;
    }
    assert_eq!(opened, 30, "同一個 IP 10 秒內最多新開 30 條");
}
