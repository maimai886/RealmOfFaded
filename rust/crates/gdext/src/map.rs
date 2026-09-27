//! 照地圖資料蓋場景，Rowan：光、環境和各種材質在 `scenes/maps/<scene>.tscn`，
//! 這裡照地圖檔畫小路、種樹林、擺擺設、撒花草。長相照舊專案 meadow.gd 和 map_environment.gd。

use std::collections::HashMap;
use std::f32::consts::{SQRT_2, TAU};
use std::path::Path;

use godot::classes::base_material_3d::{TextureParam, Transparency};
use godot::classes::geometry_instance_3d::ShadowCastingSetting;
use godot::classes::image::Format;
use godot::classes::mesh::PrimitiveType;
use godot::classes::multi_mesh::TransformFormat;
use godot::classes::{
    INode3D, Image, ImageTexture, Material, Mesh, MeshInstance3D, MultiMesh, MultiMeshInstance3D, PackedScene,
    PlaneMesh, ProjectSettings, ShaderMaterial, StandardMaterial3D, SurfaceTool,
};
use godot::prelude::*;
use serde_json::Value;

const NATURE: &str = "res://assets/vendor/quaternius/nature/";
const SEED: u64 = 20260915;
// 地面比地圖範圍每邊多這麼多，鏡頭拉到最遠也看不到邊
const GROUND_MARGIN: f32 = 40.0;
const GROUND_MIN_SIZE: f32 = 150.0;
const PATH_WIDTH: f32 = 1.8;
const WALK_CELL: f32 = 0.5;
// 草和花可以超出可行走範圍這麼多，壓在內緣的樹底下，邊界才不是刀切的直線
const GRASS_FRINGE: f32 = 0.6;
const PORTAL_CLEAR: f32 = 5.0;
const MASK_RANGE: f32 = 8.0;
// 花草的數量是照這麼大的可行走面積定的，範圍變大照比例多撒
const REFERENCE_WALK_AREA: f32 = 1590.0;
const CARPET_DENSITY: f32 = 46.0;
const CARPET_CELL: f32 = 8.0;
// 地面圖層的順序和 terrain.gdshader 一樣
const LAYERS: [&str; 4] = ["grass", "dry", "dirt", "stone"];
const DIRT: f32 = 2.0;

// 地圖檔的擺設換成素材包的模型，倍率把素材包的尺寸換成地圖檔的公尺
const PROPS: [(&str, &str, f32); 3] = [
    ("generated/models/tree_broadleaf", "CommonTree_5", 0.95),
    ("generated/models/shrub", "Bush_Common_Flowers", 0.9),
    ("generated/models/boulder", "Rock_Medium_2", 0.46),
];

// 花草碎石的數量、倍率和輪流用的模型；舊專案的落葉和水窪是平貼的貼花，M1 不鋪
const COVER: [(&str, usize, f32, &str); 7] = [
    ("grass_tuft", 2600, 0.3, "Grass_Common_Short"),
    ("flower_pink", 60, 0.3, "Flower_3_Group Flower_3_Single"),
    ("flower_white", 70, 0.27, "Flower_4_Single Flower_3_Single"),
    ("flower_blue", 50, 0.3, "Flower_3_Single Flower_4_Single"),
    ("fern", 40, 0.4, "Grass_Common_Short"),
    ("pebbles", 36, 0.55, "RockPath_Round_Small_1 RockPath_Round_Small_2 RockPath_Round_Small_3"),
    ("moss", 14, 0.45, "Clover_1 Clover_2"),
];

const FLOWER_PATCHES: [(f32, f32, &str); 5] = [
    (7.0, 5.0, "flower_blue"),
    (-8.0, -3.0, "flower_pink"),
    (9.0, -9.0, "flower_white"),
    (-6.0, 10.0, "flower_blue"),
    (-12.0, 6.0, "flower_white"),
];

#[derive(Clone, Copy)]
struct Place {
    at: Vector2,
    yaw: f32,
    scale: f32,
}

struct Area {
    center: Vector2,
    radius: f32,
    edge: f32,
    layer: i32,
}

struct Map {
    scene: String,
    bounds: Rect2,
    paths: Vec<Vec<Vector2>>,
    areas: Vec<Area>,
    props: Vec<(String, Place)>,
    portals: Vec<(Vector2, f32)>,
    dark_outside: bool,
    columns: usize,
    // 每格離最近的可行走格幾公尺，走得到的是 0
    distance: Vec<f32>,
}

