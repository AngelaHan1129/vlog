import os
import torch
import warnings
from transformers import pipeline

# 🪄 關閉 transformers 不影響功能的警告
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

_asr_pipeline = None

def _get_asr_pipeline():
    global _asr_pipeline
    if _asr_pipeline is None:
        print("🚀 正在從 Hugging Face 載入 Whisper 多國語言辨識模型...")
        
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        
        _asr_pipeline = pipeline(
            "automatic-speech-recognition",
            model="openai/whisper-large-v3-turbo",
            torch_dtype=torch_dtype,
            device=device,
        )
        print("✅ Whisper ASR 模型載入完成！")
        
    return _asr_pipeline

# 💡 將預設 language 改為 None，讓模型自己聽音辨位！
def transcribe_audio(audio_path: str, language: str = None) -> str:
    """
    將使用者的錄音檔轉換為純文字 (支援多國語言自動偵測)
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"找不到錄音檔: {audio_path}")

    asr_pipe = _get_asr_pipeline()

    print(f"👂 系統正在跨國語言聆聽模式... (檔案: {audio_path})")

    # 動態設定參數
    gen_kwargs = {"task": "transcribe"}
    if language:
        gen_kwargs["language"] = language # 除非手動指定，否則不綁死語言

    # 執行語音辨識
    result = asr_pipe(
        audio_path,
        generate_kwargs=gen_kwargs
    )
    
    transcribed_text = result["text"].strip()
    print(f"✅ 辨識完成：\n「{transcribed_text}」\n")
    
    return transcribed_text
