import os
from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips, ColorClip, TextClip, CompositeVideoClip
from moviepy.audio.fx import AudioLoop, MultiplyVolume
from moviepy.video.fx import Loop
from core.config import VLOG_WIDTH, VLOG_HEIGHT, FPS, OUTPUT_DIR, TEMPLATES
from services.ltx_service import generate_ltx_video 

def process_vlog_task(task_id, image_files, prompt, tts_audio_file, bgm_file, output_file, template_type, merchant_name=""):
    tpl = TEMPLATES.get(template_type, TEMPLATES["user_vlog"])
    print(f"\n[任務 {task_id}] 🚀 開始合成 (模板: {tpl['name']})")

    try:
        # 聲音處理
        tts_audio = AudioFileClip(str(tts_audio_file))
        bgm_audio = AudioFileClip(str(bgm_file)).with_effects([MultiplyVolume(tpl["bgm_vol"])])
        bgm_audio = bgm_audio.with_effects([AudioLoop(duration=tts_audio.duration)])
        final_audio = CompositeAudioClip([tts_audio, bgm_audio])
        
        # 影像處理
        clips = []
        for img in image_files:
            ai_path = generate_ltx_video(str(img), prompt)
            clip = VideoFileClip(ai_path).with_effects([Loop(duration=tpl["image_duration"])])
            clip = clip.resized(height=VLOG_HEIGHT).cropped(x_center=clip.w/2, y_center=clip.h/2, width=VLOG_WIDTH, height=VLOG_HEIGHT)
            clips.append(clip)

        video = concatenate_videoclips(clips, method="compose") if clips else ColorClip(size=(VLOG_WIDTH, VLOG_HEIGHT), color=(0,0,0), duration=tts_audio.duration)

        # 商家導購卡邏輯
        if tpl["add_cta"] and merchant_name:
            txt = TextClip(f"📍 推薦店家：{merchant_name}\n🔥 立即前往體驗！", fontsize=60, color='white', bg_color='rgba(0,0,0,0.6)', size=(VLOG_WIDTH*0.8, None))
            # 讓字卡出現在影片最後 3 秒
            video = CompositeVideoClip([video, txt.set_position("center").with_start(video.duration - 3)])

        video = video.with_audio(final_audio)
        video.write_videofile(str(OUTPUT_DIR / output_file), fps=FPS, codec="libx264", audio_codec="libmp3lame")
        print(f"[任務 {task_id}] ✅ 合成完畢！")

    except Exception as e:
        print(f"[任務 {task_id}] ❌ 錯誤: {str(e)}")
