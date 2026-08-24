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

# 💡 修改這裡：引入重構後的 execute_readonly_cypher
from services.neo4j_rag_service import search_neo4j_rag, execute_readonly_cypher

from services.postcard_service import (
    generate_postcard_text,
    generate_ai_postcard_image
)


router = APIRouter()


# ============================================================
# 暫時性管理端點：上傳 Neo4j dump 檔案
# ============================================================

@router.post("/admin/upload_dump")
async def upload_dump_file(
    file: UploadFile = File(...)
):
    try:
        target_path = OUTPUT_DIR.parent / file.filename

        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "status": "success",
            "filename": file.filename,
            "saved_path": str(target_path),
            "message": (
                "Dump 檔案上傳成功！"
                "請透過 docker cp 將其移入 neo4j-local 容器內進行還原。"
            )
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Dump 檔案上傳失敗：{str(e)}"
            }
        )


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
        # 將複雜的邏輯全部交給 Service 層處理
        records = execute_readonly_cypher(req.query, req.parameters)
        
        return {
            "status": "success",
            "count": len(records),
            "data": records
        }

    except ValueError as ve:
        # 捕捉 Service 丟出的安全警告 (403 Forbidden)
        return JSONResponse(status_code=403, content={"status": "error", "message": str(ve)})
        
    except ConnectionError as ce:
        # 捕捉 Service 丟出的連線失敗 (503 Service Unavailable)
        return JSONResponse(status_code=503, content={"status": "error", "message": str(ce)})
        
    except Exception as e:
        # 捕捉 Cypher 語法錯誤或其他未預期錯誤 (400 Bad Request)
        return JSONResponse(status_code=400, content={"status": "error", "message": str(e)})


# ============================================================
# NPC 專屬配音 API
# ============================================================

@router.post("/npc/speak")
async def npc_speak_api(
    text: str = Form(
        ...,
        description="LLM 產生的 NPC 對話文字"
    ),
    voice: str = Form(
        "zh-TW-HsiaoChenNeural",
        description=(
            "語音角色："
            "zh-TW-HsiaoChenNeural（活潑）"
            "或 zh-TW-HsiaoYuNeural（甜美）"
        )
    )
):
    task_id = str(uuid.uuid4())[:8]
    output_filename = f"npc_{task_id}.mp3"
    output_path = OUTPUT_DIR / output_filename

    try:
        os.makedirs(str(OUTPUT_DIR), exist_ok=True)

        communicate = edge_tts.Communicate(
            text,
            voice,
            rate="+10%",
            pitch="+5Hz"
        )

        await communicate.save(str(output_path))

        if output_path.exists() and output_path.stat().st_size > 0:
            return {
                "status": "success",
                "task_id": task_id,
                "text": text,
                "voice_used": voice,
                "download_url": (
                    f"https://vlog.angelalala.com/"
                    f"api/download/{output_filename}"
                )
            }

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "語音生成失敗，檔案大小為 0"
            }
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"TTS 發生錯誤：{str(e)}"
            }
        )


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
        # 1. 儲存原始圖片 (供後續顯示或參考)
        os.makedirs(str(IMAGES_DIR), exist_ok=True)
        raw_img_path = str(IMAGES_DIR / f"postcard_raw_{task_id}.jpg")
        with open(raw_img_path, "wb") as buffer:
            shutil.copyfileobj(user_image.file, buffer)

        # 2. 產生介紹文字
        postcard_text = generate_postcard_text(spot_name, user_prompt)

        print(f"🎨 [POSTCARD] 開始生成雜誌風明信片：{task_id}")

        # 3. 呼叫 ComfyUI 服務（內部自動套用雜誌風空間結構萃取與留白美學）
        final_img_path = await generate_ai_postcard_image(
            raw_img_path,
            spot_name,
            user_prompt,
            task_id
        )

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
            f"vlog_{task_id}",
            f"promo_{task_id}",
            f"npc_{task_id}",
            f"ai_postcard_{task_id}"
        ]

        for file_path in OUTPUT_DIR.glob("*"):

            if not file_path.is_file():
                continue

            filename = file_path.name

            if any(
                filename.startswith(prefix)
                for prefix in possible_prefixes
            ):
                return {
                    "status": "ready",
                    "task_id": task_id,
                    "filename": filename,
                    "download_url": (
                        f"https://vlog.angelalala.com/"
                        f"api/download/{filename}"
                    )
                }

        return {
            "status": "processing",
            "task_id": task_id,
            "message": "檔案生成中或尚未完成"
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "task_id": task_id,
                "message": f"檢查狀態失敗：{str(e)}"
            }
        )


