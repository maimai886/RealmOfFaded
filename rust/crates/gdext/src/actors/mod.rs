//! 角色的紙片顯示：身體和紙娃娃圖層各一片正對鏡頭的紙片，照槽位疊起來，數字照 docs/M1舊行為.md 第 7 節。

mod grading;
mod sheet;

use std::cell::RefCell;
use std::collections::{BTreeSet, HashMap};
use std::f32::consts::{FRAC_PI_4, TAU};
use std::rc::Rc;

use godot::classes::environment::AmbientSource;
use godot::classes::geometry_instance_3d::ShadowCastingSetting;
use godot::classes::{
    DirectionalLight3D, Font, FontVariation, INode3D, ImageTexture, Label, LabelSettings, Script, Shader,
    ShaderMaterial, Sprite3D, Texture2D, WorldEnvironment,
};
use godot::global::randf;
use godot::prelude::*;
use grading::{GradingProbe, environment_of, key_of};
use serde_json::Value;
use sheet::{Sheet, data, depth_push, slot_for, texture};

const BODY_DIR: &str = "res://assets/generated/sprites/characters/body";
const LAYER_DIR: &str = "res://assets/generated/sprites/characters/layers";
// 男女共用底板，女生沒有自己那份時用男生的
const SHARED_GENDER: &str = "male";
const SPRITE_SHADER: &str = "res://assets/shaders/actor_sprite.gdshader";
// 手繪像素圖集走銳利雙線性，由 meta 的 filter 決定
const PIXEL_SHADER: &str = "res://assets/shaders/actor_sprite_pixel.gdshader";
const SHADOW_SHADER: &str = "res://assets/shaders/actor_shadow.gdshader";
const ACTORS: &str = "res://data/actors.json";
// 離方向格子邊界不到這麼多格就不換方向，斜走才不會來回閃
const DIRECTION_HYSTERESIS: f32 = 0.08;
const TURN_SPEED: f32 = 0.05;
const IDLE_SPEED: f32 = 0.15;
const MIN_PLAYBACK: f32 = 0.55;
const MAX_PLAYBACK: f32 = 2.6;
// 起步那一幀直接跳到目標的 0.7 倍，再 0.05 秒追上；停下 0.07 秒收，太長腳會在地上磨
const SPEED_START_JUMP: f32 = 0.7;
const SPEED_RISE_S: f32 = 0.05;
const SPEED_FALL_S: f32 = 0.07;
// 站著呼吸的起伏佔身高的比例，約一個像素，照舊專案 sprite_actor.gd；走路的起伏圖裡已經畫了
const BOB_IDLE: f32 = 0.012;
const BOB_IDLE_PERIOD_S: f32 = 2.6;
// 受光只補一層時段的味道，圖上已經畫了明暗，多了會髒；舊專案 map_environment.gd 的 sprite_lit_amount
const LIT_AMOUNT: f32 = 0.45;
// 環境光取天空時沒有顏色可讀，用舊專案白天的代表色
const SKY_AMBIENT: Color = Color::from_rgb(0.6, 0.66, 0.78);
// 換地圖時環境會重建，每隔這麼久確認一次色調映射有沒有變
const GRADING_CHECK_S: f64 = 0.5;

