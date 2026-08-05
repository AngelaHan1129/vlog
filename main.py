from moviepy import (
    ImageClip,
    AudioFileClip,
    CompositeAudioClip,
    concatenate_videoclips,
    TextClip,
    CompositeVideoClip,
)
from moviepy.audio.fx import AudioLoop
from config import IMAGES_DIR, AUDIO_DIR, BGM_DIR, OUTPUT_DIR, VLOG_WIDTH, VLOG_HEIGHT, FPS, IMAGE_DURATION
import os

def generate_vlog(
    image_files: list[str],
    tts_audio_file: str,
    bgm_file: str,
    output_file: str = "output_vlog.mp4",
):
    # 1. 載入圖片
    clips = []
    for img_path in image_files:
        # 2. v2 語法：set_duration 變成 with_duration
        img_clip = ImageClip(str(img_path)).with_duration(IMAGE_DURATION)
        # 3. v2 語法：resize 變成 resized，crop 變成 cropped
        img_clip = img_clip.resized(height=VLOG_HEIGHT)
        img_clip = img_clip.cropped(x_center=img_clip.w/2, y_center=img_clip.h/2, width=VLOG_WIDTH, height=VLOG_HEIGHT)
        clips.append(img_clip)

    # 2. 載入旁白
    tts_audio = AudioFileClip(str(tts_audio_file))

    # 3. 載入背景音樂（音量降低）- v2 語法：volumex 變成 multiply_volume
    bgm_audio = AudioFileClip(str(bgm_file)).volx(0.3)

    # 4. 調整背景音樂長度與旁白一致 - v2 語法：subclip 變成 subclipped
    if bgm_audio.duration > tts_audio.duration:
        bgm_audio = bgm_audio.subclipped(0, tts_audio.duration)
    else:
        # 如果背景音樂太短，可以重複播放 - v2 迴圈處理方式不同
        bgm_audio = bgm_audio.with_effects([AudioLoop(duration=tts_audio.duration)])

    # 5. 合成音訊
    final_audio = CompositeAudioClip([tts_audio, bgm_audio])

    # 6. 組合影片 - v2 語法：set_audio 變成 with_audio
    video = concatenate_videoclips(clips, method="compose")
    video = video.with_audio(final_audio)

    # 7. 輸出
    output_path = OUTPUT_DIR / output_file
    video.write_videofile(str(output_path), fps=FPS, codec="libx264", audio_codec="aac")
    return str(output_path)

if __name__ == "__main__":
    # 以下測試區塊不需要更改
    image_files = [
        IMAGES_DIR / "img1.jpg",
        IMAGES_DIR / "img2.jpg",
        IMAGES_DIR / "img3.jpg",
    ]
    tts_audio_file = AUDIO_DIR / "tts_output.wav"
    bgm_file = BGM_DIR / "bgm.mp3"

    output_path = generate_vlog(
        image_files=[str(f) for f in image_files],
        tts_audio_file=str(tts_audio_file),
        bgm_file=str(bgm_file),
        output_file="vlog_test.mp4",
    )
    print(f"Vlog 已生成：{output_path}")