import os

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PIPELINE_DIR)
BUILD_DIR = os.path.join(PIPELINE_DIR, "_build")
SPRITES_OUT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites")
MODELS_OUT = os.path.join(PROJECT_ROOT, "assets", "generated", "models")

# 所有角色和怪物共用同一個比例，大小才會一致
PX_PER_M = 80.0
CAMERA_ELEVATION_DEG = 25.0

# 只算圖這 5 個方向，右側 3 個方向由遊戲端水平翻轉
RENDER_DIRECTIONS = ["S", "SW", "W", "NW", "N"]

OUTLINE_COLOR = (0.07, 0.05, 0.05, 1.0)
OUTLINE_THICKNESS = 0.01
