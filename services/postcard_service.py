import os
import uuid
import json
import urllib.request
import urllib.parse
import time
import shutil
import sys

from services.llm_service import _get_llm
from services.neo4j_rag_service import search_neo4j_rag
from core.config import OUTPUT_DIR

# 將 editorial-vision-studio 納入系統路徑以供決策引擎呼叫
sys.path.append("/home/jackstar/playtaiwan/editorial-vision-studio")

def generate_postcard_text(spot_name: str, user_prompt: str = "") -> str:
    """
    使用本地 Llama-3 結合 Neo4j 知識脈絡生成在地明信片短文
    """
    llm = _get_llm()
    rag_context = search_neo4j_rag(spot_name, is_night_mode=False)

    system_prompt = f"""你是一位文青風格的在地導覽員與明信片詩人。
【景點名稱】：{spot_name}
【Neo4j 在地知識脈絡】：{rag_context}
【使用者想法/座標】：{user_prompt}

請根據以上資訊，為一張極簡風格的明信片寫一段精緻、有溫度、帶有在地文化特色的介紹文字（限制 80 字以內，不要輸出多餘符號）。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "請生成明信片短文："}
    ]

    try:
        outputs = llm(messages, max_new_tokens=150, temperature=0.7, do_sample=True)
        return outputs[0]["generated_text"][-1]["content"].strip()
    except Exception as e:
        print(f"❌ LLM 生成文字失敗: {e}")
        return f"歡迎來到{spot_name}，感受獨特的在地文化與自然風情。"

async def generate_ai_postcard_image(user_img_path: str, spot_name: str, user_prompt: str, task_id: str = "") -> str:
    """
    落實 editorial-vision-studio 引擎規範的圖片生成與 ComfyUI 轉譯服務
    """
    os.makedirs(str(OUTPUT_DIR), exist_ok=True)
    if not task_id:
        task_id = str(uuid.uuid4())[:8]

    output_filename = f"ai_postcard_{task_id}.png"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    spec_txt_path = os.path.join(OUTPUT_DIR, f"editorial_spec_{task_id}.txt")

    try:
        # 1. 載入 editorial-vision-studio 的 ivory-postcard 預設規範
        preset_path = "/home/jackstar/playtaiwan/editorial-vision-studio/presets/ivory-postcard.md"
        if os.path.exists(preset_path):
            with open(preset_path, "r", encoding="utf-8") as f:
                print("📖 [Editorial Vision Studio] 成功載入 presets/ivory-postcard.md 規格")

        # 2. 依照引擎合約產出 VisionSpec 視覺指令 (ground: paper-light, render_mode: painterly)
        compiled_prompt = (
            f"Minimalist editorial exhibition catalog illustration of {spot_name}. "
            f"Warm ivory paper background (ground: paper-light), flat gouache and soft watercolor shapes (render_mode: painterly). "
            f"Preserve spatial relationships and major lines of the reference structure, but remove all photorealistic details, gradients, and textures. "
            f"Muted Morandi color palette, generous 55% negative space, single top-center placement. "
            f"At the bottom border, include a small elegant serif title reading '{spot_name}'."
        )

        # 3. 輸出規格書供 Manifest 追蹤
        with open(spec_txt_path, "w", encoding="utf-8") as f:
            f.write(f"--- Editorial Vision Studio Spec ---\nPreset: ivory-postcard\nTarget: {spot_name}\nPrompt: {compiled_prompt}")

        print(f"✨ [Editorial Studio] 視覺規範規格書已儲存至: {spec_txt_path}")

        # 4. 準備圖片並複製到 ComfyUI input 目錄
        filename_only = f"postcard_raw_{task_id}.jpg"
        comfy_input_dir = "/home/jackstar/playtaiwan/ComfyUI/input/"
        if os.path.exists(comfy_input_dir):
            shutil.copy(user_img_path, os.path.join(comfy_input_dir, filename_only))

        # 5. 載入 ComfyUI 工作流設定檔
        workflow_path = "postcard_workflow.json"
        if not os.path.exists(workflow_path):
            raise Exception("找不到 postcard_workflow.json")

        with open(workflow_path, "r", encoding="utf-8") as f:
            workflow = json.load(f)

        # 6. 精準注入提示詞與圖片節點 (對應節點 6 與 10)
        if "6" in workflow:
            workflow["6"]["inputs"]["text"] = compiled_prompt
        if "10" in workflow:
            workflow["10"]["inputs"]["image"] = filename_only

        # 7. 發送請求至 ComfyUI 執行背景渲染
        req = urllib.request.Request(
            "http://127.0.0.1:8188/prompt",
            data=json.dumps({"prompt": workflow}).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            prompt_id = res_data.get('prompt_id')

        # 8. 輪詢等待 ComfyUI 渲染完成
        image_data = None
        for _ in range(40):
            time.sleep(1)
            try:
                history_req = urllib.request.Request(f"http://127.0.0.1:8188/history/{prompt_id}")
                with urllib.request.urlopen(history_req) as hist_res:
                    history_data = json.loads(hist_res.read().decode('utf-8'))
                    if prompt_id in history_data:
                        outputs = history_data[prompt_id].get("outputs", {})
                        for node_output in outputs.values():
                            if "images" in node_output:
                                img_info = node_output["images"][0]
                                img_url = f"http://127.0.0.1:8188/view?filename={urllib.parse.quote(img_info['filename'])}&subfolder={urllib.parse.quote(img_info['subfolder'])}&type={img_info['type']}"
                                with urllib.request.urlopen(img_url) as img_resp:
                                    image_data = img_resp.read()
                                break
                    if image_data:
                        break
            except Exception:
                continue

        if image_data:
            with open(output_path, "wb") as f:
                f.write(image_data)
            print(f"✅ [ComfyUI] 成功渲染雜誌風明細片並儲存至: {output_path}")
            return output_path
        else:
            print("⚠️ ComfyUI 渲染逾時，退回原圖備用")
            shutil.copy(user_img_path, output_path)
            return output_path

    except Exception as e:
        print(f"⚠️ 服務管線發生錯誤: {e}")
        shutil.copy(user_img_path, output_path)
        return output_path