// 只給擺放用，同一個種子每次擺出一樣的地圖
struct Rng(u64);

impl Rng {
    fn unit(&mut self) -> f32 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0 >> 40) as f32 / (1u64 << 24) as f32
    }

    fn range(&mut self, low: f32, high: f32) -> f32 {
        low + (high - low) * self.unit()
    }

    fn place(&mut self, at: Vector2, low: f32, high: f32) -> Place {
        let (yaw, scale) = (self.range(0.0, TAU), self.range(low, high));
        Place { at, yaw, scale }
    }
}

pub fn build(map_id: &str) -> Gd<Node3D> {
    let built = Map::load(map_id).and_then(|map| {
        let path = format!("res://scenes/maps/{}.tscn", map.scene);
        let scene = try_load::<PackedScene>(&path).map_err(|e| e.to_string())?;
        let mut root = scene.instantiate_as::<Node3D>();
        terrain(root.get_node_as("Terrain"), &map);
        let mut rng = Rng(SEED);
        forest(&mut root, &map, &mut rng);
        cover(&mut root, &map, &mut rng);
        carpet(&mut root, &map, &mut rng);
        Ok(root)
    });
    let mut root = built.unwrap_or_else(|error| {
        godot_error!("地圖 {map_id} 蓋不起來：{error}");
        Node3D::new_alloc()
    });
    root.set_name(map_id);
    root
}

// 地圖檔的 [x, z]
fn xz(pair: &Value) -> Vector2 {
    let number = |i: usize| pair[i].as_f64().unwrap_or(0.0) as f32;
    Vector2::new(number(0), number(1))
}

impl Map {
    fn load(map_id: &str) -> Result<Map, String> {
        if map_id.contains(|c: char| !c.is_ascii_alphanumeric() && c != '_') {
            return Err("地圖代號不合法".into());
        }
        let path = format!("res://data/maps/{map_id}.json");
        let path = ProjectSettings::singleton().globalize_path(&path).to_string();
        let json = rof_data::read_json(Path::new(&path))?;
        let list = |pointer: &str| {
            let found = json.pointer(pointer).and_then(|v| v.as_array());
            found.cloned().unwrap_or_default()
        };
        let bounds = &json["bounds"];
        let bounds = Rect2::from_position_end(xz(&bounds["min"]), xz(&bounds["max"]));
        let mut map = Map {
            scene: json["scene"].as_str().unwrap_or(map_id).to_owned(),
            bounds,
            paths: vec![],
            areas: vec![],
            props: vec![],
            portals: vec![],
            dark_outside: json["ground"]["outside"] == "dark",
            columns: (bounds.size.x / WALK_CELL).ceil().max(1.0) as usize,
            distance: vec![],
        };
        for line in list("/paths") {
            let points = line.as_array().into_iter().flatten();
            map.paths.push(points.map(xz).collect());
        }
        for area in list("/ground/areas") {
            map.areas.push(Area {
                center: xz(&area["center"]),
                radius: area["radius"].as_f64().unwrap_or(1.0) as f32,
                edge: area["edge"].as_f64().unwrap_or(0.6) as f32,
                layer: LAYERS.iter().position(|l| area["layer"] == *l).unwrap_or(3) as i32,
            });
        }
        for prop in list("/props") {
            let at = xz(&prop["position"]);
            let yaw = (prop["rotation_y"].as_f64().unwrap_or(0.0) as f32).to_radians();
            let scale = prop["scale"].as_f64().unwrap_or(1.0) as f32;
            let model = prop["model"].as_str().unwrap_or_default().to_owned();
            map.props.push((model, Place { at, yaw, scale }));
        }
        for portal in list("/portals") {
            let radius = portal["radius"].as_f64().unwrap_or(1.0) as f32;
            map.portals.push((xz(&portal["position"]), radius));
        }
        // 只有手寫的崖邊圍出邊界，擺設由擺設自己畫出來
        let walls: Vec<Rect2> = list("/blockers")
            .iter()
            .filter(|b| b["type"] == "rect")
            .map(|b| Rect2::from_position_end(xz(&b["min"]), xz(&b["max"])))
            .collect();
        let rows = (bounds.size.y / WALK_CELL).ceil().max(1.0) as usize;
        let blocked = |i| walls.iter().any(|w| w.contains_point(map.cell_center(i)));
        let distance = (0..rows * map.columns).map(|i| match blocked(i) {
            true => f32::INFINITY,
            false => 0.0,
        });
        map.distance = distance.collect();
        map.chamfer();
        Ok(map)
    }

