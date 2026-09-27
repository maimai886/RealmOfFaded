//! 遊戲資料：`data/*.json` 的讀取和驗證。
//!
//! 舊專案的 JSON 是 Godot 寫的，整數常寫成 `1.0`，這裡讀的時候要接受小數點後為零的數當整數。
//! 各份資料的結構照 docs/Rust重構規劃.md 第 5 節的順序一份份補上。

use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};

use serde_json::Value;

/// 讀資料時出的錯，帶著是哪個檔
#[derive(Debug)]
pub enum DataError {
    Io { path: PathBuf, source: std::io::Error },
    Json { path: PathBuf, source: serde_json::Error },
}

impl fmt::Display for DataError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            DataError::Io { path, source } => write!(f, "讀不到 {}：{source}", path.display()),
            DataError::Json { path, source } => write!(f, "{} 不是合法的 JSON：{source}", path.display()),
        }
    }
}

impl std::error::Error for DataError {}

/// 讀一份 JSON 檔成通用的值
pub fn read_json(path: &Path) -> Result<Value, DataError> {
    let text = fs::read_to_string(path).map_err(|source| DataError::Io { path: path.to_path_buf(), source })?;
    serde_json::from_str(&text).map_err(|source| DataError::Json { path: path.to_path_buf(), source })
}

/// JSON 數字轉整數：`3` 和 `3.0` 都算 3，有小數、超出範圍或不是數字就回 None
pub fn lenient_i64(value: &Value) -> Option<i64> {
    if let Some(n) = value.as_i64() {
        return Some(n);
    }
    let f = value.as_f64()?;
    if f.fract() == 0.0 && f >= i64::MIN as f64 && f <= i64::MAX as f64 {
        Some(f as i64)
    } else {
        None
    }
}

/// 找專案的 data 資料夾：從目前位置一路往上找，給測試和工具用
pub fn find_data_dir(start: &Path) -> Option<PathBuf> {
    start.ancestors().map(|dir| dir.join("data")).find(|dir| dir.join("balance.json").is_file())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn whole_floats_count_as_integers() {
        assert_eq!(lenient_i64(&json!(3)), Some(3));
        assert_eq!(lenient_i64(&json!(3.0)), Some(3));
        assert_eq!(lenient_i64(&json!(-12.0)), Some(-12));
        assert_eq!(lenient_i64(&json!(3.5)), None);
        assert_eq!(lenient_i64(&json!("3")), None);
    }

    #[test]
    fn every_data_file_is_valid_json() {
        let dir = find_data_dir(Path::new(env!("CARGO_MANIFEST_DIR"))).expect("找不到 data 資料夾");
        let mut checked = 0;
        let mut stack = vec![dir];
        while let Some(dir) = stack.pop() {
            for entry in fs::read_dir(&dir).unwrap() {
                let path = entry.unwrap().path();
                if path.is_dir() {
                    stack.push(path);
                } else if path.extension().is_some_and(|ext| ext == "json") {
                    read_json(&path).unwrap_or_else(|e| panic!("{e}"));
                    checked += 1;
                }
            }
        }
        assert!(checked >= 20, "只找到 {checked} 份資料");
    }
}
