//! 角色的紙片顯示：多方向圖集貼在正對鏡頭的紙片上，格式照 docs/精靈圖規格.md，數字照 docs/M1舊行為.md 第 7 節。

use std::cell::RefCell;
use std::collections::HashMap;
use std::f32::consts::{FRAC_PI_4, TAU};

use godot::classes::camera_3d::ProjectionType;
use godot::classes::environment::{AmbientSource, BgMode};
use godot::classes::geometry_instance_3d::ShadowCastingSetting;
use godot::classes::image::Format;
use godot::classes::sub_viewport::UpdateMode;
use godot::classes::{
    Camera3D, DirectionalLight3D, Environment, FileAccess, Font, FontVariation, INode3D, ISubViewport, Image,
    ImageTexture, Label, LabelSettings, MeshInstance3D, QuadMesh, RenderingServer, Script, Shader, ShaderMaterial,
    Sprite3D, SubViewport, Texture2D, Viewport, WorldEnvironment,
};
use godot::global::randf;
use godot::prelude::*;
use serde_json::Value;

const BODY_DIR: &str = "res://assets/generated/sprites/characters/body";
// 男女共用底板，女生沒有自己那份時用男生的
const SHARED_GENDER: &str = "male";
const SPRITE_SHADER: &str = "res://assets/shaders/actor_sprite.gdshader";
const SHADOW_SHADER: &str = "res://assets/shaders/actor_shadow.gdshader";
// 離方向格子邊界不到這麼多格就不換方向，斜走才不會來回閃
const DIRECTION_HYSTERESIS: f32 = 0.08;
const TURN_SPEED: f32 = 0.05;
const IDLE_SPEED: f32 = 0.15;
const WALK_REFERENCE_SPEED: f32 = 1.7;
const MIN_PLAYBACK: f32 = 0.55;
const MAX_PLAYBACK: f32 = 2.6;
// 起步那一幀直接跳到目標的 0.7 倍，再 0.05 秒追上；停下 0.07 秒收，太長腳會在地上磨
const SPEED_START_JUMP: f32 = 0.7;
const SPEED_RISE_S: f32 = 0.05;
const SPEED_FALL_S: f32 = 0.07;
// 呼吸和走路的起伏佔身高的比例，約一兩個像素，照舊專案 sprite_actor.gd
const BOB_IDLE: f32 = 0.012;
const BOB_WALK: f32 = 0.022;
const BOB_IDLE_PERIOD_S: f32 = 2.6;
// 受光只補一層時段的味道，圖上已經畫了明暗，多了會髒；舊專案 map_environment.gd 的 sprite_lit_amount
const LIT_AMOUNT: f32 = 0.45;
// 環境光取天空時沒有顏色可讀，用舊專案白天的代表色
const SKY_AMBIENT: Color = Color::from_rgb(0.6, 0.66, 0.78);
// 換地圖時環境會重建，每隔這麼久確認一次色調映射有沒有變
const GRADING_CHECK_S: f64 = 0.5;
// 反查表每個通道幾階；21 階半秒內量完，內插誤差 2/255 以內
const CUBE: usize = 21;
const ITERATIONS: u32 = 8;
// AgX 要六倍才到純白，但泛光會把那麼亮的像素暈開，夾在 2
const MAX_INPUT: f32 = 2.0;
const PROBE_SHADER: &str = "shader_type spatial;
render_mode unshaded, cull_disabled, shadows_disabled, fog_disabled;
uniform sampler2D cube : filter_nearest, repeat_disable;
void fragment() { ALBEDO = texture(cube, UV).rgb; }";

type Rgb = [f32; 3];

