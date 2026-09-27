#!/bin/sh
# 開發版：編好伺服器和擴充，背景開 7780 伺服器，再開遊戲；遊戲關掉時伺服器一起關
cd "$(dirname "$0")/rust" || exit 1
cargo build -p rof-server -p rof-gdext || exit 1
cargo run -q -p rof-server -- --port=7780 &
server=$!
"${GODOT:-/Applications/Godot.app/Contents/MacOS/Godot}" --path ..
kill $server
