//! 顯示校正：量出場景的輸出流程把顏色改成什麼樣，解一張反查表給精靈圖著色器抵銷，見 docs/精靈圖顯示校正.md。

use godot::classes::camera_3d::ProjectionType;
use godot::classes::environment::BgMode;
use godot::classes::image::Format;
use godot::classes::sub_viewport::UpdateMode;
use godot::classes::{
    Camera3D, Environment, ISubViewport, Image, ImageTexture, MeshInstance3D, QuadMesh, RenderingServer, Shader,
    ShaderMaterial, SubViewport, Viewport,
};
use godot::prelude::*;

use super::cache;

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

pub(super) fn environment_of(viewport: &Gd<Viewport>) -> Option<Gd<Environment>> {
    let camera_environment = viewport.get_camera_3d().and_then(|camera| camera.get_environment());
    camera_environment.or_else(|| viewport.find_world_3d()?.get_environment())
}

fn compatibility() -> bool {
    RenderingServer::singleton().get_current_rendering_method() == "gl_compatibility"
}

// 會影響顏色的設定拼起來，一樣的環境共用一張反查表
pub(super) fn key_of(environment: &Gd<Environment>) -> String {
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
pub(super) struct GradingProbe {
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
    pub(super) fn start(viewport: &Gd<Viewport>, key: &str) {
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
            // 灰階上推得到的最亮一格；著色器把亮部照比例壓到這裡，只夾單一通道的話皮膚的紅會被吃掉
            let top = (0..CUBE).map(|k| k * (1 + CUBE + CUBE * CUBE)).rfind(|&i| self.inputs[i][0] < MAX_INPUT);
            self.texture.set_meta("ceiling", &top.map_or(1.0, |i| cube_color(i)[0]).to_variant());
            cache(|c| c.grading.insert(self.key.clone(), Some(self.texture.clone())));
            self.base_mut().queue_free();
        }
    }
}
