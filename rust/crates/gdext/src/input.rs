//! 滑鼠指的地面格子：射線打 y = 0 的地面、吸 0.6 公尺格子、只畫那一格、切換游標形狀，數字照 docs/M1舊行為.md 第 7 節。

use godot::classes::geometry_instance_3d::ShadowCastingSetting;
use godot::classes::input::CursorShape;
use godot::classes::mesh::PrimitiveType;
use godot::classes::{
    ArrayMesh, INode3D, Input, InputEvent, InputEventMouseButton, InputEventMouseMotion, MeshInstance3D, Shader,
    ShaderMaterial, SurfaceTool,
};
use godot::global::MouseButton;
use godot::prelude::*;

use crate::camera::RofCamera;
use crate::shot::arg;

const CELL: f32 = 0.6;
// 比地面貼花高、比技能地圈低，斜看不會和地面打架
const GROUND_Y: f32 = 0.06;
// 框線半寬用固定公尺數，再細 52 公尺外就看不見
const RING_LIGHT: f32 = 0.017;
const RING_DARK: f32 = 0.034;
const WALK_LIGHT: Color = Color::from_rgba(1.0, 0.94, 0.78, 0.55);
const BLOCK_LIGHT: Color = Color::from_rgba(0.93, 0.45, 0.4, 0.75);
// 深邊只讓亮線在淺色石板上分得出來，本身不該被看見
const EDGE: Color = Color::from_rgba(0.07, 0.05, 0.04, 0.42);
const WALK_FILL: f32 = 0.07;
const BLOCK_FILL: f32 = 0.16;
const FLASH_SECONDS: f32 = 0.45;
// 往鏡頭推半公尺，草毯的葉子蓋不住，樹幹和牆照樣擋得住
const RING_SHADER: &str = "shader_type spatial;
render_mode unshaded, cull_disabled, shadows_disabled;
void vertex() { POSITION = PROJECTION_MATRIX * (MODELVIEW_MATRIX * vec4(VERTEX, 1.0) + vec4(0.0, 0.0, 0.5, 0.0)); }
void fragment() { ALBEDO = pow(COLOR.rgb, vec3(2.2)); ALPHA = COLOR.a; }";

fn center(cell: Vector2i) -> Vector2 {
    (cell.to_vector2() + Vector2::splat(0.5)) * CELL
}

type Quad = ([Vector2; 4], [Color; 4]);

/// 一格的框：由外到內深、亮、亮、深四圈；不可走再加一個叉；fill 是框裡的淡底色
fn cell_mesh(cell: Vector2i, light: Color, fill: f32, cross: bool) -> Gd<ArrayMesh> {
    let (middle, half) = (center(cell), CELL / 2.0);
    let corners = [Vector2::new(-1.0, -1.0), Vector2::new(1.0, -1.0), Vector2::new(1.0, 1.0), Vector2::new(-1.0, 1.0)];
    let bands =
        [(half + RING_DARK, EDGE), (half + RING_LIGHT, light), (half - RING_LIGHT, light), (half - RING_DARK, EDGE)];
    let mut quads: Vec<Quad> = vec![(corners.map(|c| middle + c * half), [light.with_alpha(fill); 4])];
    for pair in bands.windows(2) {
        let ((outer, outer_color), (inner, inner_color)) = (pair[0], pair[1]);
        for side in 0..4 {
            let (a, b) = (corners[side], corners[(side + 1) % 4]);
            let points = [middle + a * outer, middle + b * outer, middle + b * inner, middle + a * inner];
            quads.push((points, [outer_color, outer_color, inner_color, inner_color]));
        }
    }
    if cross {
        let reach = half - RING_DARK * 2.0;
        for step in [Vector2::new(1.0, 1.0), Vector2::new(1.0, -1.0)] {
            let side = Vector2::new(-step.y, step.x).normalized();
            for pair in bands.windows(2) {
                let ((near, near_color), (far, far_color)) = (pair[0], pair[1]);
                let (near, far) = (side * (near - half), side * (far - half));
                let (from, to) = (middle - step * reach, middle + step * reach);
                quads.push((
                    [from + near, to + near, to + far, from + far],
                    [near_color, near_color, far_color, far_color],
                ));
            }
        }
    }
    let mut surface = SurfaceTool::new_gd();
    surface.begin(PrimitiveType::TRIANGLES);
    for (points, colors) in quads {
        for i in [0, 1, 2, 0, 2, 3] {
            surface.set_color(colors[i]);
            surface.set_normal(Vector3::UP);
            surface.add_vertex(Vector3::new(points[i].x, GROUND_Y, points[i].y));
        }
    }
    surface.commit().unwrap()
}

fn ground_mesh() -> Gd<MeshInstance3D> {
    let mut shader = Shader::new_gd();
    shader.set_code(RING_SHADER);
    let mut material = ShaderMaterial::new_gd();
    material.set_shader(&shader);
    let mut mesh = MeshInstance3D::new_alloc();
    mesh.set_cast_shadows_setting(ShadowCastingSetting::OFF);
    mesh.set_material_override(&material);
    mesh.set_visible(false);
    mesh
}

