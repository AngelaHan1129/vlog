import os
import torch
import uuid
from huggingface_hub import snapshot_download

# ==========================================
# 🪄 補丁一：PyTorch 2.6+ 魔法小補丁 (解除安全限制)
# 告訴系統允許載入較舊的 Coqui TTS 模型結構
# ==========================================
_original_load = torch.load
def _legacy_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return _original_load(*args, **kwargs)
torch.load = _legacy_load

# ==========================================
# 🪄 補丁二：Transformers 幻術小補丁 (解決依賴衝突)
# 捏造一個空的 BeamSearchScorer 騙過 TTS 的載入檢查
# ==========================================
import transformers
if not hasattr(transformers, "BeamSearchScorer"):
    class DummyBeamSearchScorer: 
        pass
    transformers.BeamSearchScorer = DummyBeamSearchScorer

from TTS.api import TTS
from core.config import OUTPUT_DIR

# 全域變數
_tts_model = None

def _get_tts_model():
    global _tts_model
    if _tts_model is None:
        print("🚀 正在從 Hugging Face 載入台灣專屬 XTTS v2 模型...")

        device = "cuda" if torch.cuda.is_available() else "cpu"

        # 1. 檢查/載入本地快取的模型
        print("⏳ 檢查 sandy1990418/xtts-v2-chinese 模型檔案...")
        model_dir = snapshot_download(repo_id="sandy1990418/xtts-v2-chinese")

        # 2. 載入模型權重至顯示卡
        print("⏳ 載入模型權重至顯示卡...")
        config_path = os.path.join(model_dir, "config.json")
        _tts_model = TTS(model_path=model_dir, config_path=config_path).to(device)

        print("✅ 台灣專屬 XTTS 模型載入完成！")

    return _tts_model

def generate_tts(text: str, reference_audio_path: str, language: str = "zh-cn") -> str:
    """
    實作台灣版 XTTS v2 的語音生成邏輯
    """
    if not os.path.exists(reference_audio_path):
        raise FileNotFoundError(f"找不到參考音色檔: {reference_audio_path}")

    tts = _get_tts_model()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    unique_id = uuid.uuid4().hex[:8]
    output_filename = f"tts_{unique_id}.wav"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    print(f"🎙️ 開始生成台灣 AI 旁白... (台詞: {text[:15]}...)")

    tts.tts_to_file(
        text=text,
        speaker_wav=reference_audio_path,
        language=language,
        file_path=output_path
    )

    print(f"✅ AI 旁白生成完畢！已儲存至: {output_path}")

    return str(output_path)
