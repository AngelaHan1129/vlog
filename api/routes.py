import os
import uuid
import shutil
import json
import zipfile
import edge_tts

from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from core.config import (
    IMAGES_DIR,
    AUDIO_DIR,
    BGM_DIR,
    OUTPUT_DIR
)

from services.asr_service import transcribe_audio
from services.llm_service import generate_vlog_content_with_template
from services.tts_service import generate_tts
from services.moviepy_service import process_vlog_task
from services.ser_service import analyze_emotion
from services.neo4j_rag_service import search_neo4j_rag, execute_readonly_cypher
from services.postcard_service import (
    generate_postcard_text,
    generate_ai_postcard_image
)
from fastapi import Request, Body
from services.llm_service import generate_story_node, generate_script_blueprint
from services.neo4j_rag_service import search_neo4j_rag, execute_readonly_cypher, fetch_locations_for_script

router = APIRouter()


# ============================================================
# 暫時性管理端點：上傳 Neo4j dump 檔案
# ============================================================
@router.post("/admin/upload_dump")
async def upload_dump_file(file: UploadFile = File(...)):
    try:
        target_path = OUTPUT_DIR.parent / file.filename
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {
            "status": "success",
            "filename": file.filename,
            "saved_path": str(target_path),
            "message": "Dump 檔案上傳成功！請透過 docker cp 將其移入 neo4j-local 容器內進行還原。"
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Dump 檔案上傳失敗：{str(e)}"})


# ============================================================
# Neo4j 唯讀 Cypher 查詢 API (供前端/外部探索資料)
# ============================================================
class CypherQueryRequest(BaseModel):
    query: str
    parameters: Optional[Dict[str, Any]] = {}

@router.post("/neo4j/cypher")
async def execute_raw_cypher(req: CypherQueryRequest):
    """
    接收前端傳來的 Cypher 語法並回傳查詢結果。
    ⚠️ 具備安全限制：僅允許執行 MATCH 查詢，嚴禁修改語法。
    """
    try:
        records = execute_readonly_cypher(req.query, req.parameters)
        return {"status": "success", "count": len(records), "data": records}
    except ValueError as ve:
        return JSONResponse(status_code=403, content={"status": "error", "message": str(ve)})
    except ConnectionError as ce:
        return JSONResponse(status_code=503, content={"status": "error", "message": str(ce)})
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "message": str(e)})