/// 所有角色共用的圖集、貼圖、材質、反查表、受光，做一次掛著，生角色那一幀不新建
#[derive(Default)]
struct Cache {
    sheets: HashMap<String, Rc<Sheet>>,
    // None 是讀失敗
    textures: HashMap<String, Option<Gd<Texture2D>>>,
    materials: HashMap<String, Gd<ShaderMaterial>>,
    // 環境的 key 對到反查表，None 是還在量
    grading: HashMap<String, Option<Gd<ImageTexture>>>,
    light: Vec<(&'static str, Variant)>,
    // 別人的名字、自己的名字
    names: Vec<Gd<LabelSettings>>,
    // 讀過的資料檔
    data: HashMap<&'static str, Rc<Value>>,
}

thread_local! {
    static CACHE: RefCell<Cache> = RefCell::default();
}

fn cache<R>(f: impl FnOnce(&mut Cache) -> R) -> R {
    CACHE.with_borrow_mut(f)
}

/// 擴充結束時由 lib.rs 呼叫；留到行程結束才放的話 Godot 已經關了，放 Gd 會 panic
pub fn release() {
    cache(|c| *c = Cache::default());
}

/// 面向換算成八方向：0 下、1 左下、2 左…順時針；離邊界不到遲滯量就維持目前的
fn pick_direction(facing: f32, camera_yaw: f32, current: i32) -> i32 {
    let units = ((camera_yaw - facing) / FRAC_PI_4).rem_euclid(8.0);
    let offset = (units - current as f32 + 4.0).rem_euclid(8.0) - 4.0;
    if offset.abs() <= 0.5 + DIRECTION_HYSTERESIS { current } else { units.round() as i32 % 8 }
}

// 和畫面更新率無關的平滑，60Hz 和 120Hz 一樣快
fn ease_toward(current: f32, wanted: f32, seconds: f32, delta: f32) -> f32 {
    current + (wanted - current) * (1.0 - (-delta / seconds).exp())
}

/// 身體或一層紙娃娃；equipment 是舊圖層照 data/paper_doll.json 找前後槽位用的裝備欄位
struct Part {
    sheet: Rc<Sheet>,
    sprite: Gd<Sprite3D>,
    equipment: String,
    ready: bool,
}

#[derive(GodotClass)]
#[class(init, base=Node3D)]
pub struct Actor {
    base: Base<Node3D>,
    gender: String,
    // 第一個是身體，後面是圖層
    parts: Vec<Part>,
    caster: Option<Gd<Sprite3D>>,
    facing: f32,
    direction: i32,
    wanted_speed: f32,
    display_speed: f32,
    action: &'static str,
    frame: i32,
    frame_time: f32,
    shown: Option<(&'static str, i32, i32)>,
    bob_phase: f32,
    grading_key: Option<String>,
    grading_wait: f64,
    // 名字和它排在腳下幾個畫面像素
    name: Option<(Gd<Label>, f32)>,
}

#[godot_api]
impl Actor {
    #[func]
    pub(crate) fn setup(&mut self, gender: GString, _appearance: VarDictionary) {
        let Some(sheet) = Sheet::cached(&format!("{BODY_DIR}/{gender}_novice"))
            .or_else(|| Sheet::cached(&format!("{BODY_DIR}/{SHARED_GENDER}_novice")))
        else {
            godot_error!("讀不到初心者底板圖集：{gender}");
            return;
        };
        self.setup_sheet(sheet, gender);
    }

    fn setup_sheet(&mut self, sheet: Rc<Sheet>, gender: GString) {
        let mut body = self.part(sheet, String::new());
        let mut caster = Sprite3D::new_alloc();
        caster.set_region_enabled(true);
        caster.set_pixel_size(body.sprite.get_pixel_size());
        caster.set_cast_shadows_setting(ShadowCastingSetting::SHADOWS_ONLY);
        // 替身側身對著太陽，會超出照正面算的包圍盒
        caster.set_extra_cull_margin(2.0);
        body.sprite.add_child(&caster);
        (self.gender, self.caster) = (gender.to_string(), Some(caster));
        self.parts = vec![body];
        // 每個人的起伏錯開，一群人才不會整齊地一起上下
        self.bob_phase = randf() as f32 * TAU;
    }

    /// 裝備欄位對到圖層資料夾名稱，例如 {"weapon": "Knife"}；先找接性別的那一份
    #[func]
    pub(crate) fn set_layers(&mut self, layers: VarDictionary) {
        for mut part in self.parts.drain(1..).collect::<Vec<_>>() {
            part.sprite.queue_free();
        }
        let Some(body) = self.parts.first().map(|p| p.sheet.clone()) else { return };
        for (equipment, name) in layers.iter_shared() {
            let own = format!("{LAYER_DIR}/{name}_{}", self.gender);
            let Some(sheet) = Sheet::cached(&own).or_else(|| Sheet::cached(&format!("{LAYER_DIR}/{name}"))) else {
                godot_error!("讀不到圖層：{name}");
                continue;
            };
            if sheet.fits(&body) {
                let part = self.part(sheet, equipment.to_string());
                self.parts.push(part);
            }
        }
        (self.shown, self.grading_key) = (None, None);
    }

