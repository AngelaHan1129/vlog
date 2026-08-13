import os
import uuid
import shutil
import json
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form
from core.config import IMAGES_DIR, AUDIO_DIR, BGM_DIR, TEMPLATES
from services.asr_service import transcribe_audio
from services.llm_service import generate_vlog_content_with_template
from services.tts_service import generate_tts
from services.moviepy_service import process_vlog_task
from services.ser_service import analyze_emotion
from services.neo4j_rag_service import search_neo4j_rag

router = APIRouter()

# ----------------------------------------------------
# 模式一：遊客端 - 生活記錄 Vlog
# ----------------------------------------------------
@router.post("/visitor/create_vlog")
async def visitor_vlog_api(
    bg_tasks: BackgroundTasks,
    user_audio: UploadFile = File(...),
    image_files: str = Form("[]"),
    spot_list: str = Form("[]"), # 支援多個景點 ["景點A", "景點B"]
    bgm_file: str = Form("default_bgm.mp3")
):
    task_id = str(uuid.uuid4())[:8]
    temp_path = str(AUDIO_DIR / f"upload_{task_id}.mp3")
    with open(temp_path, "wb") as buffer: shutil.copyfileobj(user_audio.file, buffer)
    
    raw_text = transcribe_audio(temp_path)
    emotion = analyze_emotion(temp_path)
    
    # 批次 RAG 檢索
    spots = json.loads(spot_list)
    rag_context = "\n".join([search_neo4j_rag(spot) for spot in spots])
    
    script_data = generate_vlog_content_with_template(raw_text, emotion, "user_vlog", rag_context)
    tts_path = await generate_tts(script_data["tw_script"])

    bg_tasks.add_task(
        process_vlog_task, task_id, json.loads(image_files), script_data["en_video_prompt"], 
        tts_path, str(BGM_DIR / bgm_file), f"vlog_{task_id}.mp4", "user_vlog"
    )
    return {"status": "processing", "task_id": task_id, "message": "生活記錄 Vlog 生成中"}

# ----------------------------------------------------
# 模式二：商家端 - 行銷宣傳 Promo
# ----------------------------------------------------
@router.post("/merchant/create_promo")
async def merchant_promo_api(
    bg_tasks: BackgroundTasks,
    merchant_name: str = Form(...),
    promo_text: str = Form(...),
    image_files: str = Form("[]"),
    bgm_file: str = Form("promo_bgm.mp3")
):
    task_id = str(uuid.uuid4())[:8]
    
    # 直接使用商家文案
    script_data = generate_vlog_content_with_template(promo_text, "專業熱情", "merchant_promo", "")
    tts_path = await generate_tts(script_data["tw_script"])

    bg_tasks.add_task(
        process_vlog_task, task_id, json.loads(image_files), script_data["en_video_prompt"], 
        tts_path, str(BGM_DIR / bgm_file), f"promo_{task_id}.mp4", "merchant_promo", merchant_name
    )
    return {"status": "processing", "task_id": task_id, "message": "商家宣傳影片生成中"}