# ============================================================
# NPC 專屬配音 API
# ============================================================
@router.post("/npc/speak")
async def npc_speak_api(
    text: str = Form(..., description="LLM 產生的 NPC 對話文字"),
    voice: str = Form("zh-TW-HsiaoChenNeural", description="語音角色：zh-TW-HsiaoChenNeural（活潑）或 zh-TW-HsiaoYuNeural（甜美）")
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
        return JSONResponse(status_code=500, content={"status": "error", "message": "語音生成失敗，檔案大小為 0"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"TTS 發生錯誤：{str(e)}"})


# ============================================================
# AI 展覽圖錄風格明信片
# ============================================================
@router.post("/postcard/create_ai")
async def create_ai_postcard_api(
    user_image: UploadFile = File(..., description="上傳景點照片"),
    spot_name: str = Form(..., description="地點名稱"),
    user_prompt: str = Form("", description="額外描述")
):
    task_id = str(uuid.uuid4())[:8]
    try:
        os.makedirs(str(IMAGES_DIR), exist_ok=True)
        raw_img_path = str(IMAGES_DIR / f"postcard_raw_{task_id}.jpg")
        with open(raw_img_path, "wb") as buffer:
            shutil.copyfileobj(user_image.file, buffer)
        
        postcard_text = generate_postcard_text(spot_name, user_prompt)
        print(f"🎨 [POSTCARD] 開始生成雜誌風明信片：{task_id}")
        
        final_img_path = await generate_ai_postcard_image(raw_img_path, spot_name, user_prompt, task_id)
        return {
            "status": "success",
            "task_id": task_id,
            "postcard_introduction": postcard_text,
            "download_url": f"https://vlog.angelalala.com/api/download/ai_postcard_{task_id}.png"
        }
    except Exception as e:
        print(f"❌ AI 明信片生成失敗：{e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


# ============================================================
# 檔案狀態檢查
# ============================================================
@router.get("/check_status/{task_id}")
async def check_status(task_id: str):
    try:
        possible_prefixes = [
            f"vlog_{task_id}", f"promo_{task_id}", f"npc_{task_id}", 
            f"ai_postcard_{task_id}", f"metadata_{task_id}"
        ]
        for file_path in OUTPUT_DIR.glob("*"):
            if not file_path.is_file(): continue
            filename = file_path.name
            if any(filename.startswith(prefix) for prefix in possible_prefixes):
                # 如果是影片/圖片/音檔則當作主要回傳對象
                if not filename.startswith("metadata_"):
                    return {
                        "status": "ready",
                        "task_id": task_id,
                        "filename": filename,
                        "download_url": f"https://vlog.angelalala.com/api/download/{filename}",
                        "metadata_url": f"https://vlog.angelalala.com/api/download/metadata_{task_id}.json"
                    }
        return {"status": "processing", "task_id": task_id, "message": "檔案生成中或尚未完成"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "task_id": task_id, "message": f"檢查狀態失敗：{str(e)}"})


# ============================================================
# 檔案下載
# ============================================================
@router.get("/download/{filename}")
async def download_file(filename: str):
    try:
        safe_filename = os.path.basename(filename)
        file_path = (OUTPUT_DIR / safe_filename).resolve()
        output_dir_resolved = OUTPUT_DIR.resolve()

        if output_dir_resolved not in file_path.parents:
            return JSONResponse(status_code=400, content={"message": "無效的檔案路徑"})

        if not file_path.exists():
            task_id = (safe_filename
                .replace("vlog_", "").replace("promo_", "")
                .replace("npc_", "").replace("ai_postcard_", "").replace("metadata_", "")
                .replace(".mp4", "").replace(".mp3", "")
                .replace(".jpg", "").replace(".jpeg", "").replace(".png", "").replace(".webp", "")
                .replace(".json", "")
            )
            for existing_file in OUTPUT_DIR.glob(f"*{task_id}*.*"):
                if existing_file.is_file() and existing_file.suffix == file_path.suffix:
                    file_path = existing_file.resolve()
                    break

        if not file_path.exists():
            return JSONResponse(status_code=404, content={"message": "找不到檔案，請確認任務是否已完成"})

        suffix = file_path.suffix.lower()
        if suffix == ".mp3": media_type = "audio/mpeg"
        elif suffix in [".jpg", ".jpeg"]: media_type = "image/jpeg"
        elif suffix == ".png": media_type = "image/png"
        elif suffix == ".webp": media_type = "image/webp"
        elif suffix == ".mp4": media_type = "video/mp4"
        elif suffix == ".json": media_type = "application/json"
        else: media_type = "application/octet-stream"

        return FileResponse(path=file_path, media_type=media_type, filename=file_path.name)
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": f"檔案下載失敗：{str(e)}"})


# ============================================================
# 共用函式：處理上傳與 FFmpeg
# ============================================================
def process_uploads(task_id, user_audio, image_zip, bgm_file):
    os.makedirs(str(IMAGES_DIR), exist_ok=True)
    os.makedirs(str(AUDIO_DIR), exist_ok=True)
    os.makedirs(str(BGM_DIR), exist_ok=True)
    
    # 儲存與轉檔語音
    audio_ext = os.path.splitext(user_audio.filename or ".wav")[1] or ".wav"
    raw_audio_path = str(AUDIO_DIR / f"raw_{task_id}{audio_ext}")
    clean_audio_path = str(AUDIO_DIR / f"upload_{task_id}.wav")
    
    with open(raw_audio_path, "wb") as buffer:
        shutil.copyfileobj(user_audio.file, buffer)
    os.system(f'ffmpeg -y -i "{raw_audio_path}" -ar 16000 -ac 1 "{clean_audio_path}" > /dev/null 2>&1')

    # 解壓縮圖片
    zip_temp_path = str(IMAGES_DIR / f"{task_id}_images.zip")
    extract_to = str(IMAGES_DIR / f"{task_id}_extracted")
    with open(zip_temp_path, "wb") as buffer:
        shutil.copyfileobj(image_zip.file, buffer)
    
    os.makedirs(extract_to, exist_ok=True)
    with zipfile.ZipFile(zip_temp_path, "r") as zip_ref:
        zip_ref.extractall(extract_to)
        
    full_image_paths = []
    for root, dirs, files in os.walk(extract_to):
        for file in files:
            if file.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                full_image_paths.append(os.path.join(root, file))

    # 儲存 BGM
    bgm_filename = bgm_file.filename or f"bgm_{task_id}.mp3"
    bgm_path = str(BGM_DIR / f"{task_id}_{bgm_filename}")
    with open(bgm_path, "wb") as buffer:
        shutil.copyfileobj(bgm_file.file, buffer)

    return clean_audio_path, full_image_paths, bgm_path


# ============================================================
# 模式一：遊客端 - 生活記錄與遊戲任務 Vlog
# ============================================================
@router.post("/visitor/create_vlog")
async def visitor_vlog_api(
    bg_tasks: BackgroundTasks,
    user_audio: UploadFile = File(..., description="上傳語音檔 (mp3/m4a/wav)"),
    image_zip: UploadFile = File(..., description="上傳包含多張照片的 ZIP 壓縮檔"),
    bgm_file: UploadFile = File(..., description="上傳背景音樂檔 (mp3)"),
    spot_list: str = Form('["南投環湖茶園"]', description="景點清單 (JSON或逗號分隔)"),
    play_time: str = Form("", description="遊玩時長 (例如: 2.5小時)"),
    game_tasks: str = Form("", description="解鎖任務 (例如: 收集三顆茶葉寶石)")
):
    task_id = str(uuid.uuid4())[:8]
    filename = f"vlog_{task_id}.mp4"

    try:
        clean_audio_path, full_image_paths, bgm_path = process_uploads(task_id, user_audio, image_zip, bgm_file)
        raw_text = transcribe_audio(clean_audio_path)
        emotion = analyze_emotion(clean_audio_path)

        # 解析景點清單並執行 Neo4j RAG
        try:
            spots = json.loads(spot_list)
            if not isinstance(spots, list): spots = [str(spots)]
        except:
            spots = [s.strip() for s in spot_list.split(",") if s.strip()]

        rag_context = "\n".join([search_neo4j_rag(spot) for spot in spots])

        # LLM 腳本生成 (含行銷/關鍵字客群分析回傳)
        script_data = generate_vlog_content_with_template(
            raw_text=raw_text,
            emotion=emotion,
            template="user_vlog",
            rag_context=rag_context,
            play_time=play_time,
            game_tasks=game_tasks
        )

        # 儲存客群分析 Metadata 供 .NET 端拉取
        os.makedirs(str(OUTPUT_DIR), exist_ok=True)
        metadata_path = OUTPUT_DIR / f"metadata_{task_id}.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump({
                "vlog_type": "visitor",
                "seo_keywords": script_data.get("seo_keywords", []),
                "target_audience": script_data.get("target_audience", []),
                "promo_copy": script_data.get("promo_copy", "")
            }, f, ensure_ascii=False, indent=2)

        tts_path = await generate_tts(script_data["tw_script"])

        # 啟動背景生成排程
        bg_tasks.add_task(
            process_vlog_task,
            task_id, full_image_paths, script_data["en_video_prompt"],
            tts_path, bgm_path, filename, "user_vlog",
            merchant_name="", subtitle_text=script_data["tw_script"]
        )

        return {
            "status": "processing",
            "task_id": task_id,
            "check_url": f"https://vlog.angelalala.com/api/check_status/{task_id}",
            "metadata_url": f"https://vlog.angelalala.com/api/download/metadata_{task_id}.json"
        }
    except Exception as e:
        print(f"❌ [VLOG] 遊客 Vlog 建立失敗：{e}")
        return JSONResponse(status_code=500, content={"status": "error", "task_id": task_id, "message": str(e)})


