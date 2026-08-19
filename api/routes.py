import os
import uuid
import shutil
import json
import zipfile
import edge_tts
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from core.config import IMAGES_DIR, AUDIO_DIR, BGM_DIR, OUTPUT_DIR
from services.asr_service import transcribe_audio
from services.llm_service import generate_vlog_content_with_template
from services.tts_service import generate_tts
from services.moviepy_service import process_vlog_task
from services.ser_service import analyze_emotion
from services.neo4j_rag_service import search_neo4j_rag
from services.postcard_service import generate_postcard_text, generate_ai_postcard_image

router = APIRouter()

# ----------------------------------------------------
# 暫時性管理端點：上傳 Neo4j dump 檔案
# ----------------------------------------------------
@router.post("/admin/upload_dump")
async def upload_dump_file(file: UploadFile = File(...)):
    target_path = OUTPUT_DIR.parent / file.filename
    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {
        "status": "success",
        "filename": file.filename,
        "saved_path": str(target_path),
        "message": "Dump 檔案上傳成功！請透過 docker cp 將其移入 neo4j-local 容器內進行還原。"
    }

# ----------------------------------------------------
# 新功能：NPC 專屬配音 API（讓 LLM 輸入文字生成活潑語音）
# ----------------------------------------------------
@router.post("/npc/speak")
async def npc_speak_api(
    text: str = Form(..., description="LLM 產生的 NPC 對話文字"),
    voice: str = Form("zh-TW-HsiaoChenNeural", description="語音角色：zh-TW-HsiaoChenNeural (活潑) 或 zh-TW-HsiaoYuNeural (甜美)")
):
    task_id = str(uuid.uuid4())[:8]
    output_filename = f"npc_{task_id}.mp3"
    output_path = OUTPUT_DIR / output_filename

    try:
        os.makedirs(str(OUTPUT_DIR), exist_ok=True)
        communicate = edge_tts.Communicate(text, voice, rate="+10%", pitch="+5Hz")
        await communicate.save(str(output_path))

        if output_path.exists() and output_path.stat().st_size > 0:
            return {
                "status": "success",
                "task_id": task_id,
                "text": text,
                "voice_used": voice,
                "download_url": f"https://vlog.angelalala.com/api/download/{output_filename}"
            }
        else:
            return JSONResponse(status_code=500, content={"message": "語音生成失敗，檔案大小為 0"})

    except Exception as e:
        return JSONResponse(status_code=500, content={"message": f"TTS 發生錯誤: {str(e)}"})

# ----------------------------------------------------
# 新功能：AI 展覽圖錄與彩色風格明信片與 Neo4j 介紹文字生成
# ----------------------------------------------------
@router.post("/postcard/create_ai")
async def create_ai_postcard_api(
    user_image: UploadFile = File(..., description="上傳在地特色照片作為內容參考"),
    spot_name: str = Form(..., description="地點名稱（例如：南投環湖茶園）"),
    user_prompt: str = Form("", description="使用者的額外想法或座標描述"),
    ai_art_prompt: str = Form(
        "A vibrant and warm exhibition catalog style editorial illustration. Warm watercolor palette, soft pastel tones, beautiful natural colors, lush greens and soft blue sky. Artistic poster look, clean edges, no extra text, no watermarks",
        description="預設的 AI 編輯插畫提示詞（彩色溫暖水彩風格）"
    )
):
    """
    結合 Neo4j 在地知識、LLM 導覽文字與 AI 繪圖（彩色溫暖水彩風格）生成文青明信片
    """
    task_id = str(uuid.uuid4())[:8]

    # 1. 儲存使用者上傳的參考照片
    img_extension = os.path.splitext(user_image.filename)[1] or ".jpg"
    raw_img_path = str(IMAGES_DIR / f"postcard_raw_{task_id}{img_extension}")
    with open(raw_img_path, "wb") as buffer:
        shutil.copyfileobj(user_image.file, buffer)

    # 2. 透過 Neo4j 與 LLM 產生在地文化特色介紹文字
    postcard_text = generate_postcard_text(spot_name, user_prompt)

    # 3. 呼叫 AI 圖片生成服務（帶入彩色溫暖風格提示詞）
    final_img_path = await generate_ai_postcard_image(raw_img_path, spot_name, ai_art_prompt)
    final_filename = os.path.basename(final_img_path)

    return {
        "status": "success",
        "task_id": task_id,
        "spot_name": spot_name,
        "ai_prompt_applied": ai_art_prompt,
        "postcard_introduction": postcard_text,
        "download_url": f"https://vlog.angelalala.com/api/download/{final_filename}"
    }

# ----------------------------------------------------
# 下載與檢查端點
# ----------------------------------------------------
@router.get("/check_status/{task_id}")
async def check_status(task_id: str):
    possible_files = [f"vlog_{task_id}.mp4", f"promo_{task_id}.mp4", f"npc_{task_id}.mp3", f"ai_postcard_{task_id}.png"]
    for filename in OUTPUT_DIR.glob(f"*{task_id}*.*"):
        return {"status": "ready", "download_url": f"https://vlog.angelalala.com/api/download/{filename.name}"}
    return {"status": "processing", "message": "檔案生成中或尚未完成"}

@router.get("/download/{filename}")
async def download_video(filename: str):
    file_path = (OUTPUT_DIR / filename).resolve()

    if not file_path.exists():
        task_id = filename.replace("vlog_", "").replace("promo_", "").replace("npc_", "").replace("ai_postcard_", "").replace(".mp4", "").replace(".mp3", "").replace(".jpg", "").replace(".png", "")
        for existing_file in OUTPUT_DIR.glob(f"*{task_id}*.*"):
            file_path = existing_file
            break

    if file_path.exists():
        if file_path.suffix.lower() == '.mp3':
            media_type = 'audio/mp3'
        elif file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
            media_type = 'image/png'
        else:
            media_type = 'video/mp4'
        return FileResponse(file_path, media_type=media_type, filename=file_path.name)

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

    bg_tasks.add_task(
        process_vlog_task,
        task_id,
        full_image_paths,
        script_data["en_video_prompt"],
        tts_path,
        bgm_path,
        filename,
        "user_vlog",
        merchant_name="",
        subtitle_text=script_data["tw_script"]
    )

    return {
        "status": "processing",
        "task_id": task_id,
        "check_url": f"https://vlog.angelalala.com/api/check_status/{task_id}"
    }
