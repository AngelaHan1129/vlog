import os
import subprocess
import traceback
from core.config import OUTPUT_DIR, TEMPLATES

def process_vlog_task(task_id, image_files, prompt, tts_audio_file, bgm_file, output_file, template_type, merchant_name=""):
    tpl = TEMPLATES.get(template_type, TEMPLATES["user_vlog"])
    print(f"\n[任務 {task_id}] 🚀 開始合成 (模板: {tpl['name']})")

    concat_list_path = None
    temp_video_path = None

    try:
        os.makedirs(str(OUTPUT_DIR), exist_ok=True)
        final_output_path = os.path.abspath(os.path.join(str(OUTPUT_DIR), output_file))
        temp_video_path = os.path.abspath(os.path.join(str(OUTPUT_DIR), f"{task_id}_temp_merged.mp4"))
        concat_list_path = os.path.abspath(os.path.join(str(OUTPUT_DIR), f"{task_id}_list.txt"))

        # 1. 收集剛剛由 ltx_service 成功產生的影片片段路徑
        clip_files = []
        for f in os.listdir(OUTPUT_DIR):
            if f.startswith("ltx_") and f.endswith(".mp4"):
                # 簡單過濾出最近產生的片段（或直接將 ltx_service 回傳的路徑接進來）
                pass

        # 為了保險，我們直接用 ltx_service 產生的絕對路徑陣列
        # 這裡我們利用全域變數或直接從剛剛生成的檔案中抓取對應的片段
        # 更好的方式是讓 ltx_service 回傳路徑，但我們可以直接透過 glob 抓取剛出爐的 ltx 檔案
        import glob
        all_ltx = sorted(glob.glob(os.path.join(str(OUTPUT_DIR), "ltx_*.mp4")), key=os.path.getmtime)
        # 取最後 N 個片段（對應本次任務的圖片數量）
        clip_files = all_ltx[-len(image_files):]

        if not clip_files:
            raise RuntimeError("找不到任何可用的 LTX 影片片段供合成！")

        print(f"[任務 {task_id}] 🎞️ 找到 {len(clip_files)} 個影片片段準備串接")

        # 2. 建立 FFmpeg concat 專用的文字清單檔案
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for clip_file in clip_files:
                f.write(f"file '{os.path.abspath(clip_file)}'\n")

        # 3. 使用 FFmpeg concat 快速將多個影片接成一個無聲影片
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
            print(f"[任務 {task_id}] ❌ FFmpeg 片段串接失敗:\n{result.stderr}")
            raise RuntimeError(f"FFmpeg concat failed with code {result.returncode}")

        # 4. 將串接好的無聲影片與 TTS 語音進行最終合檔
        print(f"[任務 {task_id}] 🔄 正在與 TTS 語音進行最終合檔...")
        final_cmd = [
            "ffmpeg", "-y",
            "-i", temp_video_path,
            "-i", str(tts_audio_file),
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            final_output_path
        ]
        
        result_final = subprocess.run(final_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result_final.returncode != 0:
            print(f"[任務 {task_id}] ❌ FFmpeg 最終合檔失敗:\n{result_final.stderr}")
            raise RuntimeError(f"FFmpeg final merge failed with code {result_final.returncode}")

        # 5. 最終硬碟確認
        if os.path.exists(final_output_path) and os.path.getsize(final_output_path) > 0:
            print(f"[任務 {task_id}] ✅ 完美落地！最終影片大小: {os.path.getsize(final_output_path)} bytes")
        else:
            print(f"[任務 {task_id}] ❌ 錯誤：FFmpeg 執行結束但找不到最終檔案！")

    except Exception as e:
        print(f"[任務 {task_id}] ❌ 合成崩潰:")
        traceback.print_exc()

    finally:
        # 清理暫存檔案與清單
        for p in [concat_list_path, temp_video_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass
