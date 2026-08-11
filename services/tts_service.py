import os
import uuid
import edge_tts
from core.config import OUTPUT_DIR

async def generate_tts(text: str, voice: str = "zh-TW-HsiaoChenNeural") -> str:
    """
    使用微軟 Edge TTS 生成高音質台灣腔旁白 (免 GPU、無相容性問題)
    可選音色：
    - zh-TW-HsiaoChenNeural (台灣女性，溫柔親切)
    - zh-TW-YunJheNeural (台灣男性，沉穩專業)
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    unique_id = uuid.uuid4().hex[:8]
    output_filename = f"tts_{unique_id}.mp3"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    if len(text) > 150:
        print(f"⚠️ 警告：旁白略長 ({len(text)} 字)，進行自動精簡...")
        cut_text = text[:150]
        if "。" in cut_text:
            text = cut_text.rsplit("。", 1)[0] + "。"
        elif "，" in cut_text:
            text = cut_text.rsplit("，", 1)[0] + "..."
        else:
            text = cut_text + "..."

    print(f"🎙️ 開始生成台灣 AI 旁白 (Edge-TTS)... \n實際唸稿: {text}")

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

    print(f"✅ AI 旁白生成完畢！已儲存至: {output_path}")
    return str(output_path)
