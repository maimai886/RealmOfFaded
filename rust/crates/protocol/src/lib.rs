//! 封包協定。信封格式 `{"v": 版本, "t": 類型, "id": 請求編號, "d": {資料}}`，JSON 文字走 WebSocket。
//! 照舊專案 `src/net/protocol.gd` 的規則：先擋大小、再解析、再查版本和信封欄位、最後查類型。
//! 訊息類型和欄位規則在 M1 補，現在由呼叫的人傳一個判斷類型認不認得的函式進來。

use serde_json::{Map, Value};

pub const VERSION: i64 = 1;
/// 單一訊息 UTF-8 位元組數上限，超過伺服器直接斷線
pub const MAX_MESSAGE_BYTES: usize = 8192;
/// JSON 數字能精確表示的最大整數，信封 id 不能超過
pub const MAX_SAFE_INT: i64 = 9_007_199_254_740_991;
/// 一個數字最多幾個字元，太長的數字是在洗伺服器，不解析直接擋
pub const MAX_NUMBER_CHARS: usize = 64;

/// 解不開的原因，字串和舊協定一樣，伺服器回給客戶端的是代碼不是句子
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DecodeError {
    TooLarge,
    BadJson,
    BadEnvelope,
    BadVersion,
    UnknownType,
}

impl DecodeError {
    pub fn code(self) -> &'static str {
        match self {
            DecodeError::TooLarge => "too_large",
            DecodeError::BadJson => "bad_json",
            DecodeError::BadEnvelope => "bad_envelope",
            DecodeError::BadVersion => "bad_version",
            DecodeError::UnknownType => "unknown_type",
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Envelope {
    pub t: String,
    pub id: i64,
    pub d: Map<String, Value>,
}

pub fn encode(t: &str, id: i64, d: Map<String, Value>) -> String {
    let mut root = Map::new();
    root.insert("v".into(), Value::from(VERSION));
    root.insert("t".into(), Value::from(t));
    root.insert("id".into(), Value::from(id));
    root.insert("d".into(), Value::Object(d));
    Value::Object(root).to_string()
}

pub fn decode(text: &str, is_known_type: impl Fn(&str) -> bool) -> Result<Envelope, DecodeError> {
    if text.len() > MAX_MESSAGE_BYTES {
        return Err(DecodeError::TooLarge);
    }
    if has_oversized_number(text) || text.contains("\\u0000") {
        return Err(DecodeError::BadJson);
    }
    let value: Value = serde_json::from_str(text).map_err(|_| DecodeError::BadJson)?;
    let Value::Object(mut root) = value else {
        return Err(DecodeError::BadEnvelope);
    };
    let version = root.get("v").ok_or(DecodeError::BadEnvelope)?;
    if whole_number(version) != Some(VERSION) {
        return Err(DecodeError::BadVersion);
    }
    if root.len() != 4 {
        return Err(DecodeError::BadEnvelope);
    }
    let id = root.get("id").and_then(whole_number).filter(|id| id.abs() <= MAX_SAFE_INT);
    let (Some(Value::String(t)), Some(Value::Object(d)), Some(id)) = (root.remove("t"), root.remove("d"), id) else {
        return Err(DecodeError::BadEnvelope);
    };
    if !is_known_type(&t) {
        return Err(DecodeError::UnknownType);
    }
    Ok(Envelope { t, id, d })
}

/// 整數或小數點後為零的數字，其他回 None
fn whole_number(value: &Value) -> Option<i64> {
    if let Some(n) = value.as_i64() {
        return Some(n);
    }
    let f = value.as_f64()?;
    (f.fract() == 0.0 && f.abs() <= MAX_SAFE_INT as f64).then_some(f as i64)
}

/// 字串外面連續的數字字元超過上限就算洗版
fn has_oversized_number(text: &str) -> bool {
    let mut in_string = false;
    let mut escaped = false;
    let mut run = 0usize;
    for c in text.chars() {
        if in_string {
            if escaped {
                escaped = false;
            } else if c == '\\' {
                escaped = true;
            } else if c == '"' {
                in_string = false;
            }
            continue;
        }
        if c == '"' {
            in_string = true;
            run = 0;
        } else if c.is_ascii_digit() || matches!(c, '-' | '+' | '.' | 'e' | 'E') {
            run += 1;
            if run > MAX_NUMBER_CHARS {
                return true;
            }
        } else {
            run = 0;
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn any(_: &str) -> bool {
        true
    }

    #[test]
    fn round_trip() {
        let mut d = Map::new();
        d.insert("x".into(), json!(1.5));
        let text = encode("move", 7, d.clone());
        assert_eq!(decode(&text, any), Ok(Envelope { t: "move".into(), id: 7, d }));
    }

    #[test]
    fn rejects_in_the_same_order_as_the_old_protocol() {
        let big = format!(r#"{{"v":1,"t":"x","id":1,"d":{{"s":"{}"}}}}"#, "a".repeat(MAX_MESSAGE_BYTES));
        assert_eq!(decode(&big, any), Err(DecodeError::TooLarge));
        assert_eq!(decode("{", any), Err(DecodeError::BadJson));
        assert_eq!(decode(r#"{"v":1,"t":"x","id":1,"d":{"s":"\u0000"}}"#, any), Err(DecodeError::BadJson));
        let long_number = format!(r#"{{"v":1,"t":"x","id":1,"d":{{"n":{}}}}}"#, "9".repeat(80));
        assert_eq!(decode(&long_number, any), Err(DecodeError::BadJson));
        assert_eq!(decode("[]", any), Err(DecodeError::BadEnvelope));
        assert_eq!(decode(r#"{"v":2,"t":"x","id":1,"d":{}}"#, any), Err(DecodeError::BadVersion));
        assert_eq!(decode(r#"{"v":1,"t":"x","id":1,"d":{},"z":0}"#, any), Err(DecodeError::BadEnvelope));
        assert_eq!(decode(r#"{"v":1,"t":"x","id":1.5,"d":{}}"#, any), Err(DecodeError::BadEnvelope));
        assert_eq!(decode(r#"{"v":1,"t":"x","id":1,"d":[]}"#, any), Err(DecodeError::BadEnvelope));
        assert_eq!(decode(r#"{"v":1,"t":"x","id":1,"d":{}}"#, |_| false), Err(DecodeError::UnknownType));
    }

    #[test]
    fn long_strings_are_not_numbers() {
        let text = format!(r#"{{"v":1,"t":"x","id":1,"d":{{"s":"{}"}}}}"#, "1".repeat(200));
        assert!(decode(&text, any).is_ok());
    }

    #[test]
    fn godot_style_whole_floats_are_accepted() {
        assert_eq!(decode(r#"{"v":1.0,"t":"x","id":3.0,"d":{}}"#, any).map(|e| e.id), Ok(3));
    }
}
