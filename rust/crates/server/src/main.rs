//! 遊戲伺服器。M1 起接上 tokio 和 WebSocket，現在只讀參數和檢查資料。

use std::path::PathBuf;
use std::process::ExitCode;

/// 新專案的開發伺服器預設 7780，不撞舊專案的 7777、7778、7779
const DEFAULT_PORT: u16 = 7780;

fn main() -> ExitCode {
    let mut port = DEFAULT_PORT;
    let mut game_data: Option<PathBuf> = None;
    for arg in std::env::args().skip(1) {
        if let Some(v) = arg.strip_prefix("--port=") {
            match v.parse() {
                Ok(p) => port = p,
                Err(_) => {
                    eprintln!("埠號不對：{v}");
                    return ExitCode::FAILURE;
                }
            }
        } else if let Some(v) = arg.strip_prefix("--game-data=") {
            game_data = Some(PathBuf::from(v));
        }
    }
    let cwd = std::env::current_dir().unwrap_or_default();
    let Some(dir) = game_data.or_else(|| rof_data::find_data_dir(&cwd)) else {
        eprintln!("找不到遊戲資料，用 --game-data= 指定 data 資料夾");
        return ExitCode::FAILURE;
    };
    match rof_data::read_json(&dir.join("balance.json")) {
        Ok(_) => {
            println!("Realm of Faded 伺服器 {}，埠 {port}，資料 {}", env!("CARGO_PKG_VERSION"), dir.display());
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("{e}");
            ExitCode::FAILURE
        }
    }
}