/// 所有角色共用的圖集、材質、反查表、受光，做一次掛著，生角色那一幀不新建
#[derive(Default)]
struct Cache {
    sheets: HashMap<String, Sheet>,
    materials: HashMap<String, Gd<ShaderMaterial>>,
    // 環境的 key 對到反查表，None 是還在量
    grading: HashMap<String, Option<Gd<ImageTexture>>>,
    light: Vec<(&'static str, Variant)>,
    // 別人的名字、自己的名字
    names: Vec<Gd<LabelSettings>>,
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

#[derive(Clone, Copy, PartialEq)]
struct Action {
    start: i32,
    frames: i32,
    fps: f32,
}

#[derive(Clone)]
struct Sheet {
    dir: String,
    texture: Gd<Texture2D>,
    size: Vector2,
    anchor: Vector2,
    pixels_per_meter: f32,
    columns: i32,
    directions: i32,
    idle: Action,
    walk: Action,
    // 腳底到頭頂，公尺
    height: f32,
}

impl Sheet {
    fn load(dir: &str) -> Option<Sheet> {
        let path = format!("{dir}/meta.json");
        if !FileAccess::file_exists(&path) {
            return None;
        }
        let meta: Value = serde_json::from_str(&FileAccess::get_file_as_string(&path).to_string()).ok()?;
        let number = |value: &Value| value.as_f64().map(|n| n as f32);
        let pair = |key: &str| Some(Vector2::new(number(&meta[key][0])?, number(&meta[key][1])?));
        let action = |name: &str| {
            let info = &meta["actions"][name];
            Some(Action {
                start: number(&info["start"])? as i32,
                frames: number(&info["frames"])? as i32,
                fps: number(&info["fps"])?,
            })
        };
        let mut sheet = Sheet {
            dir: dir.to_owned(),
            texture: try_load(&format!("{dir}/sheet.png")).ok()?,
            size: pair("frame_size")?,
            anchor: pair("anchor")?,
            pixels_per_meter: number(&meta["pixels_per_meter"])?,
            columns: number(&meta["columns"])? as i32,
            directions: meta["directions"].as_array()?.len() as i32,
            idle: action("idle")?,
            walk: action("walk")?,
            height: 0.0,
        };
        // meta 沒寫 top_row，從面向鏡頭站立第一格最高的不透明像素量
        let mut image = sheet.texture.get_image()?;
        image.decompress();
        let top = image.get_region(sheet.frame_rect(sheet.idle, 0, 0).to_rect2i())?.get_used_rect().position.y;
        sheet.height = (sheet.anchor.y - top as f32) / sheet.pixels_per_meter;
        Some(sheet)
    }

    fn cached(dir: &str) -> Option<Sheet> {
        cache(|c| c.sheets.get(dir).cloned()).or_else(|| {
            let sheet = Sheet::load(dir)?;
            cache(|c| c.sheets.insert(dir.to_owned(), sheet.clone()));
            Some(sheet)
        })
    }

    // packed 排版：格號 = start + 方向 × 格數 + 格，一個方向可以跨列
    fn frame_rect(&self, action: Action, direction: i32, frame: i32) -> Rect2 {
        let cell = action.start + direction * action.frames + frame;
        let position = Vector2::new((cell % self.columns) as f32, (cell / self.columns) as f32) * self.size;
        Rect2::new(position, self.size)
    }

    // 五方向圖集的右半邊拿左半邊水平翻
    fn sheet_direction(&self, index: i32) -> (i32, bool) {
        if self.directions >= 8 || index <= 4 { (index, false) } else { (8 - index, true) }
    }

    // Sprite3D 的 offset 往上為正，讓錨點落在節點原點；翻過去錨點也鏡射
    fn anchor_offset(&self, flipped: bool) -> Vector2 {
        let x = if flipped { self.size.x - self.anchor.x } else { self.anchor.x };
        Vector2::new(self.size.x / 2.0 - x, self.anchor.y - self.size.y / 2.0)
    }
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

fn luma(color: Color) -> f32 {
    color.r * 0.299 + color.g * 0.587 + color.b * 0.114
}

#[derive(GodotClass)]
#[class(init, base=Node3D)]
pub struct Actor {
    base: Base<Node3D>,
    sheet: Option<Sheet>,
    body: Option<Gd<Sprite3D>>,
    caster: Option<Gd<Sprite3D>>,
    facing: f32,
    direction: i32,
    wanted_speed: f32,
    display_speed: f32,
    action: Option<Action>,
    frame: i32,
    frame_time: f32,
    shown: Option<(i32, i32, i32)>,
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
        let mut body = Sprite3D::new_alloc();
        body.set_texture(&sheet.texture);
        body.set_region_enabled(true);
        body.set_pixel_size(1.0 / sheet.pixels_per_meter);
        body.set_cast_shadows_setting(ShadowCastingSetting::OFF);
        let mut caster = body.duplicate_node();
        body.set_material_override(&material(&sheet, "", None));
        caster.set_cast_shadows_setting(ShadowCastingSetting::SHADOWS_ONLY);
        caster.set_material_override(&material(&sheet, "shadow", None));
        // 替身側身對著太陽，會超出照正面算的包圍盒
        caster.set_extra_cull_margin(2.0);
        body.add_child(&caster);
        self.base_mut().add_child(&body);
        (self.body, self.caster, self.sheet) = (Some(body), Some(caster), Some(sheet));
        // 每個人的起伏錯開，一群人才不會整齊地一起上下
        self.bob_phase = randf() as f32 * TAU;
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
        let scale = 1.0 / luma(ambient + sun_light * 0.5).max(0.02);
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

    fn place_name(&mut self) {
        let Some(camera) = self.base().get_viewport().and_then(|v| v.get_camera_3d()) else { return };
        let at = self.base().get_global_position();
        let Some((label, down)) = self.name.as_mut() else { return };
        label.set_visible(!camera.is_position_behind(at));
        let size = label.get_minimum_size();
        label.set_position((camera.unproject_position(at) + Vector2::new(-size.x / 2.0, *down - size.y / 2.0)).round());
    }

    fn sync_grading(&mut self) {
        let Some(viewport) = self.base().get_viewport() else { return };
        let key = environment_of(&viewport).map_or(String::new(), |environment| key_of(&environment));
        if self.grading_key.as_ref() == Some(&key) {
            return;
        }
        let lut = match cache(|c| c.grading.get(&key).cloned()) {
            _ if key.is_empty() => None,
            Some(Some(lut)) => Some(lut),
            Some(None) => return,
            None => return GradingProbe::start(&viewport, &key),
        };
        let (Some(body), Some(sheet)) = (self.body.as_mut(), self.sheet.as_ref()) else { return };
        body.set_material_override(&material(sheet, &key, lut));
        self.grading_key = Some(key);
    }

    fn show_frame(&mut self, action: Action) {
        let (Some(sheet), Some(body), Some(caster)) = (&self.sheet, self.body.as_mut(), self.caster.as_mut()) else {
            return;
        };
        let (direction, flipped) = sheet.sheet_direction(self.direction);
        let rect = sheet.frame_rect(action, direction, self.frame);
        for sprite in [&mut *body, caster] {
            sprite.set_region_rect(rect);
            sprite.set_flip_h(flipped);
            sprite.set_offset(sheet.anchor_offset(flipped));
        }
        // 受光照這一格的左右算圓柱法線；flip_h 只換 UV，法線的左右要自己轉回來
        let size = sheet.texture.get_size();
        let uv = Vector4::new(
            rect.position.x / size.x,
            rect.position.y / size.y,
            rect.size.x / size.x,
            rect.size.y / size.y,
        );
        body.set_instance_shader_parameter("frame_uv", &uv.to_variant());
        body.set_instance_shader_parameter("flip_sign", &(if flipped { -1.0 } else { 1.0 }).to_variant());
    }

    // 站著是對稱的慢呼吸；走路跟著步頻，一步兩個起伏、腳著地時最低
    fn bob(&mut self, delta: f32, walking: bool) {
        let (Some(sheet), Some(body)) = (&self.sheet, self.body.as_mut()) else { return };
        let lift = if walking {
            self.bob_phase += delta * self.display_speed / WALK_REFERENCE_SPEED * TAU * 2.0;
            self.bob_phase.sin().abs() * BOB_WALK
        } else {
            self.bob_phase += delta * TAU / BOB_IDLE_PERIOD_S;
            (self.bob_phase.sin() * 0.5 + 0.5) * BOB_IDLE
        };
        body.set_position(Vector3::new(0.0, lift * sheet.height, 0.0));
    }
}

#[godot_api]
impl INode3D for Actor {
    fn process(&mut self, delta: f64) {
        let Some(sheet) = &self.sheet else { return };
        let (idle, walk) = (sheet.idle, sheet.walk);
        self.grading_wait -= delta;
        if self.grading_wait <= 0.0 {
            self.grading_wait = GRADING_CHECK_S;
            self.sync_grading();
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
        let action = if walking { walk } else { idle };
        if self.action != Some(action) {
            (self.action, self.frame, self.frame_time) = (Some(action), 0, 0.0);
        }
        let playback =
            if walking { (self.display_speed / WALK_REFERENCE_SPEED).clamp(MIN_PLAYBACK, MAX_PLAYBACK) } else { 1.0 };
        self.frame_time += delta * playback * action.fps;
        self.frame = (self.frame + self.frame_time as i32) % action.frames;
        self.frame_time = self.frame_time.fract();
        let shown = Some((action.start, self.direction, self.frame));
        if self.shown != shown {
            self.shown = shown;
            self.show_frame(action);
        }
        self.bob(delta, walking);
        self.place_name();
    }
}

// 一張圖集一種環境一份材質；key 是 shadow 時給影子替身
fn material(sheet: &Sheet, key: &str, lut: Option<Gd<ImageTexture>>) -> Gd<ShaderMaterial> {
    cache(|c| {
        let entry = c.materials.entry(format!("{}|{key}", sheet.dir)).or_insert_with(|| {
            let mut material = ShaderMaterial::new_gd();
            material.set_shader(&load::<Shader>(if key == "shadow" { SHADOW_SHADER } else { SPRITE_SHADER }));
            material.set_shader_parameter("sheet", &sheet.texture.to_variant());
            if let Some(lut) = lut {
                material.set_shader_parameter("grading_enabled", &1.to_variant());
                material.set_shader_parameter("grading_lut", &lut.to_variant());
                material.set_shader_parameter("grading_cube", &(CUBE as f32).to_variant());
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

fn environment_of(viewport: &Gd<Viewport>) -> Option<Gd<Environment>> {
    let camera_environment = viewport.get_camera_3d().and_then(|camera| camera.get_environment());
    camera_environment.or_else(|| viewport.find_world_3d()?.get_environment())
}

fn compatibility() -> bool {
    RenderingServer::singleton().get_current_rendering_method() == "gl_compatibility"
}

// 會影響顏色的設定拼起來，一樣的環境共用一張反查表
fn key_of(environment: &Gd<Environment>) -> String {
    let properties = "tonemap_mode tonemap_exposure tonemap_white tonemap_agx_white tonemap_agx_contrast \
                      adjustment_enabled adjustment_brightness adjustment_contrast adjustment_saturation";
    let mut parts: Vec<String> = properties.split_whitespace().map(|p| environment.get(p).to_string()).collect();
    // 相容渲染器開泛光才畫進浮點緩衝，量出來不一樣
    if compatibility() && environment.is_glow_enabled() {
        parts.push("hdr".into());
    }
    parts.join("|")
}

fn srgb_to_linear(c: f32) -> f32 {
    if c < 0.04045 { c / 12.92 } else { ((c + 0.055) / 1.055).powf(2.4) }
}

// 反查表和探針都排成 cube² × cube 的圖：x 是 r + cube × b、y 是 g，第 i 格就是第 i 個像素
fn cube_color(i: usize) -> Rgb {
    let (x, g) = (i % (CUBE * CUBE), i / (CUBE * CUBE));
    [x % CUBE, g, x / CUBE].map(|c| c as f32 / (CUBE - 1) as f32)
}

fn cube_image(inputs: &[Rgb]) -> Gd<Image> {
    let bytes: PackedByteArray =
        inputs.iter().flat_map(|c| [c[0], c[1], c[2], 1.0]).flat_map(f32::to_le_bytes).collect();
    Image::create_from_data((CUBE * CUBE) as i32, CUBE as i32, false, Format::RGBAF, &bytes).unwrap()
}

// sRGB 空間照 Godot 的反順序扣掉飽和度、對比、亮度
fn undo_adjustment(target: Rgb, environment: &Gd<Environment>) -> Rgb {
    if !environment.is_adjustment_enabled() {
        return target;
    }
    let [brightness, contrast, saturation] =
        ["brightness", "contrast", "saturation"].map(|p| environment.get(&format!("adjustment_{p}")).to::<f32>());
    let mean = target.iter().sum::<f32>() / 3.0;
    target.map(|c| ((((mean + (c - mean) / saturation) - 0.5) / contrast + 0.5) / brightness).clamp(0.0, 1.0))
}

/// 把候選顏色真的丟進同一個環境算一張圖讀回來，和目標比、往回推，收斂後存成反查表，見 docs/精靈圖顯示校正.md
#[derive(GodotClass)]
#[class(no_init, base=SubViewport)]
struct GradingProbe {
    base: Base<SubViewport>,
    key: String,
    linear: bool,
    targets: Vec<Rgb>,
    inputs: Vec<Rgb>,
    previous: Option<(Vec<Rgb>, Vec<Rgb>)>,
    texture: Gd<ImageTexture>,
    iteration: u32,
    wait: u32,
}

impl GradingProbe {
    fn start(viewport: &Gd<Viewport>, key: &str) {
        cache(|c| c.grading.insert(key.to_owned(), None));
        let Some(source) = environment_of(viewport) else { return };
        let mut environment = source.duplicate_resource();
        // 只留色調映射；色彩調整 Mobile 的 SubViewport 不做，一律關掉改由目標先扣
        // 相容渲染器開泛光才畫進浮點緩衝，只借緩衝、強度歸零
        environment.set_glow_enabled(compatibility() && source.is_glow_enabled());
        environment.set_glow_intensity(0.0);
        environment.set_glow_bloom(0.0);
        environment.set_glow_hdr_bleed_threshold(4.0);
        let disabled = "adjustment_enabled fog_enabled volumetric_fog_enabled ssao_enabled ssil_enabled sdfgi_enabled";
        disabled.split(' ').for_each(|property| environment.set(property, &false.to_variant()));
        environment.set_background(BgMode::COLOR);
        environment.set_bg_color(Color::BLACK);
        let targets: Vec<Rgb> = (0..CUBE * CUBE * CUBE).map(|i| undo_adjustment(cube_color(i), &source)).collect();
        // 相容渲染器整條管線在 sRGB，候選直接從目標開始
        let linear = !compatibility();
        let inputs: Vec<Rgb> =
            if linear { targets.iter().map(|t| t.map(srgb_to_linear)).collect() } else { targets.clone() };
        let texture = ImageTexture::create_from_image(&cube_image(&inputs)).unwrap();
        let mut probe = Gd::from_init_fn(|base| GradingProbe {
            base,
            key: key.to_owned(),
            linear,
            targets,
            inputs,
            previous: None,
            texture: texture.clone(),
            iteration: 0,
            wait: 0,
        });
        probe.set_size(Vector2i::new((CUBE * CUBE) as i32, CUBE as i32));
        probe.set_use_own_world_3d(true);
        probe.set_update_mode(UpdateMode::ALWAYS);
        let mut camera = Camera3D::new_alloc();
        camera.set_projection(ProjectionType::ORTHOGONAL);
        camera.set_size(2.0);
        camera.set_position(Vector3::new(0.0, 0.0, 1.0));
        camera.set_environment(&environment);
        let mut mesh = QuadMesh::new_gd();
        mesh.set_size(Vector2::new(2.0 * CUBE as f32, 2.0));
        let mut shader = Shader::new_gd();
        shader.set_code(PROBE_SHADER);
        let mut material = ShaderMaterial::new_gd();
        material.set_shader(&shader);
        material.set_shader_parameter("cube", &texture.to_variant());
        let mut quad = MeshInstance3D::new_alloc();
        quad.set_mesh(&mesh);
        quad.set_material_override(&material);
        probe.add_child(&camera);
        probe.add_child(&quad);
        viewport.get_tree().get_root().add_child(&probe);
    }

    // 已經量到純白又要純白的通道不推，不然會一直長到上限；第二次起拿斜率當步長，AgX 肩部才收斂得快
    fn refine(&mut self, measured: Vec<Rgb>) {
        let to_space = |c: f32| if self.linear { srgb_to_linear(c) } else { c };
        let mut next = self.inputs.clone();
        for (i, target) in self.targets.iter().enumerate() {
            for axis in 0..3 {
                if measured[i][axis] >= 0.998 && target[axis] >= 0.998 {
                    continue;
                }
                let current = self.inputs[i][axis];
                let got = to_space(measured[i][axis]);
                let mut gain = 1.0;
                if let Some((previous_inputs, previous_measured)) = &self.previous {
                    let input_change = current - previous_inputs[i][axis];
                    let output_change = got - to_space(previous_measured[i][axis]);
                    // 讀回來只有 8 位元，變化太小的斜率不可信
                    let readable = (measured[i][axis] - previous_measured[i][axis]).abs() > 2.5 / 255.0;
                    if input_change.abs() > 0.001 && readable && input_change * output_change > 0.0 {
                        gain = (input_change / output_change).clamp(0.4, 8.0);
                    }
                }
                next[i][axis] = (current + (to_space(target[axis]) - got) * gain).clamp(0.0, MAX_INPUT);
            }
        }
        self.previous = Some((std::mem::replace(&mut self.inputs, next), measured));
    }
}

#[godot_api]
impl ISubViewport for GradingProbe {
    // 每量一次等三幀讓探針畫完
    fn process(&mut self, _delta: f64) {
        self.wait += 1;
        if self.wait < 3 {
            return;
        }
        self.wait = 0;
        // 沒有畫面的客戶端讀不回像素，不校正
        let Some(mut image) = self.base().get_texture().and_then(|t| t.get_image()) else {
            return self.base_mut().queue_free();
        };
        image.convert(Format::RGBA8);
        let measured =
            image.get_data().as_slice().chunks(4).map(|p| [p[0], p[1], p[2]].map(|c| c as f32 / 255.0)).collect();
        self.refine(measured);
        self.iteration += 1;
        self.texture.update(&cube_image(&self.inputs));
        if self.iteration == ITERATIONS {
            let texture = self.texture.clone();
            cache(|c| c.grading.insert(self.key.clone(), Some(texture)));
            self.base_mut().queue_free();
        }
    }
}

/// 預覽：萌芽草原中央石板，男生一排走路、女生一排站著，各八個方向
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
        let yaw = self.base().get_viewport().and_then(|v| v.get_camera_3d()).map_or(0.0, |c| c.get_global_rotation().y);
        // 玩家移動速度 3.5；0.1 過了轉身門檻、不到走路門檻，站著面向那一方
        for (row, gender, speed) in [(-1.6, "male", 3.5), (1.6, "female", 0.1)] {
            for index in 0..8 {
                let facing = yaw - index as f32 * FRAC_PI_4;
                let mut actor = Actor::new_alloc();
                actor.set_position(Vector3::new((index as f32 - 3.5) * 2.2, 0.0, row));
                actor.bind_mut().setup(gender.into(), VarDictionary::new());
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
