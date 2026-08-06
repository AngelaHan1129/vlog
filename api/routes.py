import uuid
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from core.config import IMAGES_DIR, AUDIO_DIR, BGM_DIR
from services.moviepy_service import process_vlog_task

router = APIRouter()

# 前端只需傳檔名，不用傳完整路徑
class VlogRequest(BaseModel):
    image_files: list[str]
    tts_audio_file: str
    bgm_file: str

@router.post("/create_vlog")
async def create_vlog_api(request: VlogRequest, bg_tasks: BackgroundTasks):
    # 產生唯一的任務 ID，避免檔名衝突 (取前8碼)
    task_id = str(uuid.uuid4())[:8] 
    output_filename = f"vlog_{task_id}.mp4"
    
    # 將前端傳來的檔名，組裝成伺服器看懂的絕對路徑
    full_image_paths = [str(IMAGES_DIR / img) for img in request.image_files]
    full_tts_path = str(AUDIO_DIR / request.tts_audio_file)
    full_bgm_path = str(BGM_DIR / request.bgm_file)
    
    # 丟進背景處理 (立刻交辦，不卡著 API)
    bg_tasks.add_task(
        process_vlog_task,
        task_id=task_id,
        image_files=full_image_paths,
        tts_audio_file=full_tts_path,
        bgm_file=full_bgm_path,
        output_file=output_filename
    )
    
    # 立刻回覆前端
    return {
        "status": "processing",
        "task_id": task_id,
        "message": "已將生成任務加入排程，影片正在背景生成中...",
        "expected_output": output_filename
    }