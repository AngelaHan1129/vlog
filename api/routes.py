import os
import uuid
import shutil
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
from core.config import IMAGES_DIR, AUDIO_DIR, BGM_DIR

# 引入我們的五大模組 (加入了 SER 情感分析)
from services.asr_service import transcribe_audio
from services.llm_service import generate_vlog_content
from services.tts_service import generate_tts
from services.moviepy_service import process_vlog_task
from services.ser_service import analyze_emotion

router = APIRouter()

# ----------------------------------------------------
# 模式一：原本的手動 JSON 觸發 (保留原本的彈性)
# ----------------------------------------------------
class VlogRequest(BaseModel):
    image_files: list[str]
    prompt: str             # AI 提示詞
    tts_audio_file: str
    bgm_file: str

@router.post("/create_vlog")
async def create_vlog_api(request: VlogRequest, bg_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())[:8]
    output_filename = f"vlog_{task_id}.mp4"

    full_image_paths = [str(IMAGES_DIR / img) for img in request.image_files]
    full_tts_path = str(AUDIO_DIR / request.tts_audio_file)
    full_bgm_path = str(BGM_DIR / request.bgm_file)

    bg_tasks.add_task(
        process_vlog_task,
        task_id=task_id,
        image_files=full_image_paths,
        prompt=request.prompt,
        tts_audio_file=full_tts_path,
        bgm_file=full_bgm_path,
        output_file=output_filename
    )

    return {
        "status": "processing",
        "task_id": task_id,
        "message": "已將生成任務加入排程，影片正在背景生成中...",
        "expected_output": output_filename
    }


# ----------------------------------------------------
# 🆕 模式二：全自動語音一條龍 (ASR -> SER -> LLM -> TTS -> Video)
# ----------------------------------------------------
@router.post("/create_vlog_from_audio")
async def create_vlog_from_audio_api(
    bg_tasks: BackgroundTasks,
    user_audio: UploadFile = File(...),              # 使用者上傳的手機錄音檔
    image_files: str = Form("[]"),                   # 選擇性傳入的基礎圖片列表 (JSON 字串)
    bgm_file: str = Form("default_bgm.mp3")          # 背景音樂檔名
):
    task_id = str(uuid.uuid4())[:8]
    output_filename = f"vlog_{task_id}.mp4"

    # 1. 暫存使用者上傳的語音檔
    os.makedirs(AUDIO_DIR, exist_ok=True)
    temp_user_audio_path = str(AUDIO_DIR / f"upload_{task_id}_{user_audio.filename}")
    with open(temp_user_audio_path, "wb") as buffer:
        shutil.copyfileobj(user_audio.file, buffer)

    # 2. 👂 ASR 聽語音 (轉文字)
    print(f"[{task_id}] 👂 啟動 ASR 聽取語音...")
    raw_text = transcribe_audio(temp_user_audio_path)

    # 2.5 💓 SER 情感分析 (聽出情緒)
    print(f"[{task_id}] 💓 啟動 SER 情感分析...")
    detected_emotion = analyze_emotion(temp_user_audio_path)

    # 3. 🧠 LLM 大腦改寫 (生成繁體旁白 + 英文 Prompt，並融入情緒)
    print(f"[{task_id}] 🧠 啟動 LLM 撰寫 Vlog 腳本 (情緒設定：{detected_emotion})...")
    script_data = generate_vlog_content(raw_text, user_emotion=detected_emotion)
    tw_script = script_data.get("tw_script", "歡迎來到南投的美麗茶園。")
    en_prompt = script_data.get("en_video_prompt", "beautiful tea garden in Nantou, Taiwan")

    # 4. 🗣️ TTS 台灣語音生成 (使用極速、高音質的 Edge-TTS)
    print(f"[{task_id}] 🗣️ 啟動 TTS 生成台灣口音配音...")
    
    # 記得加上 await，並傳入從 LLM 拿到的 tw_script
    generated_tts_path = await generate_tts(text=tw_script, voice="zh-TW-HsiaoChenNeural")

    # 5. 🎬 準備背景任務 (將合成工作丟給 MoviePy/LTX-Video)
    full_bgm_path = str(BGM_DIR / bgm_file)
    import json
    try:
        parsed_images = json.loads(image_files)
        full_image_paths = [str(IMAGES_DIR / img) for img in parsed_images]
    except Exception:
        full_image_paths = []

    print(f"[{task_id}] 🚀 將 AI 合成任務派發至背景執行...")
    bg_tasks.add_task(
        process_vlog_task,
        task_id=task_id,
        image_files=full_image_paths,
        prompt=en_prompt,               # LLM 自動產出的英文 Prompt
        tts_audio_file=generated_tts_path, # 剛產出的台灣腔音檔
        bgm_file=full_bgm_path,
        output_file=output_filename
    )

    # 6. 迅速回應前端，包含大腦思考出來的優美台詞與偵測到的情緒
    return {
        "status": "processing",
        "task_id": task_id,
        "ai_result": {
            "transcribed_raw": raw_text,
            "detected_emotion": detected_emotion,  # 回傳情緒給前端展示
            "tw_script": tw_script,
            "en_prompt": en_prompt
        },
        "message": f"AI 已感受到你的【{detected_emotion}】，Vlog 影片正在背景全力繪製中！",
        "expected_output": output_filename
    }
