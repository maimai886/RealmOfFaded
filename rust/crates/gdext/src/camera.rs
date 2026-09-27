//! 斜俯角跟隨鏡頭：跟著目標、右鍵拖曳只轉水平、滾輪和觸控板縮放，手感數字在 data/camera.json。

use godot::builtin::math::FloatExt;
use godot::classes::{
    Camera3D, FileAccess, INode3D, InputEvent, InputEventMagnifyGesture, InputEventMouseButton, InputEventMouseMotion,
    InputEventPanGesture,
};
use godot::global::{MouseButton, MouseButtonMask};
use godot::prelude::*;
use serde_json::Value;

// 俯角和視角是整套美術的基準，改了要重算 docs/美術技術框架.md，所以不放資料檔
const PITCH_DEGREES: f32 = -45.0;
const FOV_DEGREES: f32 = 15.0;
const SETTINGS: &str = "res://data/camera.json";

struct Settings {
    min_distance: f32,
    max_distance: f32,
    zoom_step: f32,
    pan_zoom_scale: f32,
    magnify_zoom_meters: f32,
    rotate_per_pixel: f32,
    follow_speed: f32,
    rotate_sharpness: f32,
    zoom_sharpness: f32,
}

impl Settings {
    fn load() -> Settings {
        let json: Value =
            serde_json::from_str(&FileAccess::get_file_as_string(SETTINGS).to_string()).unwrap_or_default();
        let number = |key: &str| {
            json[key].as_f64().unwrap_or_else(|| {
                godot_error!("{SETTINGS} 缺 {key}");
                1.0
            }) as f32
        };
        Settings {
            min_distance: number("min_distance"),
            max_distance: number("max_distance"),
            zoom_step: number("zoom_step"),
            pan_zoom_scale: number("pan_zoom_scale"),
            magnify_zoom_meters: number("magnify_zoom_meters"),
            rotate_per_pixel: number("rotate_per_pixel"),
            follow_speed: number("follow_speed"),
            rotate_sharpness: number("rotate_sharpness"),
            zoom_sharpness: number("zoom_sharpness"),
        }
    }
}

// 和畫面更新率無關的平滑，60Hz 和 120Hz 一樣快
fn blend(sharpness: f32, delta: f32) -> f32 {
    1.0 - (-sharpness * delta).exp()
}

#[derive(GodotClass)]
#[class(base=Node3D)]
pub struct RofCamera {
    base: Base<Node3D>,
    settings: Settings,
    camera: Option<Gd<Camera3D>>,
    target: Option<Vector3>,
    wanted_yaw: f32,
    distance: f32,
    wanted_distance: f32,
}

#[godot_api]
impl RofCamera {
    /// 目標的世界座標，每幀給；第一次直接跳過去
    #[func]
    fn follow(&mut self, target: Vector3) {
        if self.target.is_none() {
            self.base_mut().set_position(target);
        }
        self.target = Some(target);
    }

    #[func]
    fn yaw(&self) -> f32 {
        self.base().get_rotation().y
    }

    fn zoom_by(&mut self, meters: f32) {
        let Settings { min_distance, max_distance, .. } = self.settings;
        self.wanted_distance = (self.wanted_distance + meters).clamp(min_distance, max_distance);
    }

    fn place_camera(&mut self) {
        let pitch = PITCH_DEGREES.to_radians();
        let offset = Vector3::new(0.0, -pitch.sin(), pitch.cos()) * self.distance;
        if let Some(camera) = self.camera.as_mut() {
            camera.set_position(offset);
        }
    }
}

#[godot_api]
impl INode3D for RofCamera {
    // 預設開在最遠，使用者要一進遊戲就看得寬
    fn init(base: Base<Node3D>) -> Self {
        let settings = Settings::load();
        let distance = settings.max_distance;
        Self { base, settings, camera: None, target: None, wanted_yaw: 0.0, distance, wanted_distance: distance }
    }

    fn ready(&mut self) {
        let mut camera = Camera3D::new_alloc();
        camera.set_fov(FOV_DEGREES);
        camera.set_near(1.0);
        camera.set_far(300.0);
        camera.set_rotation(Vector3::new(PITCH_DEGREES.to_radians(), 0.0, 0.0));
        self.base_mut().add_child(&camera);
        camera.make_current();
        self.camera = Some(camera);
        self.wanted_yaw = self.yaw();
        self.place_camera();
    }

    // 位置照 Godot Camera2D 的平滑：lerp(目前, 目標, clamp(速度 × dt))
    fn process(&mut self, delta: f64) {
        let delta = delta as f32;
        let follow = (self.settings.follow_speed * delta).clamp(0.0, 1.0);
        let yaw = self.yaw().lerp_angle(self.wanted_yaw, blend(self.settings.rotate_sharpness, delta));
        self.distance += (self.wanted_distance - self.distance) * blend(self.settings.zoom_sharpness, delta);
        let position = self.target.map(|target| self.base().get_position().lerp(target, follow));
        let mut base = self.base_mut();
        base.set_rotation(Vector3::new(0.0, yaw, 0.0));
        if let Some(position) = position {
            base.set_position(position);
        }
        drop(base);
        self.place_camera();
    }

    // 介面先收掉滑鼠事件，滑鼠停在視窗上轉滾輪不會動到鏡頭
    fn unhandled_input(&mut self, event: Gd<InputEvent>) {
        let settings = &self.settings;
        let zoom = if let Ok(motion) = event.clone().try_cast::<InputEventMouseMotion>() {
            if motion.get_button_mask().is_set(MouseButtonMask::RIGHT) {
                self.wanted_yaw -= motion.get_relative().x * settings.rotate_per_pixel;
            }
            return;
        } else if let Ok(pan) = event.clone().try_cast::<InputEventPanGesture>() {
            pan.get_delta().y * settings.pan_zoom_scale
        } else if let Ok(magnify) = event.clone().try_cast::<InputEventMagnifyGesture>() {
            (1.0 - magnify.get_factor()) * settings.magnify_zoom_meters
        } else if let Ok(button) = event.try_cast::<InputEventMouseButton>()
            && button.is_pressed()
        {
            match button.get_button_index() {
                MouseButton::WHEEL_UP => -settings.zoom_step,
                MouseButton::WHEEL_DOWN => settings.zoom_step,
                _ => return,
            }
        } else {
            return;
        };
        self.zoom_by(zoom);
    }
}