    /// velocity 是地面上的 x、z 速度，公尺每秒；camera_yaw 是鏡頭繞 Y 軸的弧度
    #[func]
    pub(crate) fn set_motion(&mut self, velocity: Vector2, camera_yaw: f32) {
        let speed = velocity.length();
        if speed > TURN_SPEED {
            self.facing = velocity.x.atan2(velocity.y);
        }
        self.direction = pick_direction(self.facing, camera_yaw, self.direction);
        self.wanted_speed = speed;
        if self.display_speed < IDLE_SPEED && speed >= IDLE_SPEED {
            self.display_speed = speed * SPEED_START_JUMP;
        }
    }

    /// 地圖蓋好後呼叫一次：照地圖場景的 Sun 和 WorldEnvironment 給所有角色受光
    #[func]
    pub(crate) fn light_from(map: Gd<Node>) {
        let sun = map.try_get_node_as::<DirectionalLight3D>("Sun");
        let world = map.try_get_node_as::<WorldEnvironment>("WorldEnvironment");
        let (Some(sun), Some(environment)) = (sun, world.and_then(|w| w.get_environment())) else {
            return godot_error!("地圖 {} 沒有 Sun 或 WorldEnvironment，角色不受光", map.get_name());
        };
        let sun_light = sun.get_color() * sun.get_param(godot::classes::light_3d::Param::ENERGY);
        let ambient = if environment.get_ambient_source() == AmbientSource::COLOR {
            environment.get_ambient_light_color()
        } else {
            SKY_AMBIENT
        } * environment.get_ambient_light_energy();
        // 以中間調為基準換算，角色不會被太陽推到爆白
        let mid = ambient + sun_light * 0.5;
        let scale = 1.0 / (mid.r * 0.299 + mid.g * 0.587 + mid.b * 0.114).max(0.02);
        let rgb = |c: Color| Vector3::new(c.r, c.g, c.b) * scale;
        let light = vec![
            ("lit_amount", LIT_AMOUNT.to_variant()),
            ("sun_direction", (-sun.get_transform().basis.col_c()).to_variant()),
            ("sun_color", rgb(sun_light).to_variant()),
            ("ambient_color", rgb(ambient).to_variant()),
        ];
        cache(|c| {
            for material in c.materials.values_mut() {
                light.iter().for_each(|(name, value)| material.set_shader_parameter(*name, value));
            }
            c.light = light;
        });
    }

    /// 名字畫在腳下，照舊專案 name_plates.gd：自己的字大一級、往下讓開 HP 和 SP 條
    pub(crate) fn set_display_name(&mut self, name: String, own: bool) {
        let mut label = Label::new_alloc();
        label.set_text(&name);
        label.set_label_settings(&name_settings(own));
        self.base_mut().add_child(&label);
        self.name = Some((label, if own { 26.0 } else { 14.0 }));
    }

    fn part(&mut self, sheet: Rc<Sheet>, equipment: String) -> Part {
        let mut sprite = Sprite3D::new_alloc();
        sprite.set_region_enabled(true);
        sprite.set_pixel_size(1.0 / sheet.pixels_per_meter);
        sprite.set_cast_shadows_setting(ShadowCastingSetting::OFF);
        sprite.set_visible(false);
        self.base_mut().add_child(&sprite);
        Part { sheet, sprite, equipment, ready: false }
    }

