extends SceneTree
## 擴充載得進來、GDScript 呼叫得到 Rust


func _initialize() -> void:
	var failures := 0
	if not ClassDB.class_exists("RofInfo"):
		push_error("擴充沒載進來，先在 rust/ 跑 cargo build -p rof-gdext")
		failures += 1
	else:
		var info: RefCounted = ClassDB.instantiate("RofInfo")
		print("rof-gdext ", info.version(), "，協定 ", info.protocol_version(), "，tick ", info.tick_ms(), " 毫秒")
		if info.protocol_version() != 1 or info.tick_ms() != 50:
			push_error("擴充回的數字不對")
			failures += 1
	print("冒煙測試 " + ("通過" if failures == 0 else "失敗"))
	quit(1 if failures > 0 else 0)
