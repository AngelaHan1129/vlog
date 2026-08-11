import os
import torch
import uuid
from huggingface_hub import snapshot_download

# ==========================================
# 🪄 補丁一：PyTorch 2.6+ 魔法小補丁 (解除安全限制)
# ==========================================
_original_load = torch.load
def _legacy_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return _original_load(*args, **kwargs)
torch.load = _legacy_load

# ==========================================
# 🪄 補丁二：Transformers 終極幻術小補丁 (解決 import 報錯)
# ==========================================
import transformers
import transformers.generation.utils

class DummyComponent: 
    pass

_missing_root = ["BeamSearchScorer", "ConstrainedBeamSearchScorer", "DisjunctiveConstraint", "PhrasalConstraint"]
for comp in _missing_root:
    if not hasattr(transformers, comp):
        setattr(transformers, comp, DummyComponent)

_missing_utils = ["SampleOutput", "GenerateOutput"]
for comp in _missing_utils:
    if not hasattr(transformers.generation.utils, comp):
        setattr(transformers.generation.utils, comp, DummyComponent)

# ⚠️ 必須先套用補丁二，才能安全載入 TTS
from TTS.api import TTS

# ==========================================
# 🪄 補丁三：血統融合補丁 (解決執行時缺少 generate 及所有附屬函數報錯)
# 最新版 Transformers 徹底把 GenerationMixin 從底層抽離
# 我們利用 Python 的動態特性，直接把 GenerationMixin 塞進 XTTS 的父類別陣列中！
# ==========================================
from transformers.generation import GenerationMixin
from TTS.tts.layers.xtts.gpt import GPT2InferenceModel

# 強制多重繼承：讓 GPT2InferenceModel 瞬間找回所有生成技能
if GenerationMixin not in GPT2InferenceModel.__bases__:
    GPT2InferenceModel.__bases__ = (GenerationMixin,) + GPT2InferenceModel.__bases__
# ==========================================

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

def generate_tts(text: str, reference_audio_path: str, language: str = "zh") -> str:
    """
    實作台灣版 XTTS v2 的語音生成邏輯
    """
    if not os.path.exists(reference_audio_path):
        raise FileNotFoundError(f"找不到參考音色檔: {reference_audio_path}")

    # ==========================================
    # 🛡️ 終極安全機制：防止文本過長導致 XTTS 崩潰
    # XTTS 有 400 tokens 的極限。我們強制將腳本限制在 80 個中文字以內。
    # 這長度剛好非常適合一段 15~20 秒的 Vlog 短影音！
    # ==========================================
    if len(text) > 80:
        print(f"⚠️ 警告：AI 生成的旁白太長 ({len(text)} 字)，為防止 TTS 崩潰，啟動自動精簡...")
        # 找最後一個句號或逗號來截斷，讓語句聽起來比較自然
        cut_text = text[:80]
        if "。" in cut_text:
            text = cut_text.rsplit("。", 1)[0] + "。"
        elif "，" in cut_text:
            text = cut_text.rsplit("，", 1)[0] + "..."
        else:
            text = cut_text + "..."

    tts = _get_tts_model()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    unique_id = uuid.uuid4().hex[:8]
    output_filename = f"tts_{unique_id}.wav"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    print(f"🎙️ 開始生成台灣 AI 旁白... (實際唸稿: {text})")

    tts.tts_to_file(
        text=text,
        speaker_wav=reference_audio_path,
        language=language,
        file_path=output_path
    )

    print(f"✅ AI 旁白生成完畢！已儲存至: {output_path}")

    return str(output_path)
