import os
import json
import uuid
import shutil
import time
import urllib.request
import urllib.parse
from services.llm_service import _get_llm
from services.neo4j_rag_service import search_neo4j_rag
from core.config import OUTPUT_DIR

def generate_postcard_text(spot_name: str, user_prompt: str = "") -> str:
    """
    使用本地的 Llama-3-8B-Instruct 結合 Neo4j 脈絡生成明信片在地介紹短文
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
        response = outputs[0]["generated_text"][-1]["content"].strip()
        return response
    except Exception as e:
        print(f"❌ 本地 LLM 生成明信片文字失敗: {e}")
        return f"歡迎來到{spot_name}，感受獨特的在地文化與自然風情。"


async def generate_ai_postcard_image(user_img_path: str, spot_name: str, custom_art_prompt: str) -> str:
    """
    透過本地 ComfyUI API (port 8188) 進行高質感展覽圖錄風格明信片生成，並取得真實生成結果
    """
    os.makedirs(str(OUTPUT_DIR), exist_ok=True)
    task_id = str(uuid.uuid4())[:8]
    output_filename = f"ai_postcard_{task_id}.png"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    workflow_path = "postcard_workflow.json"
    
    if not os.path.exists(workflow_path):
        print(f"⚠️ 找不到 {workflow_path}，將暫時以原圖作為備用輸出。")
        shutil.copy(user_img_path, output_path)
        return output_path

    try:
        # 1. 讀取 ComfyUI API Workflow 設定
        with open(workflow_path, "r") as f:
            workflow = json.load(f)

        filename_only = os.path.basename(user_img_path)
        
        # 將照片複製到 ComfyUI 的 input 資料夾
        comfy_input_dir = "/home/jackstar/playtaiwan/ComfyUI/input/"
        if os.path.exists(comfy_input_dir):
            shutil.copy(user_img_path, os.path.join(comfy_input_dir, filename_only))

        # 動態修改 Workflow 節點屬性（根據你的 JSON 結構：文字通常在 CLIPTextEncode，圖片在 LoadImage）
        for node_id, node_data in workflow.items():
            if node_data.get("class_type") == "CLIPTextEncode":
                if "text" in node_data["inputs"]:
                    node_data["inputs"]["text"] = custom_art_prompt
            elif node_data.get("class_type") == "LoadImage":
                if "image" in node_data["inputs"]:
                    node_data["inputs"]["image"] = filename_only

        # 2. 發送 API 請求給本地 ComfyUI (8188)
        req = urllib.request.Request(
            "http://127.0.0.1:8188/prompt", 
            data=json.dumps({"prompt": workflow}).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        
        prompt_id = None
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            prompt_id = res_data.get('prompt_id')
            print(f"🎨 [ComfyUI] 成功觸發繪圖任務，Prompt ID: {prompt_id}")

        if not prompt_id:
            raise Exception("未能取得 ComfyUI prompt_id")

        # 3. 輪詢等待 ComfyUI 執行完畢並取得生成的圖片
        image_data = None
        for _ in range(30):  # 最多等待 30 次 (約 30 秒)
            time.sleep(1)
            try:
                history_req = urllib.request.Request(f"http://127.0.0.1:8188/history/{prompt_id}")
                with urllib.request.urlopen(history_req) as hist_res:
                    history_data = json.loads(hist_res.read().decode('utf-8'))
                    if prompt_id in history_data:
                        outputs = history_data[prompt_id].get("outputs", {})
                        # 尋找輸出圖片的節點
                        for node_output in outputs.values():
                            if "images" in node_output:
                                img_info = node_output["images"][0]
                                filename = img_info["filename"]
                                subfolder = img_info["subfolder"]
                                folder_type = img_info["type"]
                                
                                # 下載生成的圖片
                                img_url = f"http://127.0.0.1:8188/view?filename={urllib.parse.quote(filename)}&subfolder={urllib.parse.quote(subfolder)}&type={folder_type}"
                                with urllib.request.urlopen(img_url) as img_resp:
                                    image_data = img_resp.read()
                                break
                    if image_data:
                        break
            except Exception as poll_err:
                continue

        if image_data:
            with open(output_path, "wb") as f:
                f.write(image_data)
            print(f"✅ [ComfyUI] 成功取得 AI 生成圖片並儲存至: {output_path}")
            return output_path
        else:
            print("⚠️ ComfyUI 執行逾時或未回傳圖片，退回原圖備用。")
            shutil.copy(user_img_path, output_path)
            return output_path

    except Exception as e:
        print(f"⚠️ 連線本地 ComfyUI 失敗，已自動切換為備用機制: {e}")
        shutil.copy(user_img_path, output_path)
        return output_path