    fn cell_center(&self, index: usize) -> Vector2 {
        let (x, y) = (index % self.columns, index / self.columns);
        self.bounds.position + Vector2::new(x as f32 + 0.5, y as f32 + 0.5) * WALK_CELL
    }

    // 兩趟倒角距離，每格得到離最近可行走格幾公尺
    fn chamfer(&mut self) {
        let (straight, diagonal) = (WALK_CELL, WALK_CELL * SQRT_2);
        let steps = [(-1, 0, straight), (0, -1, straight), (-1, -1, diagonal), (1, -1, diagonal)];
        let columns = self.columns as i64;
        let rows = self.distance.len() as i64 / columns;
        let cells: Vec<(i64, i64)> = (0..rows).flat_map(|y| (0..columns).map(move |x| (x, y))).collect();
        let passes = [(cells.clone(), 1), (cells.into_iter().rev().collect(), -1)];
        for (order, sign) in passes {
            for (x, y) in order {
                for (dx, dy, step) in steps {
                    let (nx, ny) = (x + dx * sign, y + dy * sign);
                    if nx >= 0 && ny >= 0 && nx < columns && ny < rows {
                        let near = self.distance[(ny * columns + nx) as usize] + step;
                        let here = &mut self.distance[(y * columns + x) as usize];
                        *here = here.min(near);
                    }
                }
            }
        }
    }

    // 離最近的可行走地面幾公尺，範圍外當作很遠
    fn walk_distance(&self, spot: Vector2) -> f32 {
        if !self.bounds.contains_point(spot) {
            return f32::INFINITY;
        }
        let cell = (spot - self.bounds.position) / WALK_CELL;
        let x = (cell.x as usize).min(self.columns - 1);
        let y = (cell.y as usize).min(self.distance.len() / self.columns - 1);
        self.distance[y * self.columns + x]
    }

    fn path_distance(&self, spot: Vector2) -> f32 {
        let segments = self.paths.iter().flat_map(|line| line.windows(2));
        let to_segment = |pair: &[Vector2]| {
            let along = pair[1] - pair[0];
            let t = (spot - pair[0]).dot(along) / along.length_squared().max(1e-4);
            spot.distance_to(pair[0] + along * t.clamp(0.0, 1.0))
        };
        segments.map(to_segment).fold(f32::INFINITY, f32::min)
    }

    // 離廣場這類區域邊緣多遠，在裡面是負的
    fn area_distance(&self, spot: Vector2) -> f32 {
        let to_edge = |a: &Area| spot.distance_to(a.center) - a.radius;
        self.areas.iter().map(to_edge).fold(f32::INFINITY, f32::min)
    }

    fn is_open(&self, spot: Vector2, clearance: f32) -> bool {
        self.path_distance(spot) > PATH_WIDTH * 0.5 + clearance && self.area_distance(spot) > clearance
    }

    fn is_grass(&self, spot: Vector2) -> bool {
        self.walk_distance(spot) <= GRASS_FRINGE
    }

    // 自己和四周 margin 公尺的八個點都走得到
    fn is_inland(&self, spot: Vector2, margin: f32) -> bool {
        let ring = (0..8).map(|i| spot + Vector2::RIGHT.rotated(i as f32 * TAU / 8.0) * margin);
        ring.chain([spot]).all(|p| self.walk_distance(p) == 0.0)
    }

    fn near_portal(&self, spot: Vector2) -> bool {
        let reach = |&(at, radius): &(Vector2, f32)| spot.distance_to(at) < radius + PORTAL_CLEAR;
        self.portals.iter().any(reach)
    }

    // 離可行走範圍 low 到 high 公尺的格子中心，順序打亂
    fn band(&self, low: f32, high: f32, rng: &mut Rng) -> Vec<Vector2> {
        let cells = (0..self.distance.len()).filter(|&i| (low..=high).contains(&self.distance[i]));
        let mut spots: Vec<Vector2> = cells.map(|i| self.cell_center(i)).collect();
        for i in (1..spots.len()).rev() {
            spots.swap(i, (rng.unit() * (i + 1) as f32) as usize % (i + 1));
        }
        spots
    }

    fn random_spot(&self, rng: &mut Rng) -> Vector2 {
        let (low, high) = (self.bounds.position, self.bounds.end());
        Vector2::new(rng.range(low.x, high.x), rng.range(low.y, high.y))
    }
}

