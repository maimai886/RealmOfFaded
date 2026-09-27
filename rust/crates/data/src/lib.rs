//! 讀 `data/*.json`。

use std::path::{Path, PathBuf};

use serde_json::Value;

pub fn read_json(path: &Path) -> Result<Value, String> {
    let text =
        std::fs::read_to_string(path).map_err(|e| format!("讀不到 {}：{e}", path.display()))?;
    serde_json::from_str(&text).map_err(|e| format!("{} 不是合法的 JSON：{e}", path.display()))
}

// 舊 JSON 的整數常寫成 1.0
pub fn lenient_i64(value: &Value) -> Option<i64> {
    value.as_i64().or_else(|| {
        value
            .as_f64()
            .filter(|f| f.fract() == 0.0 && f.abs() < 9e15)
            .map(|f| f as i64)
    })
}

/// 從 start 往上找含 balance.json 的 data 資料夾
pub fn find_data_dir(start: &Path) -> Option<PathBuf> {
    start
        .ancestors()
        .map(|dir| dir.join("data"))
        .find(|dir| dir.join("balance.json").is_file())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn whole_floats_count_as_integers() {
        assert_eq!(lenient_i64(&json!(3)), Some(3));
        assert_eq!(lenient_i64(&json!(-12.0)), Some(-12));
        assert_eq!(lenient_i64(&json!(3.5)), None);
        assert_eq!(lenient_i64(&json!("3")), None);
    }

    #[test]
    fn every_data_file_is_valid_json() {
        let mut dirs = vec![find_data_dir(Path::new(env!("CARGO_MANIFEST_DIR"))).unwrap()];
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
}
