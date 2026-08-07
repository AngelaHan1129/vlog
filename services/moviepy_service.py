import os
from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips
from moviepy.audio.fx import AudioLoop, MultiplyVolume
from moviepy.video.fx import Loop
from core.config import VLOG_WIDTH, VLOG_HEIGHT, FPS, IMAGE_DURATION, OUTPUT_DIR

# 匯入寫好的 LTX 引擎
from services.ltx_service import generate_ltx_video 

def process_vlog_task(task_id: str, image_files: list[str], prompt: str, tts_audio_file: str, bgm_file: str, output_file: str):
    """
    這是一個處理影片合成的背景函數 (已整合 LTX-Video AI 動態生成)
    """
    print(f"\n[任務 {task_id}] 🚀 開始進行影片合成...")

    # 檢查檔案
    for img in image_files:
        if not os.path.exists(img):
            print(f"[任務 {task_id}] ❌ 失敗：找不到圖片 {img}")
            return

    try:
        clips = []
        for img_path in image_files:
            print(f"[任務 {task_id}] 🎨 正在呼叫 LTX-Video 生成動態影片... (來源: {img_path})")
            
            # 1. 呼叫 LTX-Video 將靜態圖片轉為動態 MP4
            ai_video_path = generate_ltx_video(str(img_path), prompt)
            
            # 2. 讀取 AI 生成的動態影片
            img_clip = VideoFileClip(ai_video_path)
            
            # 3. 調整長度 (讓 2 秒的 AI 影片循環播放，直到滿足設定的畫面停留時間)
            img_clip = img_clip.with_effects([Loop(duration=IMAGE_DURATION)])
            
            # 4. 調整大小與裁切 (符合 Vlog 的長寬比)
            img_clip = img_clip.resized(height=VLOG_HEIGHT)
            img_clip = img_clip.cropped(x_center=img_clip.w/2, y_center=img_clip.h/2, width=VLOG_WIDTH, height=VLOG_HEIGHT)
            
            clips.append(img_clip)

        # 處理語音與背景音樂
        tts_audio = AudioFileClip(str(tts_audio_file))
        bgm_audio = AudioFileClip(str(bgm_file)).with_effects([MultiplyVolume(0.3)])

        if bgm_audio.duration > tts_audio.duration:
            bgm_audio = bgm_audio.subclipped(0, tts_audio.duration)
        else:
            bgm_audio = bgm_audio.with_effects([AudioLoop(duration=tts_audio.duration)])

        final_audio = CompositeAudioClip([tts_audio, bgm_audio])

        # 串接所有動態影片並壓上音軌
        video = concatenate_videoclips(clips, method="compose")
        video = video.with_audio(final_audio)

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = OUTPUT_DIR / output_file

        # 加上 temp_audiofile 避免多任務並行時暫存檔衝突
        temp_audio_name = str(OUTPUT_DIR / f"temp_{task_id}.mp3")
        video.write_videofile(
            str(output_path),
            fps=FPS,
            codec="libx264",
            audio_codec="libmp3lame",
            temp_audiofile=temp_audio_name
        )

        print(f"[任務 {task_id}] ✅ 影片合成完畢！路徑: {output_path}")

    except Exception as e:
        print(f"[任務 {task_id}] ❌ 合成發生錯誤: {str(e)}")