fn far_from(spot: Vector2, placed: &[Vector2], distance: f32) -> bool {
    placed.iter().all(|p| p.distance_to(spot) >= distance)
}

// 地面材質的貼圖和顏色在場景檔，這裡填小路、區域和走不到的地方畫黑的遮罩
fn terrain(mut ground: Gd<MeshInstance3D>, map: &Map) {
    let mut material = ground.get_material_override().unwrap().cast::<ShaderMaterial>();
    let mut set = |name: &str, value: Variant| material.set_shader_parameter(name, &value);
    let mut points = PackedVector2Array::new();
    let mut paths = PackedVector4Array::new();
    for line in &map.paths {
        let (start, count) = (points.len() as f32, line.len() as f32);
        paths.push(Vector4::new(start, count, PATH_WIDTH * 0.5, DIRT));
        points.extend(line.iter().copied());
    }
    set("path_count", (paths.len() as i32).to_variant());
    set("path_points", points.to_variant());
    set("paths", paths.to_variant());
    let areas = map.areas.iter().map(|a| Vector4::new(a.center.x, a.center.y, a.radius, a.edge));
    set("areas", areas.collect::<PackedVector4Array>().to_variant());
    let layers: PackedInt32Array = map.areas.iter().map(|a| a.layer).collect();
    set("area_layer", layers.to_variant());
    set("area_count", (map.areas.len() as i32).to_variant());

    let shades = map.distance.iter().map(|d| ((d / MASK_RANGE).min(1.0) * 255.0) as u8);
    let rows = (map.distance.len() / map.columns) as i32;
    let bytes: PackedByteArray = shades.collect();
    let image = Image::create_from_data(map.columns as i32, rows, false, Format::R8, &bytes);
    let mask = ImageTexture::create_from_image(image.as_ref());
    let rect = map.bounds;
    set("walk_mask", mask.to_variant());
    let walk_rect = Vector4::new(rect.position.x, rect.position.y, rect.size.x, rect.size.y);
    set("walk_rect", walk_rect.to_variant());
    set("walk_mask_range", MASK_RANGE.to_variant());
    let fade = if map.dark_outside { Vector2::new(0.8, 3.0) } else { Vector2::new(1e5, 1e6) };
    set("walk_fade", fade.to_variant());

    let size = GROUND_MIN_SIZE.max(rect.size.x.max(rect.size.y) + GROUND_MARGIN * 2.0);
    let mut plane = ground.get_mesh().unwrap().cast::<PlaneMesh>();
    plane.set_size(Vector2::new(size, size));
    ground.set_position(Vector3::new(rect.center().x, 0.0, rect.center().y));
}

// 可行走範圍外種一圈樹林：內緣一排樹貼著邊，隔一段一塊大石頭，縫裡塞樹叢；傳送點附近不擺
fn forest(root: &mut Gd<Node3D>, map: &Map, rng: &mut Rng) {
    let clear = PATH_WIDTH * 0.5 + 0.9;
    let free = |spot: Vector2| map.path_distance(spot) > clear && !map.near_portal(spot);
    let mut trunks = vec![];
    for spot in map.band(0.4, 1.0, rng) {
        if free(spot) && far_from(spot, &trunks, 2.3) {
            trunks.push(spot);
        }
    }
    let mut rocks = vec![];
    for spot in map.band(1.0, 1.6, rng) {
        if free(spot) && far_from(spot, &rocks, 9.0) && far_from(spot, &trunks, 1.4) {
            rocks.push(spot);
        }
    }
    let mut bushes = vec![];
    for spot in map.band(0.5, 1.0, rng) {
        let apart = far_from(spot, &trunks, 1.5) && far_from(spot, &rocks, 1.6);
        if free(spot) && apart && far_from(spot, &bushes, 1.5) {
            bushes.push(spot);
        }
    }
    let edges = [(trunks, 0.95, 1.25), (bushes, 0.8, 1.15), (rocks, 1.2, 1.6)];
    let mut places: Vec<Vec<Place>> = vec![];
    for (spots, low, high) in edges {
        places.push(spots.into_iter().map(|s| rng.place(s, low, high)).collect());
    }
    for (model, place) in &map.props {
        match PROPS.iter().position(|p| p.0 == model) {
            Some(kind) => places[kind].push(*place),
            None => godot_warn!("地圖擺設沒有對應的模型：{model}"),
        }
    }
    for ((_, models, scale), list) in PROPS.iter().zip(&places) {
        plant(root, models, *scale, list, false);
    }
}