# ============================================================
# 檔案下載
# ============================================================

@router.get("/download/{filename}")
async def download_file(filename: str):

    try:
        safe_filename = os.path.basename(filename)

        file_path = (
            OUTPUT_DIR /
            safe_filename
        ).resolve()

        output_dir_resolved = (
            OUTPUT_DIR.resolve()
        )

        # 防止 Path Traversal
        if output_dir_resolved not in file_path.parents:
            return JSONResponse(
                status_code=400,
                content={
                    "message": "無效的檔案路徑"
                }
            )

        # ----------------------------------------------------
        # 找不到時，嘗試使用 task_id 搜尋
        # ----------------------------------------------------

        if not file_path.exists():

            task_id = (
                safe_filename
                .replace("vlog_", "")
                .replace("promo_", "")
                .replace("npc_", "")
                .replace("ai_postcard_", "")
                .replace(".mp4", "")
                .replace(".mp3", "")
                .replace(".jpg", "")
                .replace(".jpeg", "")
                .replace(".png", "")
                .replace(".webp", "")
            )

            for existing_file in OUTPUT_DIR.glob(
                f"*{task_id}*.*"
            ):
                if existing_file.is_file():
                    file_path = existing_file.resolve()
                    break

        # ----------------------------------------------------
        # 檔案不存在
        # ----------------------------------------------------

        if not file_path.exists():
            return JSONResponse(
                status_code=404,
                content={
                    "message": (
                        "找不到檔案，"
                        "請確認任務是否已完成"
                    )
                }
            )

        # ----------------------------------------------------
        # MIME Type
        # ----------------------------------------------------

        suffix = file_path.suffix.lower()

        if suffix == ".mp3":
            media_type = "audio/mpeg"

        elif suffix in [".jpg", ".jpeg"]:
            media_type = "image/jpeg"

        elif suffix == ".png":
            media_type = "image/png"

        elif suffix == ".webp":
            media_type = "image/webp"

        elif suffix == ".mp4":
            media_type = "video/mp4"

        else:
            media_type = "application/octet-stream"

        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=file_path.name
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "message": f"檔案下載失敗：{str(e)}"
            }
        )


# ============================================================
# 模式一：遊客端 - 生活記錄 Vlog
# ============================================================

