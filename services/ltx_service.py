import os
import torch
import uuid
from PIL import Image
from diffusers import LTXImageToVideoPipeline
from diffusers.utils import export_to_video
from core.config import OUTPUT_DIR

# 全域變數：確保伺服器啟動期間，模型只載入一次
_pipeline = None

def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        print("🚀 正在載入 LTX-Video AI 模型 (需消耗較多 VRAM)...")
        
        # 使用 bfloat16 資料型態載入，大幅節省顯示卡記憶體
        _pipeline = LTXImageToVideoPipeline.from_pretrained(
            "Lightricks/LTX-Video", 
            torch_dtype=torch.bfloat16
        )
        
        # 啟用模型 CPU 卸載優化 (非常重要，能讓 24GB VRAM 以下的顯卡也能跑)
        _pipeline.enable_model_cpu_offload()
        print("✅ LTX-Video 模型載入完成！")
        
    return _pipeline

def generate_ltx_video(image_path: str, prompt: str) -> str:
    """
    實作 LTX-Video 圖生影片 (I2V) 的推論邏輯
    """
    # 1. 檢查圖片是否存在
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"找不到來源圖片: {image_path}")

    # 2. 準備圖片與載入模型
    image = Image.open(image_path).convert("RGB")
    pipe = _get_pipeline()

    # 3. 準備輸出路徑
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    unique_id = uuid.uuid4().hex[:8]
    output_filename = f"ltx_{unique_id}.mp4"
    output_path = OUTPUT_DIR / output_filename

    print(f"🎥 開始生成 AI 動態影片... (提示詞: {prompt})")

    # 4. 執行推論
    # 參數微調說明：
    # width/height: 解析度需為 32 的倍數
    # num_frames: 49 幀在 24fps 下約等於 2 秒的影片
    video_frames = pipe(
        image=image,
        prompt=prompt,
        negative_prompt="worst quality, inconsistent motion, blurry, jittery, distorted, watermark",
        width=768,           
        height=512,          
        num_frames=49,       
        num_inference_steps=40, 
        guidance_scale=3.0,
    ).frames[0]

    # 5. 將生成的影格陣列輸出成 mp4 影片
    export_to_video(video_frames, str(output_path), fps=24)
    
    print(f"✅ AI 影片生成完畢！已儲存至: {output_path}")
    
    return str(output_path)