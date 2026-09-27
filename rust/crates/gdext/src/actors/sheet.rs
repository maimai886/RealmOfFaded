//! 圖集：讀 meta.json、貼圖在背景讀、每一格畫哪裡，身體和紙娃娃圖層共用，格式照 docs/精靈圖規格.md。

use std::collections::BTreeSet;
use std::rc::Rc;

use godot::classes::{FileAccess, ResourceLoader, Texture2D};
use godot::prelude::*;
use serde_json::Value;

use super::cache;

const PAPER_DOLL: &str = "res://data/paper_doll.json";

#[derive(Clone, Copy, PartialEq)]
pub(super) struct Action {
    pub start: i32,
    pub frames: i32,
    pub fps: f32,
}

pub(super) struct Sheet {
    pub dir: String,
    pub size: Vector2,
    pub anchor: Vector2,
    pub pixels_per_meter: f32,
    pub directions: Vec<String>,
    pub nearest: bool,
    pub idle: Action,
    pub walk: Action,
    // 腳底到頭頂，公尺；meta 沒寫 top_row 是 None
    pub height: Option<f32>,
    pub layer: String,
    pub hides_hair: bool,
    meta: Value,
}

pub(super) fn read_json(path: &str) -> Option<Value> {
    FileAccess::file_exists(path)
        .then(|| serde_json::from_str(&FileAccess::get_file_as_string(path).to_string()).ok())?
}

impl Sheet {
    fn load(dir: &str) -> Option<Sheet> {
        let meta = read_json(&format!("{dir}/meta.json"))?;
        let number = |value: &Value| value.as_f64().map(|n| n as f32);
        let pair = |key: &str| Some(Vector2::new(number(&meta[key][0])?, number(&meta[key][1])?));
        let action = |name: &str| {
            let info = &meta["actions"][name];
            let start = number(&info["start"]).unwrap_or(0.0) as i32;
            Some(Action { start, frames: number(&info["frames"])? as i32, fps: number(&info["fps"])? })
        };
        let (anchor, pixels_per_meter) = (pair("anchor")?, number(&meta["pixels_per_meter"])?);
        // 身體要 top_row 算身高；圖層有 kind 或舊的 order，不用
        if meta["top_row"].is_null() && meta["kind"].is_null() && meta["order"].is_null() {
            godot_warn!("{dir} 的 meta.json 沒有 top_row，身高先用畫格頂端，請產圖端補");
        }
        Some(Sheet {
            dir: dir.to_owned(),
            size: pair("frame_size")?,
            height: number(&meta["top_row"]).map(|top| (anchor.y - top) / pixels_per_meter),
            anchor,
            pixels_per_meter,
            directions: meta["directions"].as_array()?.iter().filter_map(|d| Some(d.as_str()?.to_owned())).collect(),
            nearest: meta["filter"] == "nearest",
            idle: action("idle")?,
            walk: action("walk")?,
            layer: meta["layer"].as_str().unwrap_or_default().to_owned(),
            hides_hair: meta["hides_hair"] == true,
            meta,
        })
    }

    pub fn cached(dir: &str) -> Option<Rc<Sheet>> {
        cache(|c| c.sheets.get(dir).cloned()).or_else(|| {
            let sheet = Rc::new(Sheet::load(dir)?);
            cache(|c| c.sheets.insert(dir.to_owned(), sheet.clone()));
            Some(sheet)
        })
    }

    /// 圖層和身體的畫格、錨點、密度、方向、格數要一模一樣，對不上就不畫
    pub fn fits(&self, body: &Sheet) -> bool {
        let same = (self.size, self.anchor, self.pixels_per_meter, &self.directions)
            == (body.size, body.anchor, body.pixels_per_meter, &body.directions)
            && (self.idle.frames, self.walk.frames) == (body.idle.frames, body.walk.frames);
        if !same {
            godot_error!("{} 和身體 {} 的畫格、錨點、密度、方向或格數對不上，這一層不畫", self.dir, body.dir);
        }
        same
    }

