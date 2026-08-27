import os
import re
import subprocess
import traceback
from core.config import OUTPUT_DIR, TEMPLATES

def clean_subtitle_text(text: str) -> str:
    if not text:
        return ""
    # 移除 Emoji 與特殊符號，只保留中文、英文、數字、常見標點
    clean_pattern = re.compile(r"[^\u4e00-\u9fa5a-zA-Z0-9\s\-\(\)\/\:\.]+")
    cleaned = clean_pattern.sub(r"", text)
    cleaned = cleaned.replace("'", "").replace('"', "").replace("`", "")
    cleaned = cleaned.replace(":", "\\:").replace("%", "\\%")
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > 80:
        cleaned = cleaned[:80] + "..."
    return cleaned

def find_valid_font():
    """尋找 Linux 系統中可用的中文字型路徑"""
    candidate_fonts = [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    for font in candidate_fonts:
        if os.path.exists(font):
            return font
    return None

def process_vlog_task(
    task_id, 
    image_files, 
    prompt, 
    tts_audio_file, 
    bgm_file, 
    output_file, 
    template_type, 
    merchant_name="", 
    subtitle_text="",
    spot_metadata=None
):
    tpl = TEMPLATES.get(template_type, TEMPLATES["user_vlog"])
    print(f"\n[任務 {task_id}] 🚀 開始合成 (模板: {tpl['name']})")

    concat_list_path = None
    temp_video_path = None
    slide_videos = []

    try:
        os.makedirs(str(OUTPUT_DIR), exist_ok=True)
        final_output_path = os.path.abspath(os.path.join(str(OUTPUT_DIR), output_file))
        temp_video_path = os.path.abspath(os.path.join(str(OUTPUT_DIR), f"{task_id}_temp_merged.mp4"))
        concat_list_path = os.path.abspath(os.path.join(str(OUTPUT_DIR), f"{task_id}_list.txt"))

        font_path = find_valid_font()
        print(f"[任務 {task_id}] 🔤 使用字型路徑: {font_path}")

        print(f"[任務 {task_id}] 🎞️ 正在處理 {len(image_files)} 張照片的動態與地點標籤...")
        
        for idx, img_path in enumerate(image_files):
            slide_out = os.path.abspath(os.path.join(str(OUTPUT_DIR), f"{task_id}_slide_{idx}.mp4"))
            slide_videos.append(slide_out)

            meta_info = spot_metadata[idx] if spot_metadata and idx < len(spot_metadata) else {}
            spot_name = meta_info.get("spot_name", merchant_name or "探索據點")
            codename = meta_info.get("location_codename", "")
            visit_time = meta_info.get("visit_time", "")

            # 組合乾淨的地點與時間字串（避免 Emoji 亂碼）
            watermark_text = f"地點: {spot_name}"
            if codename:
                watermark_text += f" ({codename})"
            if visit_time:
                watermark_text += f"  時間: {visit_time}"

            safe_wm = clean_subtitle_text(watermark_text)

            # FFmpeg 濾鏡組合
            vf_filter = (
                f"scale=1280:720:force_original_aspect_ratio=decrease,"
                f"pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"zoompan=z='min(zoom+0.0015,1.08)':d=125:s=1280x720,"
            )

            # 若有找到有效的中文字型則透過 fontfile 渲染，否則僅印出文字
            if safe_wm:
                if font_path:
                    vf_filter += f"drawtext=fontfile={font_path}:text='{safe_wm}':fontcolor=white:fontsize=28:box=1:boxcolor=black@0.6:boxborderw=8:x=40:y=40,"
                else:
                    vf_filter += f"drawtext=text='{safe_wm}':fontcolor=white:fontsize=28:box=1:boxcolor=black@0.6:boxborderw=8:x=40:y=40,"

            vf_filter += "format=yuv420p"

            slide_cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", img_path,
                "-t", "4",
                "-vf", vf_filter,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                slide_out
            ]
            subprocess.run(slide_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # 2. 建立 FFmpeg concat 清單
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for slide in slide_videos:
                f.write(f"file '{slide}'\n")

        # 3. 串接所有幻燈片片段
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            temp_video_path
        ]
        subprocess.run(concat_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # 4. 準備主字幕 (TTS 旁白文字)
        video_filter_arg = "format=yuv420p"
        if subtitle_text:
            safe_sub = clean_subtitle_text(subtitle_text)
            if safe_sub:
                if font_path:
                    video_filter_arg = f"drawtext=fontfile={font_path}:text='{safe_sub}':fontcolor=white:fontsize=32:box=1:boxcolor=black@0.6:boxborderw=10:x=(w-text_w)/2:y=h-100"
                else:
                    video_filter_arg = f"drawtext=text='{safe_sub}':fontcolor=white:fontsize=32:box=1:boxcolor=black@0.6:boxborderw=10:x=(w-text_w)/2:y=h-100"

        # 5. 最終合檔
        has_bgm = bgm_file and os.path.exists(str(bgm_file))
        if has_bgm:
            final_cmd = [
                "ffmpeg", "-y",
                "-i", temp_video_path,
                "-i", str(tts_audio_file),
                "-i", str(bgm_file),
                "-filter_complex",
                "[1:a]volume=1.0[a1];[2:a]volume=0.2[a2];[a1][a2]amix=inputs=2:duration=first[aout]",
                "-vf", video_filter_arg,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-map", "0:v:0",
                "-map", "[aout]",
                "-shortest",
                final_output_path
            ]
        else:
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

        subprocess.run(final_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(f"[任務 {task_id}] ✅ 影片合成成功: {final_output_path}")

    except Exception as e:
        print(f"[任務 {task_id}] ❌ 合成崩潰: {e}")
        traceback.print_exc()

    finally:
        for p in [concat_list_path, temp_video_path] + slide_videos:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass
