import os
import re
import subprocess
import traceback
from core.config import OUTPUT_DIR, TEMPLATES

def clean_subtitle_text(text: str) -> str:
    if not text:
        return ""
    # 移除 Emoji 與特殊符號
    emoji_pattern = re.compile(
        r"["
        r"\U00010000-\U0010ffff"
        r"\u2600-\u27bf"
        r"\u1f900-\u1f9ff"
        r"]+", flags=re.UNICODE
    )
    cleaned = emoji_pattern.sub(r"", text)
    cleaned = cleaned.replace("'", "").replace('"', "").replace("`", "")
    cleaned = cleaned.replace(":", "\\:").replace("%", "\\%")
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > 80:
        cleaned = cleaned[:80] + "..."
    return cleaned

def process_vlog_task(task_id, image_files, prompt, tts_audio_file, bgm_file, output_file, template_type, merchant_name="", subtitle_text=""):
    tpl = TEMPLATES.get(template_type, TEMPLATES["user_vlog"])
    print(f"\n[任務 {task_id}] 🚀 開始合成 (模板: {tpl['name']})")

    concat_list_path = None
    temp_video_path = None

    try:
        os.makedirs(str(OUTPUT_DIR), exist_ok=True)
        final_output_path = os.path.abspath(os.path.join(str(OUTPUT_DIR), output_file))
        temp_video_path = os.path.abspath(os.path.join(str(OUTPUT_DIR), f"{task_id}_temp_merged.mp4"))
        concat_list_path = os.path.abspath(os.path.join(str(OUTPUT_DIR), f"{task_id}_list.txt"))

        # 1. 抓取剛剛由 ltx_service 產生的影片片段
        import glob
        all_ltx = sorted(glob.glob(os.path.join(str(OUTPUT_DIR), "ltx_*.mp4")), key=os.path.getmtime)
        clip_files = all_ltx[-len(image_files):]

        if not clip_files:
            raise RuntimeError("找不到任何可用的 LTX 影片片段供合成！")

        print(f"[任務 {task_id}] 🎞️ 找到 {len(clip_files)} 個影片片段準備串接")

        # 2. 建立 FFmpeg concat 清單
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for clip_file in clip_files:
                f.write(f"file '{os.path.abspath(clip_file)}'\n")

        # 3. 使用 FFmpeg concat 將片段接成無聲影片
        print(f"[任務 {task_id}] 🔄 正在透過 FFmpeg 串接影片片段...")
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            temp_video_path
        ]
        
        result = subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")

        # 4. 準備字幕參數：安全起見，若有中文字型則指定，若解析失敗則改用系統預設
        font_path = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
        
        video_filter_arg = "format=yuv420p"
        if subtitle_text:
            safe_sub = clean_subtitle_text(subtitle_text)
            if safe_sub:
                # 檢查字型是否存在，若存在則加上 fontfile，否則僅用文字以防報錯
                if os.path.exists(font_path):
                    # 嚴格避開引號衝突的寫法
                    video_filter_arg = f"drawtext=fontfile={font_path}:text='{safe_sub}':fontcolor=white:fontsize=32:box=1:boxcolor=black@0.6:boxborderw=10:x=(w-text_w)/2:y=h-150"
                else:
                    video_filter_arg = f"drawtext=text='{safe_sub}':fontcolor=white:fontsize=32:box=1:boxcolor=black@0.6:boxborderw=10:x=(w-text_w)/2:y=h-150"

        # 5. 將無聲影片、TTS 語音與安全字幕進行最終合檔
        print(f"[任務 {task_id}] 🔄 正在進行字幕燒錄與最終合檔...")
        final_cmd = [
            "ffmpeg", "-y",
            "-i", temp_video_path,
            "-i", str(tts_audio_file),
            "-vf", video_filter_arg,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            final_output_path
        ]
        
        result_final = subprocess.run(final_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result_final.returncode != 0:
            print(f"[任務 {task_id}] ❌ FFmpeg 燒錄字幕失敗:\n{result_final.stderr}")
            raise RuntimeError(f"FFmpeg subtitle merge failed: {result_final.stderr}")

        if os.path.exists(final_output_path) and os.path.getsize(final_output_path) > 0:
            print(f"[任務 {task_id}] ✅ 帶字幕的影片完美落地！大小: {os.path.getsize(final_output_path)} bytes")
        else:
            print(f"[任務 {task_id}] ❌ 錯誤：找不到最終檔案！")

    except Exception as e:
        print(f"[任務 {task_id}] ❌ 合成崩潰:")
        traceback.print_exc()

    finally:
        for p in [concat_list_path, temp_video_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass
