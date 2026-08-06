from pathlib import Path

# 將路徑推回 vlog_generator 根目錄
BASE_DIR = Path(__file__).resolve().parent.parent

ASSETS_DIR = BASE_DIR / "assets"
IMAGES_DIR = ASSETS_DIR / "images"
AUDIO_DIR = ASSETS_DIR / "audio"
BGM_DIR = ASSETS_DIR / "bgm"
OUTPUT_DIR = BASE_DIR / "output"

# Vlog 設定
VLOG_WIDTH = 1080
VLOG_HEIGHT = 1920
FPS = 30
IMAGE_DURATION = 3  # 每張圖片顯示秒數