extends RefCounted
## 文字表：玩家看得到的字從 locale/zh_TW.json 取，句子裡的 {名字} 用具名參數代進去，規矩在 docs/多國語系規劃.md

const TABLE_PATH := "res://locale/zh_TW.json"

static var _table: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(TABLE_PATH))


## 找不到鍵時回傳鍵本身，畫面上看得出漏了哪一條
static func text(key: String, params := {}) -> String:
	return String(_table.get(key, key)).format(params)


static func has(key: String) -> bool:
	return _table.has(key)
