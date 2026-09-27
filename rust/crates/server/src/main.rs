//! 伺服器執行檔：`cargo run -p rof-server -- --port=7780`。

use std::path::PathBuf;
use std::process::ExitCode;

// 舊專案佔了 7777 到 7779
const DEFAULT_PORT: u16 = 7780;

#[tokio::main]
async fn main() -> ExitCode {
    let mut port = DEFAULT_PORT;
    let mut data_dir: Option<PathBuf> = None;
    let mut config = PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/config/servers.json"));
    for arg in std::env::args().skip(1) {
        if let Some(v) = arg.strip_prefix("--port=") {
            let Ok(p) = v.parse() else {
                eprintln!("埠號不對：{v}");
                return ExitCode::FAILURE;
            };
            port = p;
        } else if let Some(v) = arg.strip_prefix("--game-data=") {
            data_dir = Some(v.into());
        } else if let Some(v) = arg.strip_prefix("--config=") {
            config = v.into();
        }
    }
    let cwd = std::env::current_dir().unwrap_or_default();
    let Some(dir) = data_dir.or_else(|| rof_data::find_data_dir(&cwd)) else {
        eprintln!("找不到遊戲資料，用 --game-data= 指定 data 資料夾");
        return ExitCode::FAILURE;
    };
    let started = match rof_server::Settings::load(dir, &config) {
        Ok(settings) => rof_server::start(settings, port).await,
        Err(e) => Err(e),
    };
    match started {
        Ok(server) => {
            println!("Realm of Faded 伺服器 {}，{}", env!("CARGO_PKG_VERSION"), server.addr);
            let _ = tokio::signal::ctrl_c().await;
            server.shutdown().await;
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("{e}");
            ExitCode::FAILURE
        }
    }
}