@router.post("/visitor/create_vlog")
async def visitor_vlog_api(
    bg_tasks: BackgroundTasks,

    user_audio: UploadFile = File(
        ...,
        description="上傳語音檔 (mp3/m4a/wav)"
    ),

    image_zip: UploadFile = File(
        ...,
        description="上傳包含多張照片的 ZIP 壓縮檔"
    ),

    bgm_file: UploadFile = File(
        ...,
        description="上傳背景音樂檔 (mp3)"
    ),

    spot_list: str = Form(
        '["南投環湖茶園", "竹林秘境"]',
        description="景點清單 (JSON格式或逗號分隔)"
    )
):

    task_id = str(uuid.uuid4())[:8]

    filename = f"vlog_{task_id}.mp4"

    try:

        # ----------------------------------------------------
        # 儲存語音
        # ----------------------------------------------------

        audio_extension = (
            os.path.splitext(
                user_audio.filename or ".wav"
            )[1]
            or ".wav"
        )

        raw_audio_path = str(
            AUDIO_DIR /
            f"raw_{task_id}{audio_extension}"
        )

        clean_audio_path = str(
            AUDIO_DIR /
            f"upload_{task_id}.wav"
        )

        with open(
            raw_audio_path,
            "wb"
        ) as buffer:

            shutil.copyfileobj(
                user_audio.file,
                buffer
            )

        # ----------------------------------------------------
        # FFmpeg 音訊轉換
        # ----------------------------------------------------

        ffmpeg_command = (
            f'ffmpeg -y '
            f'-i "{raw_audio_path}" '
            f'-ar 16000 '
            f'-ac 1 '
            f'"{clean_audio_path}" '
            f'> /dev/null 2>&1'
        )

        os.system(ffmpeg_command)

        # ----------------------------------------------------
        # 解壓縮圖片
        # ----------------------------------------------------

        full_image_paths = []

        zip_temp_path = str(
            IMAGES_DIR /
            f"{task_id}_images.zip"
        )

        with open(
            zip_temp_path,
            "wb"
        ) as buffer:

            shutil.copyfileobj(
                image_zip.file,
                buffer
            )

        extract_to = (
            IMAGES_DIR /
            f"{task_id}_extracted"
        )

        os.makedirs(
            extract_to,
            exist_ok=True
        )

        with zipfile.ZipFile(
            zip_temp_path,
            "r"
        ) as zip_ref:

            zip_ref.extractall(
                extract_to
            )

        for root, dirs, files in os.walk(
            extract_to
        ):

            for file in files:

                if file.lower().endswith(
                    (
                        ".png",
                        ".jpg",
                        ".jpeg",
                        ".webp"
                    )
                ):

                    full_image_paths.append(
                        os.path.join(
                            root,
                            file
                        )
                    )

        # ----------------------------------------------------
        # 儲存 BGM
        # ----------------------------------------------------

        bgm_filename = (
            bgm_file.filename
            or f"bgm_{task_id}.mp3"
        )

        bgm_path = str(
            BGM_DIR /
            f"{task_id}_{bgm_filename}"
        )

        with open(
            bgm_path,
            "wb"
        ) as buffer:

            shutil.copyfileobj(
                bgm_file.file,
                buffer
            )

        # ----------------------------------------------------
        # ASR
        # ----------------------------------------------------

        raw_text = transcribe_audio(
            clean_audio_path
        )

        # ----------------------------------------------------
        # 情緒分析
        # ----------------------------------------------------

        emotion = analyze_emotion(
            clean_audio_path
        )

        # ----------------------------------------------------
        # 景點清單
        # ----------------------------------------------------

        try:

            spots = json.loads(
                spot_list
            )

            if not isinstance(
                spots,
                list
            ):
                spots = [str(spots)]

        except Exception:

            spots = [
                s.strip()
                for s in spot_list.split(",")
                if s.strip()
            ]

        # ----------------------------------------------------
        # Neo4j RAG
        # ----------------------------------------------------

        rag_context = "\n".join(
            [
                search_neo4j_rag(spot)
                for spot in spots
            ]
        )

        # ----------------------------------------------------
        # LLM 生成 Vlog
        # ----------------------------------------------------

        script_data = (
            generate_vlog_content_with_template(
                raw_text,
                emotion,
                "user_vlog",
                rag_context
            )
        )

        # ----------------------------------------------------
        # TTS
        # ----------------------------------------------------

        tts_path = await generate_tts(
            script_data["tw_script"]
        )

        # ----------------------------------------------------
        # 背景執行 Vlog
        # ----------------------------------------------------

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
            "check_url": (
                f"https://vlog.angelalala.com/"
                f"api/check_status/{task_id}"
            )
        }

    except Exception as e:

        print(
            f"❌ [VLOG] "
            f"Vlog 建立失敗：{e}"
        )

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "task_id": task_id,
                "message": f"Vlog 建立失敗：{str(e)}"
            }
        )