/// 放在世界原點；世界收到 hovered 之後用 set_walkable 告訴它那格能不能走
#[derive(GodotClass)]
#[class(init, base=Node3D)]
pub struct GroundPicker {
    base: Base<Node3D>,
    #[init(val = ground_mesh())]
    ring: Gd<MeshInstance3D>,
    #[init(val = ground_mesh())]
    flash: Gd<MeshInstance3D>,
    flash_left: f32,
    mouse: Option<Vector2>,
    cell: Option<Vector2i>,
    #[init(val = true)]
    walkable: bool,
    dirty: bool,
    held: bool,
    sent: Option<Vector2i>,
}

#[godot_api]
impl GroundPicker {
    #[signal]
    fn hovered(x: f32, z: f32);

    #[signal]
    fn clicked(x: f32, z: f32);

    #[func]
    fn set_walkable(&mut self, walkable: bool) {
        self.dirty |= self.walkable != walkable;
        self.walkable = walkable;
    }

    // 滑到介面上就交還給介面，Godot 自己換回箭頭
    fn cell_under_mouse(&self) -> Option<Vector2i> {
        let viewport = self.base().get_viewport()?;
        if viewport.gui_get_hovered_control().is_some() {
            return None;
        }
        let (camera, mouse) = (viewport.get_camera_3d()?, self.mouse?);
        let (origin, direction) = (camera.project_ray_origin(mouse), camera.project_ray_normal(mouse));
        if direction.y > -0.001 {
            return None;
        }
        let point = origin + direction * (-origin.y / direction.y);
        Some(Vector2::new(point.x, point.z) / CELL).map(|cell| cell.floor().to_vector2i())
    }

    fn emit(&mut self, signal: &str, cell: Vector2i) {
        let spot = center(cell);
        self.base_mut().emit_signal(signal, &[spot.x.to_variant(), spot.y.to_variant()]);
    }

    fn redraw(&mut self) {
        let shape = match self.cell {
            Some(cell) if self.walkable => {
                self.ring.set_mesh(&cell_mesh(cell, WALK_LIGHT, WALK_FILL, false));
                CursorShape::MOVE
            }
            Some(cell) => {
                self.ring.set_mesh(&cell_mesh(cell, BLOCK_LIGHT, BLOCK_FILL, true));
                CursorShape::FORBIDDEN
            }
            None => CursorShape::ARROW,
        };
        self.ring.set_visible(self.cell.is_some());
        // 形狀 walk 和 blocked 的圖由介面的 game_cursor.gd 掛上去
        Input::singleton().set_default_cursor_shape_ex().shape(shape).done();
    }
}

#[godot_api]
impl INode3D for GroundPicker {
    fn ready(&mut self) {
        let (ring, flash) = (self.ring.clone(), self.flash.clone());
        self.base_mut().add_child(&ring);
        self.base_mut().add_child(&flash);
    }

    fn input(&mut self, event: Gd<InputEvent>) {
        if let Ok(motion) = event.try_cast::<InputEventMouseMotion>() {
            self.mouse = Some(motion.get_position());
        }
    }

    fn unhandled_input(&mut self, event: Gd<InputEvent>) {
        if let Ok(button) = event.try_cast::<InputEventMouseButton>()
            && button.get_button_index() == MouseButton::LEFT
        {
            self.mouse = Some(button.get_position());
            self.held = button.is_pressed();
            self.sent = None;
        }
    }

    fn process(&mut self, delta: f64) {
        let cell = self.cell_under_mouse();
        if cell != self.cell {
            (self.cell, self.dirty) = (cell, true);
            if let Some(cell) = cell {
                self.emit("hovered", cell);
            }
        }
        if self.dirty {
            self.dirty = false;
            self.redraw();
        }
        // 按住左鍵一路跟著游標走，換到別的格子才再送一次
        self.held &= Input::singleton().is_mouse_button_pressed(MouseButton::LEFT);
        if let Some(cell) = cell.filter(|c| self.held && self.walkable && self.sent != Some(*c)) {
            self.sent = Some(cell);
            self.emit("clicked", cell);
            self.flash.set_mesh(&cell_mesh(cell, WALK_LIGHT, 0.0, false));
            self.flash_left = FLASH_SECONDS;
        }
        self.flash_left = (self.flash_left - delta as f32).max(0.0);
        self.flash.set_visible(self.flash_left > 0.0);
        self.flash.set_transparency(1.0 - self.flash_left / FLASH_SECONDS);
    }
}

/// 預覽：鏡頭對準 --cursor=x,z，游標停在畫面正中那一格，加 --blocked 畫成不可走
#[derive(GodotClass)]
#[class(init, base=Node3D)]
struct PickerPreview {
    base: Base<Node3D>,
}

#[godot_api]
impl INode3D for PickerPreview {
    fn ready(&mut self) {
        let spot = arg("--cursor=").unwrap_or_default();
        let spot: Vec<f32> = spot.split(',').filter_map(|n| n.parse().ok()).collect();
        let mut camera = self.base().get_node_as::<RofCamera>("Camera");
        camera.set_position(Vector3::new(
            spot.first().copied().unwrap_or(0.0),
            0.0,
            spot.get(1).copied().unwrap_or(0.0),
        ));
        let middle = self.base().get_viewport().unwrap().get_visible_rect().size / 2.0;
        let mut picker = self.base().get_node_as::<GroundPicker>("Picker");
        let mut picker = picker.bind_mut();
        picker.mouse = Some(middle);
        picker.walkable = arg("--blocked").is_none();
    }
}
