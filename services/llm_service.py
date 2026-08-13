import torch
import json
from transformers import pipeline
from core.config import TEMPLATES

_llm_pipeline = None

def _get_llm():
    global _llm_pipeline
    if _llm_pipeline is None:
        print("🚀 正在載入 LLM 大腦 (Llama-3-8B-Instruct)...")
        _llm_pipeline = pipeline("text-generation", model="NousResearch/Meta-Llama-3-8B-Instruct", 
                                 model_kwargs={"torch_dtype": torch.bfloat16}, device_map="auto")
    return _llm_pipeline

def generate_vlog_content_with_template(raw_text: str, emotion: str, template: str, rag_context: str = "") -> dict:
    llm = _get_llm()
    tpl = TEMPLATES.get(template, TEMPLATES["user_vlog"])
    
    system_prompt = f"""你是一個專業旅遊編劇。
【當前模式】：{tpl['name']}
【口吻風格】：{tpl['tone']}
【在地背景 (RAG)】：{rag_context}
【使用者情感】：{emotion}

請根據以上條件，輸出 JSON：
{{"tw_script": "...", "en_video_prompt": "..."}}"""

    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"素材：{raw_text}"}]
    outputs = llm(messages, max_new_tokens=300, temperature=0.7, do_sample=True)
    
    response = outputs[0]["generated_text"][-1]["content"]
    start, end = response.find("{"), response.rfind("}") + 1
    try:
        return json.loads(response[start:end])
    except:
        return {"tw_script": "歡迎來到南投，這是一段美好的旅程。", "en_video_prompt": "scenic landscape"}