fn cover(root: &mut Gd<Node3D>, map: &Map, rng: &mut Rng) {
    let walkable = map.distance.iter().filter(|&&d| d == 0.0).count() as f32;
    let ratio = walkable * WALK_CELL * WALK_CELL / REFERENCE_WALK_AREA;
    for (name, count, scale, models) in COVER {
        let target = ((count as f32 * ratio).round() as usize).max(1);
        let mut places = vec![];
        for _ in 0..target * 8 {
            let spot = map.random_spot(rng);
            let to_path = map.path_distance(spot) - PATH_WIDTH * 0.5;
            let fits = match name {
                "pebbles" => (-0.2..1.2).contains(&to_path) && map.area_distance(spot) > 0.5,
                // 蕨類是林地的東西，長在靠樹林那一圈
                "fern" => !map.is_inland(spot, 4.0) && map.is_open(spot, 0.3),
                _ => map.is_open(spot, 0.3),
            };
            if places.len() < target && fits && map.is_grass(spot) {
                places.push(rng.place(spot, 0.8, 1.3));
            }
        }
        // 成片的花像花圃，每片 38 朵
        for &(x, z, _) in FLOWER_PATCHES.iter().filter(|p| p.2 == name) {
            let mut local = Rng(SEED ^ (x * 131.0 + z * 17.0).to_bits() as u64);
            let mut planted = 0;
            for _ in 0..38 * 3 {
                let angle = local.range(0.0, TAU);
                let spread = local.unit().sqrt() * 2.2;
                let spot = Vector2::new(x, z) + Vector2::new(angle.cos(), angle.sin() * 0.7) * spread;
                if planted < 38 && map.is_open(spot, 0.4) && map.is_grass(spot) {
                    planted += 1;
                    places.push(local.place(spot, 0.9, 1.5));
                }
            }
        }
        plant(root, models, scale, &places, true);
    }
}

// 同一種東西的幾個模型輪流分，每個模型一個 MultiMesh；地被不投影
fn plant(root: &mut Gd<Node3D>, models: &str, scale: f32, places: &[Place], ground_cover: bool) {
    let models: Vec<&str> = models.split(' ').collect();
    let look = root.get_meta(if ground_cover { "cover" } else { "canopy" }).to();
    for (index, model) in models.iter().enumerate() {
        let mine: Vec<Place> = places.iter().skip(index).step_by(models.len()).copied().collect();
        let Some(mesh) = model_mesh(model, &look, ground_cover) else {
            godot_warn!("載不到模型 {model}");
            continue;
        };
        let mut instance = multimesh(&mesh, &mine, scale);
        instance.set_name(*model);
        if ground_cover {
            instance.set_cast_shadows_setting(ShadowCastingSetting::OFF);
        }
        root.add_child(&instance);
    }
}

fn multimesh(mesh: &Gd<Mesh>, places: &[Place], scale: f32) -> Gd<MultiMeshInstance3D> {
    let rows = places.iter().flat_map(|p| {
        let s = p.scale * scale;
        let (sin, cos) = (p.yaw.sin() * s, p.yaw.cos() * s);
        [cos, 0.0, sin, p.at.x, 0.0, s, 0.0, 0.0, -sin, 0.0, cos, p.at.y]
    });
    let mut multimesh = MultiMesh::new_gd();
    multimesh.set_transform_format(TransformFormat::TRANSFORM_3D);
    multimesh.set_instance_count(places.len() as i32);
    multimesh.set_buffer(&rows.collect::<PackedFloat32Array>());
    multimesh.set_mesh(mesh);
    let mut instance = MultiMeshInstance3D::new_alloc();
    instance.set_multimesh(&multimesh);
    instance
}

// 模型檔裡第一個網格，葉片換成場景檔給的會晃的材質，樹皮和石頭照原本的材質
fn model_mesh(model: &str, look: &Gd<ShaderMaterial>, ground_cover: bool) -> Option<Gd<Mesh>> {
    let node = try_load::<PackedScene>(&format!("{NATURE}{model}.gltf")).ok()?.instantiate()?;
    let found = node.find_children_ex("*").type_("MeshInstance3D").done().iter_shared().next();
    let mesh = found.and_then(|n| n.cast::<MeshInstance3D>().get_mesh());
    node.free();
    let mut mesh = mesh?.duplicate_resource();
    for surface in 0..mesh.get_surface_count() {
        let material = mesh.surface_get_material(surface);
        let Some(Ok(source)) = material.map(|m| m.try_cast::<StandardMaterial3D>()) else {
            continue;
        };
        let name = source.get_name().to_string().to_lowercase();
        let leaf = source.get_transparency() == Transparency::ALPHA_SCISSOR && !name.starts_with("bark");
        let Some(texture) = source.get_texture(TextureParam::ALBEDO).filter(|_| leaf) else {
            continue;
        };
        let mut leaves = look.duplicate_resource();
        leaves.set_shader_parameter("albedo_texture", &texture.to_variant());
        shade_canopy(&mut leaves, &mesh, surface, ground_cover);
        mesh.surface_set_material(surface, &leaves.upcast::<Material>());
    }
    Some(mesh)
}

