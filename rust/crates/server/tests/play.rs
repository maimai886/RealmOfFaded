//! 照玩法走一遍：兩個人進萌芽草原互相看得到，一個點樹後面繞過去停下，另一個看著他走。

mod common;

use std::time::Instant;

use common::Bot;
use rof_data::{Blocker, Bounds, MapData};
use rof_netcore::{Correction, Prediction, ServerClock};
use serde_json::{Value, json};

fn point(value: &Value) -> [f32; 2] {
    [value["x"].as_f64().unwrap() as f32, value["z"].as_f64().unwrap() as f32]
}

fn distance(a: [f32; 2], b: [f32; 2]) -> f32 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2)).sqrt()
}

#[tokio::test(flavor = "multi_thread")]
async fn clicking_behind_a_tree_walks_around_it_and_the_other_player_sees_it() {
    let server = common::server().await;
    let (mut alice, alice_id) = Bot::player(&server, "alice", "阿利").await;
    let enter = alice.push("world.enter").await;
    assert_eq!((enter["map"].as_str(), enter["self_id"].as_u64()), (Some("meadow"), Some(alice_id)));
    let mut blockers: Vec<Blocker> = Vec::new();
    loop {
        let batch = alice.push("world.blockers").await;
        blockers.extend(serde_json::from_value::<Vec<Blocker>>(batch["blockers"].clone()).unwrap());
        if blockers.len() == batch["total"].as_u64().unwrap() as usize {
            break;
        }
    }
    let spawn = point(&enter["self"]);
    let bounds: Bounds = serde_json::from_value(enter["bounds"].clone()).unwrap();
    let map = MapData {
        id: "meadow".into(),
        name: String::new(),
        scene: String::new(),
        bounds,
        player_spawn: spawn,
        blockers,
    };
    let speed = alice.push("self.stats").await["move_speed"].as_f64().unwrap() as f32;

    let (mut bob, bob_id) = Bot::player(&server, "bobby", "阿寶").await;
    assert_eq!(bob.push("entity.spawn").await["id"].as_u64(), Some(alice_id), "後進來的看得到先進來的");
    assert_eq!(alice.push("entity.spawn").await["id"].as_u64(), Some(bob_id), "先進來的看得到後進來的");

    // 客戶端的做法：時鐘和來回時間用 ping 對，之後每則 entity.state 再對，預測排在伺服器開始走的那一刻
    let clock_start = Instant::now();
    let now = || clock_start.elapsed().as_secs_f64() * 1000.0;
    let mut clock = ServerClock::default();
    for _ in 0..5 {
        let sent = now();
        let pong = alice.request("ping", json!({})).await;
        clock.sample(pong["time_ms"].as_f64().unwrap(), now());
        clock.record_rtt(now() - sent);
    }
    let mut prediction = Prediction::new(&map, spawn, speed);
    let target = [-4.1, -33.3];
    alice.send("move.to", json!({"x": target[0], "z": target[1]})).await;
    prediction.move_to(target, clock.command_apply_time(now()));

    let (mut worst, mut pulled, mut moved, mut last_frame) = (0.0f32, 0, false, now());
    let stopped = loop {
        let message = alice.recv(16).await;
        let frame = now();
        prediction.step(((frame - last_frame) / 1000.0) as f32, frame);
        last_frame = frame;
        let Some(message) = message.filter(|m| m["t"] == "entity.state") else { continue };
        let server_ms = message["d"]["tick"].as_f64().unwrap() * 50.0;
        clock.sample(server_ms, frame);
        let Some(me) = message["d"]["entities"].as_array().unwrap().iter().find(|e| e["id"] == alice_id) else {
            continue;
        };
        let (correction, error) = prediction.reconcile(point(me), frame, clock.lag_ms(frame, server_ms));
        worst = worst.max(error);
        pulled += (correction == Correction::Smooth) as u32;
        moved |= me["action"] == "move";
        if moved && me["action"] == "idle" {
            break point(me);
        }
    };
    for _ in 0..10 {
        let frame = now();
        prediction.step(((frame - last_frame) / 1000.0) as f32, frame);
        last_frame = frame;
    }
    eprintln!("預測和伺服器最大誤差 {worst:.4} 公尺，平滑拉回 {pulled} 次");
    assert!(distance(stopped, target) <= 0.1, "伺服器停在 {stopped:?}");
    assert!(distance(prediction.position(), stopped) <= 0.02, "預測停在 {:?}", prediction.position());
    assert!(worst < 0.12 && pulled == 0, "被拉回：最大誤差 {worst}");

    let mut seen_moving = false;
    let watched = loop {
        let state = bob.push("entity.state").await;
        assert!(!state.is_null(), "另一個人等不到他停下");
        let Some(her) = state["entities"].as_array().unwrap().iter().find(|e| e["id"] == alice_id) else { continue };
        seen_moving |= her["action"] == "move";
        if seen_moving && her["action"] == "idle" {
            break point(her);
        }
    };
    assert_eq!(watched, stopped, "另一個人看到他停在同一點");
}

#[tokio::test(flavor = "multi_thread")]
async fn a_player_who_walks_far_away_disappears_and_comes_back() {
    let server = common::server().await;
    let (mut alice, _) = Bot::player(&server, "alice", "阿利").await;
    let (mut bob, bob_id) = Bot::player(&server, "bobby", "阿寶").await;
    assert_eq!(alice.push("entity.spawn").await["id"].as_u64(), Some(bob_id));
    // 走到隔兩格、直線距離超過 20 公尺的地方，再走回來
    for [x, z] in [[-17.0, -36.0], [4.0, -38.0]] {
        bob.request("move.to", json!({"x": x, "z": z})).await;
        bob.wait_until_stopped(bob_id).await;
    }
    let mut seen = Vec::new();
    while let Some(message) = alice.recv(300).await {
        let d = &message["d"];
        let about_bob =
            d["id"] == bob_id || d["entities"].as_array().is_some_and(|e| e.iter().any(|e| e["id"] == bob_id));
        if about_bob {
            seen.push(message["t"].as_str().unwrap().to_string());
        }
    }
    let gone = seen.iter().position(|t| t == "entity.despawn").expect("走遠了要消失");
    let back = seen.iter().position(|t| t == "entity.spawn").expect("走回來要再出現");
    assert!(gone < back && seen[gone + 1..back].is_empty(), "看不到的時候收不到他的位置：{seen:?}");
    assert_eq!(seen.iter().filter(|t| *t == "entity.despawn").count(), 1, "不重複消失");
    assert_eq!(seen.iter().filter(|t| *t == "entity.spawn").count(), 1, "不重複出現");
}