# ============================================================
# 模式二：商家端 - 在地推廣 Vlog
# ============================================================
@router.post("/merchant/create_vlog")
async def merchant_vlog_api(
    bg_tasks: BackgroundTasks,
    user_audio: UploadFile = File(..., description="商家配音或口白 (mp3/m4a/wav)"),
    image_zip: UploadFile = File(..., description="主打商品/環境照片 ZIP"),
    bgm_file: UploadFile = File(..., description="背景音樂檔 (mp3)"),
    merchant_name: str = Form(..., description="商家或餐廳名稱"),
    promo_info: str = Form(..., description="優惠活動或主打商品描述")
):
    task_id = str(uuid.uuid4())[:8]
    filename = f"promo_{task_id}.mp4"

    try:
        clean_audio_path, full_image_paths, bgm_path = process_uploads(task_id, user_audio, image_zip, bgm_file)
        raw_text = transcribe_audio(clean_audio_path)
        emotion = analyze_emotion(clean_audio_path)

        # 從 Neo4j 撈取商家資訊與周邊脈絡
        rag_context = search_neo4j_rag(merchant_name)

        # LLM 腳本生成 (針對商家行銷優化)
        script_data = generate_vlog_content_with_template(
            raw_text=raw_text,
            emotion=emotion,
            template="merchant_promo",
            rag_context=rag_context,
            promo_info=promo_info
        )

        # 儲存客群分析 Metadata 供 .NET 端拉取
        os.makedirs(str(OUTPUT_DIR), exist_ok=True)
        metadata_path = OUTPUT_DIR / f"metadata_{task_id}.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump({
                "vlog_type": "merchant",
                "seo_keywords": script_data.get("seo_keywords", []),
                "target_audience": script_data.get("target_audience", []),
                "promo_copy": script_data.get("promo_copy", "")
            }, f, ensure_ascii=False, indent=2)

        tts_path = await generate_tts(script_data["tw_script"])

        # 啟動背景生成排程
        bg_tasks.add_task(
            process_vlog_task,
            task_id, full_image_paths, script_data["en_video_prompt"],
            tts_path, bgm_path, filename, "merchant_promo",
            merchant_name=merchant_name, subtitle_text=script_data["tw_script"]
        )

        return {
            "status": "processing",
            "task_id": task_id,
            "check_url": f"https://vlog.angelalala.com/api/check_status/{task_id}",
            "metadata_url": f"https://vlog.angelalala.com/api/download/metadata_{task_id}.json"
        }
    except Exception as e:
        print(f"❌ [VLOG] 商家 Vlog 建立失敗：{e}")
        return JSONResponse(status_code=500, content={"status": "error", "task_id": task_id, "message": str(e)})


