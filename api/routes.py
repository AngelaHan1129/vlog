import os
import uuid
import shutil
import json
import zipfile
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from core.config import IMAGES_DIR, AUDIO_DIR, BGM_DIR, OUTPUT_DIR
from services.asr_service import transcribe_audio
from services.llm_service import generate_vlog_content_with_template
from services.tts_service import generate_tts
from services.moviepy_service import process_vlog_task
from services.ser_service import analyze_emotion
from services.neo4j_rag_service import search_neo4j_rag

router = APIRouter()

# ----------------------------------------------------
# 下載與檢查端點
# ----------------------------------------------------
@router.get("/check_status/{task_id}")
async def check_status(task_id: str):
    # 檢查 Vlog 或 Promo 檔案是否存在
    possible_files = [f"vlog_{task_id}.mp4", f"promo_{task_id}.mp4"]
    for filename in possible_files:
        if (OUTPUT_DIR / filename).exists():
            return {"status": "ready", "download_url": f"https://vlog.angelalala.com/api/download/{filename}"}
    return {"status": "processing", "message": "影片生成中或尚未完成"}

@router.get("/download/{filename}")
async def download_video(filename: str):
    file_path = (OUTPUT_DIR / filename).resolve()
    
    # 如果精準檔名不存在，透過 task_id 進行模糊搜尋以防檔名對不上
    if not file_path.exists():
        task_id = filename.replace("vlog_", "").replace("promo_", "").replace(".mp4", "")
        for existing_file in OUTPUT_DIR.glob(f"*{task_id}*.mp4"):
            file_path = existing_file
            break

    if file_path.exists():
        return FileResponse(file_path, media_type='video/mp4', filename=file_path.name)
    
    return JSONResponse(status_code=404, content={"message": "找不到檔案，請確認任務是否已完成"})
# ----------------------------------------------------
# 模式一：遊客端 - 生活記錄 Vlog
# ----------------------------------------------------
@router.post("/visitor/create_vlog")
async def visitor_vlog_api(
    bg_tasks: BackgroundTasks,
    user_audio: UploadFile = File(..., description="上傳語音檔 (mp3/m4a/wav)"),
    image_zip: UploadFile = File(..., description="上傳包含多張照片的 ZIP 壓縮檔"),
    bgm_file: UploadFile = File(..., description="上傳背景音樂檔 (mp3)"),
    spot_list: str = Form('["南投環湖茶園", "竹林秘境"]', description="景點清單 (JSON格式或逗號分隔)")
):
    task_id = str(uuid.uuid4())[:8]
    filename = f"vlog_{task_id}.mp4"

    # 處理音訊
    raw_audio_path = str(AUDIO_DIR / f"raw_{task_id}{os.path.splitext(user_audio.filename)[1]}")
    clean_audio_path = str(AUDIO_DIR / f"upload_{task_id}.wav")
    with open(raw_audio_path, "wb") as buffer:
        shutil.copyfileobj(user_audio.file, buffer)
    os.system(f"ffmpeg -y -i {raw_audio_path} -ar 16000 -ac 1 {clean_audio_path} > /dev/null 2>&1")

    # 解壓縮圖片
    full_image_paths = []
    zip_temp_path = str(IMAGES_DIR / f"{task_id}_images.zip")
    with open(zip_temp_path, "wb") as buffer:
        shutil.copyfileobj(image_zip.file, buffer)
    extract_to = IMAGES_DIR / f"{task_id}_extracted"
    os.makedirs(extract_to, exist_ok=True)
    with zipfile.ZipFile(zip_temp_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    for root, dirs, files in os.walk(extract_to):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                full_image_paths.append(os.path.join(root, file))

    # 儲存 BGM
    bgm_path = str(BGM_DIR / f"{task_id}_{bgm_file.filename}")
    with open(bgm_path, "wb") as buffer:
        shutil.copyfileobj(bgm_file.file, buffer)

    # 執行任務
    raw_text = transcribe_audio(clean_audio_path)
    emotion = analyze_emotion(clean_audio_path)
    try:
        spots = json.loads(spot_list)
        if not isinstance(spots, list): spots = [str(spots)]
    except:
        spots = [s.strip() for s in spot_list.split(",") if s.strip()]
    rag_context = "\n".join([search_neo4j_rag(spot) for spot in spots])
    script_data = generate_vlog_content_with_template(raw_text, emotion, "user_vlog", rag_context)
    tts_path = await generate_tts(script_data["tw_script"])

    bg_tasks.add_task(process_vlog_task, task_id, full_image_paths, script_data["en_video_prompt"], tts_path, bgm_path, filename, "user_vlog")
    
    return {"status": "processing", "task_id": task_id, "check_url": f"https://vlog.angelalala.com/api/check_status/{task_id}"}
