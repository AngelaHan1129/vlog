import os
from moviepy import ImageClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips
from moviepy.audio.fx import AudioLoop, MultiplyVolume
from core.config import VLOG_WIDTH, VLOG_HEIGHT, FPS, IMAGE_DURATION, OUTPUT_DIR

def process_vlog_task(task_id: str, image_files: list[str], tts_audio_file: str, bgm_file: str, output_file: str):
    """
    這是一個純粹處理影片合成的背景函數
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
            img_clip = ImageClip(str(img_path)).with_duration(IMAGE_DURATION)
            img_clip = img_clip.resized(height=VLOG_HEIGHT)
            img_clip = img_clip.cropped(x_center=img_clip.w/2, y_center=img_clip.h/2, width=VLOG_WIDTH, height=VLOG_HEIGHT)
            clips.append(img_clip)

        tts_audio = AudioFileClip(str(tts_audio_file))
        bgm_audio = AudioFileClip(str(bgm_file)).with_effects([MultiplyVolume(0.3)])

        if bgm_audio.duration > tts_audio.duration:
            bgm_audio = bgm_audio.subclipped(0, tts_audio.duration)
        else:
            bgm_audio = bgm_audio.with_effects([AudioLoop(duration=tts_audio.duration)])

        final_audio = CompositeAudioClip([tts_audio, bgm_audio])
        
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