# ============================================================
# 動態遊戲推演 API (供前端/App遊玩時呼叫)
# ============================================================
@router.post("/v1/generate")
async def generate_game_story(
    payload: dict = Body(..., description="請貼上符合 Input Schema 的 JSON Payload")
):
    """
    接收後端打來的 JSON Payload，依據 node_type 分流處理。
    由 LLM Service 進行 Pydantic 驗證、3 次重試機制與 Fallback 處理。
    """
    try:
        result_dict = generate_story_node(payload)
        return JSONResponse(status_code=200, content=result_dict)
    except ValueError as ve:
        return JSONResponse(status_code=400, content={"status": "error", "message": str(ve)})
    except Exception as e:
        print(f"❌ /v1/generate 發生未預期錯誤：{e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# ============================================================
# 後台工具：AI 一鍵生成實境解謎劇本藍圖 API
# ============================================================
class ScriptGenRequest(BaseModel):
    town_name: str     # 例如: "北投區", "安平區"
    theme: str         # 例如: "百年溫泉的秘密", "荷蘭時期的尋寶"
    node_count: int = 4 # 預設 4 個節點 (起承轉合)

@router.post("/admin/generate_script_blueprint")
async def api_generate_script_blueprint(req: ScriptGenRequest):
    """
    【企劃後台專用】
    給定鄉鎮區與主題，系統會透過 Neo4j (RAG) 撈出真實景點，
    並由 Llama 3 套用 13 種任務模型，生成帶有「起、承、轉、合」的結構化 JSON 劇本。
    """
    try:
        # 1. 從 Neo4j 撈出真實景點 (RAG 錨點)
        locations = fetch_locations_for_script(req.town_name, limit=req.node_count)
        
        if len(locations) < req.node_count:
            return JSONResponse(
                status_code=400, 
                content={"message": f"Neo4j 中 {req.town_name} 的可用景點數量不足 {req.node_count} 個。"}
            )

        # 2. 丟給 LLM 進行劇本創作
        script_blueprint = generate_script_blueprint(
            theme=req.theme,
            town_name=req.town_name,
            locations=locations
        )

        return {"status": "success", "data": script_blueprint}
        
    except Exception as e:
        print(f"❌ 劇本藍圖生成失敗：{e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