// 明暗漸層照葉片那一面的範圍；樹冠像一顆球從中心往外受光，地被的中心在場景檔放到地底深處
fn shade_canopy(material: &mut Gd<ShaderMaterial>, mesh: &Gd<Mesh>, surface: i32, ground_cover: bool) {
    let vertices: PackedVector3Array = mesh.surface_get_arrays(surface).at(0).to();
    let first = vertices.as_slice().first().copied().unwrap_or_default();
    let mut bounds = Aabb::new(first, Vector3::ZERO);
    for vertex in vertices.as_slice() {
        bounds = bounds.expand(*vertex);
    }
    if ground_cover {
        bounds = mesh.get_aabb();
    } else {
        material.set_shader_parameter("canopy_center", &bounds.center().to_variant());
    }
    material.set_shader_parameter("gradient_bottom", &bounds.position.y.to_variant());
    material.set_shader_parameter("gradient_height", &bounds.size.y.max(0.1).to_variant());
}

// 草毯鋪滿走得到的地面，像毯子一樣看不到地；切成 8 公尺一格，鏡頭外的格子整格不畫
fn carpet(root: &mut Gd<Node3D>, map: &Map, rng: &mut Rng) {
    let mut cells: HashMap<(i32, i32), Vec<Place>> = HashMap::new();
    for _ in 0..(map.bounds.area() * CARPET_DENSITY) as usize {
        let spot = map.random_spot(rng);
        let place = rng.place(spot, 0.8, 1.25);
        if map.is_open(spot, 0.25) && map.is_grass(spot) {
            let cell = (spot / CARPET_CELL).floor();
            cells.entry((cell.x as i32, cell.y as i32)).or_default().push(place);
        }
    }
    let material = root.get_meta("grass").to::<Gd<Material>>();
    let clump = blade_clump();
    for places in cells.values() {
        let mut instance = multimesh(&clump, places, 1.0);
        instance.set_material_override(&material);
        instance.set_cast_shadows_setting(ShadowCastingSetting::OFF);
        root.add_child(&instance);
    }
}

// 一叢草：七片往外倒的葉子，每片三個三角形，UV.y 是離地高度比例；壓到腳踝才不會蓋掉怪的下半身
fn blade_clump() -> Gd<Mesh> {
    let mut rng = Rng(5);
    let mut surface = SurfaceTool::new_gd();
    surface.begin(PrimitiveType::TRIANGLES);
    for blade in 0..7 {
        let angle = blade as f32 * TAU / 7.0 + rng.range(-0.3, 0.3);
        let out = Vector3::new(angle.cos(), 0.0, angle.sin());
        let base = out * rng.range(0.02, 0.16);
        let (height, lean) = (rng.range(0.14, 0.26), rng.range(0.06, 0.2));
        let width = Vector3::new(-out.z, 0.0, out.x) * rng.range(0.035, 0.05);
        let mid = base + out * lean * 0.4 + Vector3::UP * height * 0.55;
        let tip = base + out * lean + Vector3::UP * height;
        let (p0, p1) = (base - width, base + width);
        let (p2, p3) = (mid - width * 0.7, mid + width * 0.7);
        for corner in [p0, p1, p3, p0, p3, p2, p2, p3, tip] {
            surface.set_normal(Vector3::UP);
            surface.set_uv(Vector2::new(0.5, corner.y / height));
            surface.add_vertex(corner);
        }
    }
    surface.commit().expect("草葉網格").upcast()
}

/// 放進場景就照 map_id 蓋地圖，預覽場景用
#[derive(GodotClass)]
#[class(init, base=Node3D)]
pub struct RofMap {
    base: Base<Node3D>,
    #[export]
    map_id: GString,
}

#[godot_api]
impl INode3D for RofMap {
    fn ready(&mut self) {
        let map = build(&self.map_id.to_string());
        self.base_mut().add_child(&map);
    }
}