    /// 這一格在圖集上的範圍、Sprite3D 的 offset、槽位、要不要水平翻；五方向圖集右半邊拿左半邊翻
    /// packed 圖層的槽位是 order 的 1 或 −1，cropped 圖層每一格自己寫
    pub fn cell(&self, action: &str, direction: i32, frame: i32) -> Option<(Rect2, Vector2, i32, bool)> {
        let flipped = self.directions.len() < 8 && direction > 4;
        let base = if flipped { 8 - direction } else { direction };
        let name = self.directions.get(base as usize)?;
        let (rect, mut corner, slot) = if self.meta["layout"] == "cropped" {
            let cell = &self.meta["cells"][action][name][frame as usize];
            let n = |i: usize| cell[i].as_f64().unwrap_or(0.0) as f32;
            (Rect2::new(Vector2::new(n(0), n(1)), Vector2::new(n(2), n(3))), Vector2::new(n(4), n(5)), n(6) as i32)
        } else {
            let info = if action == "walk" { self.walk } else { self.idle };
            let columns = self.meta["columns"].as_i64().unwrap_or(8) as i32;
            let index = info.start + base * info.frames + frame;
            let position = Vector2::new((index % columns) as f32, (index / columns) as f32) * self.size;
            let order = self.meta["order"][action][name][frame as usize].as_i64().unwrap_or(0) as i32;
            (Rect2::new(position, self.size), -self.anchor, order)
        };
        if rect.size.x <= 0.0 {
            return None;
        }
        if flipped {
            corner.x = -(corner.x + rect.size.x);
        }
        Some((rect, Vector2::new(corner.x + rect.size.x / 2.0, -(corner.y + rect.size.y / 2.0)), slot, flipped))
    }

    pub fn cropped(&self) -> bool {
        self.meta["layout"] == "cropped"
    }
}

/// 貼圖在背景執行緒讀，讀好之前回 None；出現新衣服的那一幀不卡
pub(super) fn texture(dir: &str) -> Option<Gd<Texture2D>> {
    if let Some(loaded) = cache(|c| c.textures.get(dir).cloned()) {
        return loaded;
    }
    let path = format!("{dir}/sheet.png").to_variant();
    let mut loader = ResourceLoader::singleton();
    // gdext 沒開 experimental-threads 就沒有型別化的背景讀取，用名字呼叫；狀態 1 讀取中、2 失敗、3 讀好
    let loaded = match loader.call("load_threaded_get_status", std::slice::from_ref(&path)).to::<i64>() {
        1 => return None,
        3 => loader.call("load_threaded_get", &[path]).try_to::<Gd<Texture2D>>().ok(),
        2 => None,
        _ => {
            loader.call("load_threaded_request", &[path]);
            return None;
        }
    };
    cache(|c| c.textures.insert(dir.to_owned(), loaded.clone()));
    loaded
}

/// 裝備欄位的舊圖層在身體前面和後面的槽位，照 data/paper_doll.json
pub(super) fn slot_for(equipment: &str, order: i32) -> i32 {
    let doll = doll();
    let layers = doll["layers"].as_array().cloned().unwrap_or_default();
    let layer = layers.iter().find(|l| l["slot"] == equipment);
    let side = if order > 0 { "front" } else { "back" };
    layer.and_then(|l| l[side].as_i64()).unwrap_or(order as i64) as i32
}

/// 槽位換成緊密的名次再乘間距，只推寫進深度的平面：身體 0、前面 1、2、3、後面 −1、−2
pub(super) fn depth_push(slot: i32, slots: &BTreeSet<i32>) -> f32 {
    let doll = doll();
    let number = |key: &str, default: f64| doll[key].as_f64().unwrap_or(default);
    let rank = if slot > 0 { slots.range(1..=slot).count() as i32 } else { -(slots.range(slot..0).count() as i32) };
    let rank = rank.clamp(number("outline_slot", -5.0) as i32 + 1, number("max_slot", 7.0) as i32);
    rank as f32 * number("slot_spacing", 0.004) as f32
}

fn doll() -> Rc<Value> {
    cache(|c| c.doll.get_or_insert_with(|| Rc::new(read_json(PAPER_DOLL).unwrap_or_default())).clone())
}
