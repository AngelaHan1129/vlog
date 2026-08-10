import os
import torch
from transformers import pipeline

# 全域變數：確保伺服器啟動期間，ASR 模型只載入一次
_asr_pipeline = None

def _get_asr_pipeline():
    global _asr_pipeline
    if _asr_pipeline is None:
        print("🚀 正在從 Hugging Face 載入 Whisper-large-v3-turbo 語音辨識模型...")
        
        # 自動判斷是否有 NVIDIA 顯卡可用
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        
        # 為了節省 VRAM，如果有顯卡則使用 float16 精度
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        
        # 載入 Whisper Pipeline
        _asr_pipeline = pipeline(
            "automatic-speech-recognition",
            model="openai/whisper-large-v3-turbo",
            torch_dtype=torch_dtype,
            device=device,
        )
        print("✅ Whisper ASR 模型載入完成！")
        
    return _asr_pipeline

def transcribe_audio(audio_path: str, language: str = "chinese") -> str:
    """
    將使用者的錄音檔轉換為純文字
    :param audio_path: 錄音檔的絕對或相對路徑
    :param language: 強制指定語言（chinese 能大幅提升中文辨識與標點符號的準確度）
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"找不到錄音檔: {audio_path}")

    asr_pipe = _get_asr_pipeline()

    print(f"👂 系統正在聆聽並辨識語音... (檔案: {audio_path})")

    # 執行語音辨識 (generate_kwargs 用來強制模型輸出繁體/簡體中文)
    result = asr_pipe(
        audio_path,
        generate_kwargs={"language": language, "task": "transcribe"}
    )
    
    transcribed_text = result["text"].strip()
    print(f"✅ 辨識完成：\n「{transcribed_text}」\n")
    
    return transcribed_text
