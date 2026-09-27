//! 讀 `data/*.json`。

mod map;

use std::path::{Path, PathBuf};

use serde::Deserialize;
use serde::de::DeserializeOwned;
use serde_json::Value;

pub use map::{Blocker, Bounds, EDGE_TOLERANCE, MapData};

pub fn read_json(path: &Path) -> Result<Value, String> {
    read(path)
}

pub fn read<T: DeserializeOwned>(path: &Path) -> Result<T, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("讀不到 {}：{e}", path.display()))?;
    serde_json::from_str(&text).map_err(|e| format!("{} 格式不對：{e}", path.display()))
}

// 舊 JSON 的整數常寫成 1.0
pub fn lenient_i64(value: &Value) -> Option<i64> {
    value.as_i64().or_else(|| value.as_f64().filter(|f| f.fract() == 0.0 && f.abs() < 9e15).map(|f| f as i64))
}

/// 從 start 往上找含 balance.json 的 data 資料夾
pub fn find_data_dir(start: &Path) -> Option<PathBuf> {
    start.ancestors().map(|dir| dir.join("data")).find(|dir| dir.join("balance.json").is_file())
}

/// 捏臉的選項數量，照 `appearances.json` 的 keys 順序
pub struct Appearances {
    keys: Vec<String>,
    female: Vec<i64>,
    male: Vec<i64>,
}

impl Appearances {
    pub fn load(data_dir: &Path) -> Result<Self, String> {
        let options = read_json(&data_dir.join("appearances.json"))?["options"].take();
        let keys: Vec<String> =
            serde_json::from_value(options["keys"].clone()).map_err(|_| "appearances.json 的 keys 不對".to_string())?;
        let count = |key: &String, gender: &str| {
            let list = &options[key];
            let list = if list.is_object() { &list[gender] } else { list };
            list.as_array().map(|a| a.len() as i64)
        };
        let counts = |gender| keys.iter().map(|key| count(key, gender)).collect();
        let (Some(female), Some(male)) = (counts("female"), counts("male")) else {
            return Err("appearances.json 有選項不是陣列".into());
        };
        Ok(Appearances { keys, female, male })
    }

    /// 每一項 0 到數量減 1，沒帶的算 0；有一項不合法回 None
    pub fn normalize(
        &self,
        gender: &str,
        raw: &serde_json::Map<String, Value>,
    ) -> Option<std::collections::BTreeMap<String, u32>> {
        let counts = if gender == "male" { &self.male } else { &self.female };
        self.keys
            .iter()
            .zip(counts)
            .map(|(key, &count)| {
                let value = raw.get(key).map_or(Some(0), lenient_i64)?;
                (0..count).contains(&value).then(|| (key.clone(), value as u32))
            })
            .collect()
    }
}

#[derive(Deserialize)]
pub struct ReservedNames {
    exact: Vec<String>,
    fragments: Vec<String>,
}

impl ReservedNames {
    pub fn load(data_dir: &Path) -> Result<Self, String> {
        read(&data_dir.join("reserved_names.json"))
    }

    pub fn contains(&self, name: &str) -> bool {
        let lower = name.to_lowercase();
        self.exact.contains(&lower) || self.fragments.iter().any(|f| lower.contains(f.as_str()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn data_dir() -> PathBuf {
        find_data_dir(Path::new(env!("CARGO_MANIFEST_DIR"))).unwrap()
    }

    #[test]
    fn every_data_file_is_valid_json() {
        let mut dirs = vec![data_dir()];
        let mut checked = 0;
        while let Some(dir) = dirs.pop() {
            for path in std::fs::read_dir(dir).unwrap().map(|e| e.unwrap().path()) {
                if path.is_dir() {
                    dirs.push(path);
                } else if path.extension().is_some_and(|ext| ext == "json") {
                    read_json(&path).unwrap();
                    checked += 1;
                }
            }
        }
        assert!(checked >= 20, "只找到 {checked} 份資料");
    }

    #[test]
    fn default_looks_are_valid_choices() {
        let appearances = Appearances::load(&data_dir()).unwrap();
        let defaults = read_json(&data_dir().join("appearances.json")).unwrap();
        for gender in ["female", "male"] {
            let wanted = defaults["options"]["defaults"][gender].as_object().unwrap();
            let got = appearances.normalize(gender, wanted).unwrap();
            assert_eq!(got.len(), wanted.len(), "{gender} 的預設外觀");
        }
    }

    #[test]
    fn reserved_names_ignore_case_and_catch_fragments() {
        let reserved = ReservedNames::load(&data_dir()).unwrap();
        assert!(reserved.contains("GM") && reserved.contains("RoF"));
        assert!(reserved.contains("我是管理員"));
        assert!(!reserved.contains("小明"));
    }
}
