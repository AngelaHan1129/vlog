import os
import uuid
import json
import urllib.request
import urllib.parse
import time
import shutil
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from services.llm_service import _get_llm
from services.neo4j_rag_service import search_neo4j_rag
from core.config import OUTPUT_DIR

# 將 editorial-vision-studio 納入系統路徑
sys.path.append("/home/jackstar/playtaiwan/editorial-vision-studio")

def generate_postcard_text(spot_name: str, user_prompt: str = "") -> str:
    llm = _get_llm()
    rag_context = search_neo4j_rag(spot_name, is_night_mode=False)
    system_prompt = f"你是一位文青風格導覽員與明信片詩人。景點：{spot_name}。請寫一段精緻、有溫度的在地介紹（限制 80 字以內，不輸出多餘符號）。"

    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": "請生成明信片短文："}]
    try:
        outputs = llm(messages, max_new_tokens=150, temperature=0.7, do_sample=True)
        return outputs[0]["generated_text"][-1]["content"].strip()
    except Exception as e:
        print(f"❌ LLM 生成文字失敗: {e}")
        return f"歡迎來到 {spot_name}，感受獨特的在地文化與自然風情。"

async def generate_ai_postcard_image(user_img_path: str, spot_name: str, user_prompt: str, task_id: str = "") -> str:
    os.makedirs(str(OUTPUT_DIR), exist_ok=True)
    if not task_id:
        task_id = str(uuid.uuid4())[:8]

    raw_ai_output_path = os.path.join(OUTPUT_DIR, f"ai_raw_{task_id}.png")
    output_path = os.path.join(OUTPUT_DIR, f"ai_postcard_{task_id}.png")

    try:
        # 1. 回歸最純粹的極簡高調 Prompt
        compiled_prompt = (
            f"masterpiece, minimalist editorial illustration of {spot_name}, distinct 8-tiered stacked architecture, "
            f"exhibition catalog art style, generous negative space, pure ivory background, clean empty sky, "
            f"muted low-saturation Morandi palette, flat pastel gouache brushstrokes, 2D flat design, "
            f"exact architectural structure, sharp straight lines, simple elegant geometric shapes."
        )
        
        negative_prompt = (
            "photorealistic, realistic photography, realistic lighting, 3d render, perspective, "
            "complex textures, shading, gradients, dark, grey, mountains, clouds, messy background, "
            "magazine cover, frame, border, text, watermark, noisy, cluttered, melted, deformed"
        )

        # 2. 🚨 核心破解：用 PIL 自製線稿預處理 (Faux-Lineart)
        original_pil = Image.open(user_img_path).convert("RGB")
        # 轉成灰階並強化邊緣 (這會產生黑底白線，正是 ControlNet 最喜歡的格式)
        edges_pil = original_pil.convert("L").filter(ImageFilter.FIND_EDGES)
        # 增強對比，讓建築線條更清晰
        edges_pil = ImageOps.autocontrast(edges_pil)

        filename_only = f"postcard_lineart_{task_id}.jpg"
        comfy_input_dir = "/home/jackstar/playtaiwan/ComfyUI/input/"
        edges_path = os.path.join(comfy_input_dir, filename_only)
        edges_pil.save(edges_path)

        # 3. 讀取並動態重組工作流 (強制回到純淨的 Empty Latent 模式)
        with open("postcard_workflow.json", "r", encoding="utf-8") as f:
            workflow = json.load(f)

        # 確保 14 號節點是空白畫布 (取代之前的 VAEEncode)
        workflow["14"] = {
            "inputs": { "width": 512, "height": 512, "batch_size": 1 },
            "class_type": "EmptyLatentImage"
        }

        if "3" in workflow:
            workflow["3"]["inputs"]["latent_image"] = ["14", 0]  # 接回空白畫布
            workflow["3"]["inputs"]["positive"] = ["13", 0]      # 接回 ControlNet
            workflow["3"]["inputs"]["denoise"] = 1.0             # 1.0 全開，允許徹底洗掉寫實感
            
        if "13" in workflow:
            # 強度 0.85：足以鎖住 PIL 抓出來的 101 線稿，又不會干擾水粉上色
            workflow["13"]["inputs"]["strength"] = 0.85

        if "6" in workflow:
            workflow["6"]["inputs"]["text"] = compiled_prompt
        if "7" in workflow:
            workflow["7"]["inputs"]["text"] = negative_prompt
        if "10" in workflow:
            workflow["10"]["inputs"]["image"] = filename_only # 餵入黑白線稿，而非彩色原圖！

        # 4. 發送至 ComfyUI API
        req = urllib.request.Request(
            "http://127.0.0.1:8188/prompt",
            data=json.dumps({"prompt": workflow}).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req) as response:
            prompt_id = json.loads(response.read().decode('utf-8'))['prompt_id']

        # 5. 等待 ComfyUI 渲染 (等待時間拉長至 600 秒，確保硬體有充裕時間運算)
        image_data = None
        for _ in range(600):
            time.sleep(1)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:8188/history/{prompt_id}") as hist_res:
                    history_data = json.loads(hist_res.read().decode('utf-8'))
                    if prompt_id in history_data:
                        for node_output in history_data[prompt_id].get("outputs", {}).values():
                            if "images" in node_output:
                                img_info = node_output["images"][0]
                                img_url = f"http://127.0.0.1:8188/view?filename={urllib.parse.quote(img_info['filename'])}&subfolder={urllib.parse.quote(img_info['subfolder'])}&type={img_info['type']}"
                                with urllib.request.urlopen(img_url) as img_resp:
                                    image_data = img_resp.read()
                        break
            except Exception:
                continue

        if not image_data:
            raise Exception("ComfyUI 渲染失敗或逾時")

        with open(raw_ai_output_path, "wb") as f:
            f.write(image_data)

        # 6. PIL 後處理 (象牙白邊框 + 排版)
        img = Image.open(raw_ai_output_path).convert("RGB")
        base_width = 1200
        h_size = int(float(img.size[1]) * (base_width / float(img.size[0])))
        img = img.resize((base_width, h_size), Image.Resampling.LANCZOS)

        canvas = Image.new("RGB", (base_width + 160, h_size + 280), color="#FBF9F5")
        canvas.paste(img, (80, 80))

        draw = ImageDraw.Draw(canvas)
        font = None
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"
        ]
        for f_path in font_paths:
            if os.path.exists(f_path):
                try:
                    font = ImageFont.truetype(f_path, 48)
                    break
                except Exception:
                    continue
        if font is None:
            font = ImageFont.load_default()

        title_text = f"//  {spot_name.upper()}  —  EDITORIAL ZINE EDITION"
        draw.text((90, h_size + 150), title_text, fill="#4A4A4A", font=font)

        canvas.save(output_path, quality=95)
        print(f"✅ [Editorial Pipeline] 成功生成極簡雜誌風明信片: {output_path}")
        return output_path

    except Exception as e:
        print(f"⚠️ 完整管線錯誤: {e}")
        shutil.copy(user_img_path, output_path)
        return output_path
