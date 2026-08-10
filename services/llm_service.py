import torch
import json
from transformers import pipeline

# 全域變數：確保 LLM 只載入一次
_llm_pipeline = None

def _get_llm():
    global _llm_pipeline
    if _llm_pipeline is None:
        print("🚀 正在載入 LLM 大腦 (Llama-3-8B-Instruct)...")
        # ⚠️ 注意：這顆大腦需要大約 15GB 的顯示卡記憶體 (VRAM)
        _llm_pipeline = pipeline(
            "text-generation",
            model="NousResearch/Meta-Llama-3-8B-Instruct",
            model_kwargs={"torch_dtype": torch.bfloat16}, # 使用 bfloat16 節省記憶體
            device_map="auto"
        )
        print("✅ LLM 大腦載入完成！")
        
    return _llm_pipeline

def generate_vlog_content(asr_text: str) -> dict:
    """
    接收 ASR 辨識出的草稿，轉換為 Vlog 旁白與影片生成 Prompt
    """
    llm = _get_llm()
    
    print("🧠 大腦正在思考如何將語音轉換為優美的 Vlog 腳本...")

# Llama-3 的系統提示詞，賦予它強烈的「南投觀光 Vlog 企劃」人設
    system_prompt = """你是一個專業的台灣南投觀光 Vlog 企劃。
請根據使用者提供的語音草稿（可能是語音辨識錯誤的亂碼或外語），完成兩件事：
1. 修正錯字與語病，將其改寫為一句流暢、充滿感情的「繁體中文（台灣用語）」旁白。若草稿不知所云（例如出現 Firefox 等無關詞彙），請主動將其腦補、轉化為跟「南投、茶園、放鬆、大自然」有關的優美句子。絕對不能出現簡體字。
2. 根據旁白，寫一句「英文」的畫面描述 (Prompt)，用來生成沒有文字的風景動態影片。

請嚴格輸出 JSON 格式，格式如下：
{"tw_script": "你的繁體中文旁白", "en_video_prompt": "Your english video prompt"}"""

    # 將對話格式化為 Llama-3 認得的 Chat Template
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"語音草稿：{asr_text}"},
    ]
    
    # 執行推論生成
    outputs = llm(
        messages,
        max_new_tokens=200,
        temperature=0.7, # 給予一點創造力
        do_sample=True,
    )
    
    # 取出 AI 回覆的文字
    response_text = outputs[0]["generated_text"][-1]["content"].strip()
    
    # 嘗試解析 JSON (實務上這裡可以加上 Try-Except 確保容錯)
    try:
        # 尋找 JSON 區塊
        start_idx = response_text.find("{")
        end_idx = response_text.rfind("}") + 1
        json_str = response_text[start_idx:end_idx]
        result = json.loads(json_str)
        
        print("✅ 腳本生成完畢！")
        return result
    except Exception as e:
        print(f"❌ 解析 LLM 輸出失敗：{e}\n原始輸出：{response_text}")
        return {"tw_script": asr_text, "en_video_prompt": "beautiful landscape in Nantou, Taiwan, highly detailed"}