    fn place_name(&mut self) {
        let Some(camera) = self.base().get_viewport().and_then(|v| v.get_camera_3d()) else { return };
        let at = self.base().get_global_position();
        let Some((label, down)) = self.name.as_mut() else { return };
        label.set_visible(!camera.is_position_behind(at));
        let size = label.get_minimum_size();
        label.set_position((camera.unproject_position(at) + Vector2::new(-size.x / 2.0, *down - size.y / 2.0)).round());
    }

    // 貼圖讀好的那一層才掛材質；環境的色調映射換了每一層一起換
    fn sync_materials(&mut self) {
        let Some(viewport) = self.base().get_viewport() else { return };
        let wanted = environment_of(&viewport).map_or(String::new(), |environment| key_of(&environment));
        // 還在量的環境先用不抵銷的材質，量好下一次確認時再換
        let (key, lut) = match cache(|c| c.grading.get(&wanted).cloned()) {
            _ if wanted.is_empty() => (wanted, None),
            Some(Some(lut)) => (wanted, Some(lut)),
            Some(None) => (String::new(), None),
            None => {
                GradingProbe::start(&viewport, &wanted);
                (String::new(), None)
            }
        };
        let changed = self.grading_key.as_ref() != Some(&key);
        for (index, part) in self.parts.iter_mut().enumerate() {
            if part.ready && !changed {
                continue;
            }
            let Some(sheet_texture) = texture(&part.sheet.dir) else { continue };
            part.sprite.set_texture(&sheet_texture);
            part.sprite.set_material_override(&material(&part.sheet, &sheet_texture, &key, lut.clone()));
            if let (0, Some(caster)) = (index, self.caster.as_mut()) {
                caster.set_texture(&sheet_texture);
                caster.set_material_override(&material(&part.sheet, &sheet_texture, "shadow", None));
            }
            (part.ready, self.shown) = (true, None);
        }
        if self.parts.iter().all(|p| p.ready) {
            self.grading_key = Some(key);
        }
    }

    // 每一層照這一格的槽位疊；hides_hair 的頭飾戴著時不畫頭髮
    fn show_frame(&mut self) {
        let hide_hair = self.parts.iter().any(|p| p.sheet.hides_hair);
        let mut slots = BTreeSet::new();
        let mut shown = Vec::new();
        for part in &mut self.parts {
            let hidden = hide_hair && part.sheet.layer.starts_with("hair");
            let cell = part.sheet.cell(self.action, self.direction, self.frame).filter(|_| part.ready && !hidden);
            part.sprite.set_visible(cell.is_some());
            let Some((rect, offset, slot, flipped)) = cell else { continue };
            let slot = if part.sheet.cropped() || slot == 0 { slot } else { slot_for(&part.equipment, slot) };
            slots.insert(slot);
            shown.push((part.sprite.clone(), slot));
            part.sprite.set_region_rect(rect);
            part.sprite.set_flip_h(flipped);
            part.sprite.set_offset(offset);
            // 受光照這一格的左右算圓柱法線、銳利取樣夾在這一格裡；flip_h 只換 UV，法線的左右要自己轉回來
            let size = part.sprite.get_texture().map_or(Vector2::ONE, |t| t.get_size());
            let uv = Vector4::new(
                rect.position.x / size.x,
                rect.position.y / size.y,
                rect.size.x / size.x,
                rect.size.y / size.y,
            );
            part.sprite.set_instance_shader_parameter("frame_uv", &uv.to_variant());
            part.sprite.set_instance_shader_parameter("flip_sign", &(if flipped { -1.0 } else { 1.0 }).to_variant());
        }
        for (mut sprite, slot) in shown {
            sprite.set_instance_shader_parameter("depth_push", &depth_push(slot, &slots).to_variant());
        }
        let (Some(body), Some(caster)) = (self.parts.first(), self.caster.as_mut()) else { return };
        caster.set_region_rect(body.sprite.get_region_rect());
        caster.set_flip_h(body.sprite.is_flipped_h());
        caster.set_offset(body.sprite.get_offset());
    }

    // 站著是對稱的慢呼吸，每一層跟著身體一起動
    fn bob(&mut self, delta: f32, walking: bool) {
        self.bob_phase += delta * TAU / BOB_IDLE_PERIOD_S;
        let lift = if walking { 0.0 } else { (self.bob_phase.sin() * 0.5 + 0.5) * BOB_IDLE };
        let height =
            self.parts.first().map_or(0.0, |p| p.sheet.height.unwrap_or(p.sheet.anchor.y / p.sheet.pixels_per_meter));
        for part in &mut self.parts {
            part.sprite.set_position(Vector3::new(0.0, lift * height, 0.0));
        }
    }
}

#[godot_api]
impl INode3D for Actor {
    fn process(&mut self, delta: f64) {
        let Some(body) = self.parts.first() else { return };
        let (idle, walk) = (body.sheet.idle, body.sheet.walk);
        self.grading_wait -= delta;
        if self.grading_wait <= 0.0 || self.parts.iter().any(|p| !p.ready) {
            self.grading_wait = GRADING_CHECK_S;
            self.sync_materials();
        }
        let delta = delta as f32;
        self.display_speed = if self.wanted_speed > self.display_speed {
            ease_toward(self.display_speed, self.wanted_speed, SPEED_RISE_S, delta)
        } else {
            Some(ease_toward(self.display_speed, self.wanted_speed, SPEED_FALL_S, delta))
                .filter(|s| *s >= 0.01)
                .unwrap_or(0.0)
        };
        let walking = self.display_speed >= IDLE_SPEED;
        let (name, action) = if walking { ("walk", walk) } else { ("idle", idle) };
        if self.action != name {
            (self.action, self.frame, self.frame_time) = (name, 0, 0.0);
        }
        let playback =
            if walking { (self.display_speed / walk_reference_speed()).clamp(MIN_PLAYBACK, MAX_PLAYBACK) } else { 1.0 };
        self.frame_time += delta * playback * action.fps;
        self.frame = (self.frame + self.frame_time as i32) % action.frames;
        self.frame_time = self.frame_time.fract();
        let shown = Some((name, self.direction, self.frame));
        if self.shown != shown {
            self.shown = shown;
            self.show_frame();
        }
        self.bob(delta, walking);
        self.place_name();
    }
}

// 走路動作倍率 1 對應的移動速度，照 data/actors.json
fn walk_reference_speed() -> f32 {
    data(ACTORS)["walk_reference_speed"].as_f64().unwrap_or(3.15) as f32
}

// 一張圖集一種環境一份材質；key 是 shadow 時給影子替身
fn material(sheet: &Sheet, texture: &Gd<Texture2D>, key: &str, lut: Option<Gd<ImageTexture>>) -> Gd<ShaderMaterial> {
    cache(|c| {
        let entry = c.materials.entry(format!("{}|{key}", sheet.dir)).or_insert_with(|| {
            let shader = match key {
                "shadow" => SHADOW_SHADER,
                _ if sheet.nearest => PIXEL_SHADER,
                _ => SPRITE_SHADER,
            };
            let mut material = ShaderMaterial::new_gd();
            material.set_shader(&load::<Shader>(shader));
            material.set_shader_parameter("sheet", &texture.to_variant());
            if let Some(lut) = lut {
                material.set_shader_parameter("grading_enabled", &1.to_variant());
                material.set_shader_parameter("grading_lut", &lut.to_variant());
                material.set_shader_parameter("grading_ceiling", &lut.get_meta("ceiling"));
            }
            c.light.iter().for_each(|(name, value)| material.set_shader_parameter(*name, value));
            material
        });
        entry.clone()
    })
}

// 粗體白字加右下一格深色影子，中文小字描邊會糊；字級和顏色取介面的 ui_theme.gd
fn name_settings(own: bool) -> Gd<LabelSettings> {
    if let Some(settings) = cache(|c| c.names.get(own as usize).cloned()) {
        return settings;
    }
    let mut theme = load::<Script>("res://src/ui/ui_theme.gd");
    let constants = theme.get_script_constant_map();
    let mut bold = FontVariation::new_gd();
    bold.set_base_font(&theme.call("font", &["body".to_variant()]).to::<Gd<Font>>());
    bold.set_variation_embolden(0.6);
    let names = ["FONT_SMALL", "FONT_BODY"].map(|size| {
        let mut settings = LabelSettings::new_gd();
        settings.set_font(&bold);
        settings.set_font_size(constants.at(size).to());
        settings.set_font_color(constants.at("TEXT_BODY").to());
        settings.set_shadow_color(constants.at("OUTLINE").to());
        settings.set_shadow_size(0);
        settings.set_shadow_offset(Vector2::ONE);
        settings
    });
    cache(|c| c.names = names.to_vec());
    names[own as usize].clone()
}

/// 預覽：萌芽草原中央石板，男生一排走路、女生一排站著，各八個方向，都拿著小刀
#[derive(GodotClass)]
#[class(init, base=Node3D)]
struct ActorPreview {
    base: Base<Node3D>,
    actors: Vec<(Gd<Actor>, Vector2)>,
}

#[godot_api]
impl INode3D for ActorPreview {
    fn ready(&mut self) {
        let map = crate::map::build("meadow");
        self.base_mut().add_child(&map);
        Actor::light_from(map.upcast());
        let camera = self.base().get_viewport().and_then(|v| v.get_camera_3d());
        let yaw = camera.as_ref().map_or(0.0, |c| c.get_global_rotation().y);
        // --body=圖集資料夾：只放一個站著一個走路、都面向 sw；--at=x,z 挪到那塊地，--cam= 鏡頭距離
        if let Some(dir) = crate::shot::arg("--body=") {
            let Some(sheet) = Sheet::cached(&dir) else { return godot_error!("讀不到圖集：{dir}") };
            let at: Vec<f32> = crate::shot::arg("--at=").unwrap_or_default().split(',').filter_map(|n| n.parse().ok()).collect();
            let at = Vector3::new(at.first().copied().unwrap_or(0.0), 0.0, at.get(1).copied().unwrap_or(0.0));
            let distance = crate::shot::arg("--cam=").and_then(|n| n.parse().ok()).unwrap_or(52.0_f32);
            if let Some(mut camera) = camera {
                camera.set_global_position(at + Vector3::new(0.0, 1.0, 1.0) * distance * FRAC_PI_4.sin());
            }
            let facing = yaw - FRAC_PI_4;
            for (offset, speed) in [(-0.6, 0.1), (0.6, 3.5)] {
                let mut actor = Actor::new_alloc();
                actor.set_position(at + Vector3::new(offset, 0.0, 0.0));
                actor.bind_mut().setup_sheet(sheet.clone(), "male".into());
                self.base_mut().add_child(&actor);
                self.actors.push((actor, Vector2::new(facing.sin(), facing.cos()) * speed));
            }
            return;
        }
        let mut layers = VarDictionary::new();
        layers.set("weapon", "Knife");
        // 玩家移動速度 3.5；0.1 過了轉身門檻、不到走路門檻，站著面向那一方
        for (row, gender, speed) in [(-1.6, "male", 3.5), (1.6, "female", 0.1)] {
            for index in 0..8 {
                let facing = yaw - index as f32 * FRAC_PI_4;
                let mut actor = Actor::new_alloc();
                actor.set_position(Vector3::new((index as f32 - 3.5) * 2.2, 0.0, row));
                actor.bind_mut().setup(gender.into(), VarDictionary::new());
                actor.bind_mut().set_layers(layers.clone());
                self.base_mut().add_child(&actor);
                self.actors.push((actor, Vector2::new(facing.sin(), facing.cos()) * speed));
            }
        }
    }

    fn process(&mut self, _delta: f64) {
        let yaw = self.base().get_viewport().and_then(|v| v.get_camera_3d()).map_or(0.0, |c| c.get_global_rotation().y);
        for (actor, velocity) in &mut self.actors {
            actor.bind_mut().set_motion(*velocity, yaw);
        }
    }
}
