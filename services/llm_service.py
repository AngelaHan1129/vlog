import torch
import json
from pydantic import ValidationError
from api.schemas import (
    DialogueInput, DialogueOutput,
    OvernightTransitionInput, OvernightTransitionOutput,
    NarrationInput, NarrationOutputNode
)
from transformers import pipeline
from core.config import TEMPLATES

_llm_pipeline = None

def _get_llm():
    global _llm_pipeline
    if _llm_pipeline is None:
        print("🚀 正在載入 LLM 大腦 (Llama-3-8B-Instruct)...")
        _llm_pipeline = pipeline(
            "text-generation",
            model="NousResearch/Meta-Llama-3-8B-Instruct",
            model_kwargs={"torch_dtype": torch.bfloat16},
            device_map="auto"
        )
    return _llm_pipeline

def generate_vlog_content_with_template(
    raw_text: str,
    emotion: str,
    template: str,
    rag_context: str = "",
    play_time: str = "",
    game_tasks: str = "",
    promo_info: str = ""
) -> dict:
    llm = _get_llm()
    # 防呆：若找不到對應 template，預設回傳 user_vlog 相關設定
    tpl = TEMPLATES.get(template, TEMPLATES.get("user_vlog", {"name": "一般生活紀錄", "tone": "自然"}))

    # ==========================================
    # 根據情境 (遊客 vs 商家) 動態組裝額外提示詞
    # ==========================================
    extra_info = ""
    if "user" in template or "visitor" in template:
        # 遊客模式：強調遊戲化與時間回憶
        extra_info += f"【遊玩時間】：{play_time}\n" if play_time else ""
        extra_info += f"【完成任務】：{game_tasks}\n" if game_tasks else ""
    elif "merchant" in template or "promo" in template:
        # 商家模式：強調主打特色與促銷
        extra_info += f"【商家優惠/主打】：{promo_info}\n" if promo_info else ""

    system_prompt = f"""你是一個專業旅遊編劇與數位行銷專家。
【當前模式】：{tpl['name']}
【口吻風格】：{tpl['tone']}
【在地背景 (RAG)】：{rag_context}
【使用者情感/語氣】：{emotion}
{extra_info}
【撰寫守則】：
1. 嚴禁憑空捏造，請將「在地背景」的文史故事或特色自然融入旁白中。
2. 若有提供「遊玩時間」、「完成任務」或「商家優惠」，必須以流暢的敘事手法寫入腳本。
3. 根據內容萃取出具備商業價值的客群與 SEO 標籤。

請務必嚴格輸出以下 JSON 格式，不要包含任何其他解釋文字：
{{
    "tw_script": "Vlog的中文旁白腳本 (約100-150字)",
    "en_video_prompt": "給AI影片生成引擎的英文場景提示詞，詳細描述畫面視覺",
    "seo_keywords": ["關鍵字1", "關鍵字2", "關鍵字3"],
    "target_audience": ["客群1", "客群2"],
    "promo_copy": "適合發布在 IG/FB 的社群宣傳貼文文案 (包含 Hashtag)"
}}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"使用者提供素材/要求：{raw_text}"}
    ]

    # 將 max_new_tokens 提高至 1024 以容納完整的行銷文案與多維度 JSON
    outputs = llm(messages, max_new_tokens=1024, temperature=0.7, do_sample=True)

    response = outputs[0]["generated_text"][-1]["content"]
    start, end = response.find("{"), response.rfind("}") + 1

    try:
        # 嘗試解析 JSON
        return json.loads(response[start:end])
    except Exception as e:
        print(f"❌ LLM JSON 解析失敗: {e}\n原始輸出: {response}")
        # 預設 Fallback 確保後續 MoviePy 與 TTS 流程不會崩潰
        return {
            "tw_script": "歡迎來到這段美好的旅程，讓我們一起探索在地文化與獨特風情！",
            "en_video_prompt": "beautiful scenic landscape, high quality, cinematic lighting",
            "seo_keywords": ["台灣旅遊", "在地體驗", "特色觀光"],
            "target_audience": ["旅遊愛好者", "大眾客群"],
            "promo_copy": "展開一段美好的旅程！快來這裡探索未知的驚喜吧！ #旅遊 #探索"
        }

def _parse_llm_json(response_text: str):
    start, end = response_text.find("{"), response_text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("找不到 JSON 結構")
    return json.loads(response_text[start:end])

def generate_story_node(payload_dict: dict) -> dict:
    llm = _get_llm()
    node_type = payload_dict.get("node_type")
    max_retries = 3

    # ==========================================
    # 1. 處理 Dialogue 節點
    # ==========================================
    if node_type == "dialogue":
        req = DialogueInput(**payload_dict)
        npc = req.npcs[0]

        sys_prompt = f"""你是一個實境遊戲的劇情引擎。請嚴格輸出JSON。
【場景】：{req.location.name} - {req.location.description}
【目標】：{req.node_context.goal} ({req.node_context.scene_description})
【扮演NPC】：{npc.name} ({npc.role})。個性：{",".join(npc.personality)}。
對話情緒限定：happy, neutral, angry, sad, excited
"""
        msgs = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"玩家說：{req.player_input}\n請輸出JSON："}]

        for attempt in range(max_retries):
            try:
                outputs = llm(msgs, max_new_tokens=req.max_tokens, temperature=req.temperature)
                raw_json = _parse_llm_json(outputs[0]["generated_text"][-1]["content"])
                parsed = DialogueOutput(**raw_json)

                # 驗證一致性
                if parsed.node_id != req.node_id or parsed.location_id != req.location.location_id:
                    raise ValueError("node_id 或 location_id 不一致")
                return parsed.model_dump()
            except Exception as e:
                print(f"⚠️ [Dialogue] 驗證失敗 ({attempt+1}/{max_retries}): {e}")

        print("❌ [Dialogue] 觸發 Fallback")
        return DialogueOutput(
            location_id=req.location.location_id, node_id=req.node_id,
            narration={"opening_hook": "周圍的空氣似乎凝結了。", "scene_description": "場景中暫時沒有變化。", "historical_note": None},
            npc_dialogue=[{"npc_id": npc.npc_id, "line": "不好意思，我剛剛恍神了，你能再說一次嗎？", "emotion": "neutral", "handoff_to": None}],
            player_choices=[{"choice_id": "retry", "text": "再試一次"}]
        ).model_dump()

    # ==========================================
    # 2. 處理 Overnight Transition 節點
    # ==========================================
    elif node_type == "overnight_transition":
        req = OvernightTransitionInput(**payload_dict)
        sys_prompt = f"""你是一個實境遊戲編劇。請嚴格輸出JSON。
今日總結：{", ".join([s.summary_text for s in req.day_summary])}
住宿地點：{req.accommodation.name} - {req.accommodation.description}
請回傳 recap, accommodation_scene, next_day_hint。
"""
        msgs = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": "請根據今日行程與住宿產出過夜轉場 JSON："}]

        for attempt in range(max_retries):
            try:
                outputs = llm(msgs, max_new_tokens=req.max_tokens, temperature=req.temperature)
                raw_json = _parse_llm_json(outputs[0]["generated_text"][-1]["content"])
                parsed = OvernightTransitionOutput(**raw_json)

                if parsed.day_index != req.day_index:
                    raise ValueError("day_index 不一致")
                return parsed.model_dump()
            except Exception as e:
                print(f"⚠️ [Overnight] 驗證失敗 ({attempt+1}/{max_retries}): {e}")

        print("❌ [Overnight] 觸發 Fallback")
        return OvernightTransitionOutput(
            day_index=req.day_index,
            recap="充實的一天結束了，回顧今日的旅程，收穫滿滿。",
            accommodation_scene=f"你回到了{req.accommodation.name}，舒適的環境讓你放鬆下來。",
            next_day_hint="好好休息吧，明天還有全新的挑戰等著你。"
        ).model_dump()

    # ==========================================
    # 3. 處理 Narration 節點
    # ==========================================
    elif node_type == "narration":
        req = NarrationInput(**payload_dict)
        sys_prompt = "你是一個旁白修飾引擎。請微調並輸出JSON。"
        msgs = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"旁白原文：{req.script_text}\n請輸出JSON："}]

        for attempt in range(max_retries):
            try:
                outputs = llm(msgs, max_new_tokens=req.max_tokens, temperature=req.temperature)
                raw_json = _parse_llm_json(outputs[0]["generated_text"][-1]["content"])
                parsed = NarrationOutputNode(**raw_json)

                if parsed.node_id != req.node_id or parsed.day_index != req.day_index:
                    raise ValueError("node_id 或 day_index 不一致")
                return parsed.model_dump()
            except Exception as e:
                print(f"⚠️ [Narration] 驗證失敗 ({attempt+1}/{max_retries}): {e}")

        print("❌ [Narration] 觸發 Fallback")
        return NarrationOutputNode(
            day_index=req.day_index, node_id=req.node_id, narration_text=req.script_text
        ).model_dump()

    else:
        raise ValueError(f"未知的 node_type: {node_type}")


# ============================================================
# 4. 後台工具：實境劇本與NPC對話一次性自動生成
# ============================================================
def generate_script_blueprint(theme: str, town_name: str, locations: list) -> dict:
    llm = _get_llm()

    # 將 RAG 撈出來的地點轉為文字給 LLM 參考
    locations_text = "\n".join([f"- 第 {idx+1} 站: {loc['name']} ({loc['description'][:100]}...)" for idx, loc in enumerate(locations)])

    # 👇 在這裡加入強制使用繁體中文的指令
    system_prompt = f"""你是一個實境解謎遊戲企劃兼劇本作家。
【任務目標】：請根據以下真實地點與主題，一次性生成完整的「起承轉合地點任務」與「NPC 對話劇本」。
⚠️ 重要限制：請務必使用「繁體中文 (zh-TW)」撰寫所有的標題、大綱、任務內容與對話。嚴禁使用英文或簡體中文！

【劇本主題】：{theme} ({town_name})
【指定地點清單 (請依序安排為關卡)】：
{locations_text}

【可用任務類型庫】：
1. 拍照打卡型、2. 短片演繹型、3. 採訪蒐證型、4. 計數推理型、5. 跨關集結型、6. GPS 區域定位型
7. 圖像地理猜謎型、8. 協作解謎型、9. e人訪談型、10. 文化問答型、11. 創意攝影型、12. 光影觀察型、13. 地方美食型

請嚴格輸出以下 JSON 格式 (純 JSON，不要包含 Markdown 標記如 ```json )：
{{
  "story_id": "自動產生一個英文ID (例: story_001)",
  "title": "引人入勝的劇本標題 (繁體中文)",
  "synopsis": "劇本大綱(約100字，繁體中文)",
  "npc": {{
    "name": "專屬 NPC 名稱",
    "role": "NPC 身份",
    "intro": "NPC 的背景故事，與劇本主題的關聯"
  }},
  "nodes": [
    {{
      "node_order": 1,
      "narrative_arc": "起",
      "place_name": "指定地點1的名稱",
      "node_title": "第一關標題",
      "task_type": "填入上方13種任務類型之一",
      "task_description": "玩家要在這關做什麼解謎或任務？",
      "dialogues": {{
        "opening": "【開場對話】當玩家抵達此地點時，NPC 對玩家說的話（介紹場景並引出任務）。",
        "success": "【成功對話】玩家解完任務後，NPC 稱讚玩家並引導前往下一關的話。"
      }}
    }},
    {{
      "node_order": 2,
      "narrative_arc": "承",
      "place_name": "指定地點2的名稱",
      "node_title": "第二關標題",
      "task_type": "任務類型",
      "task_description": "玩家要在這關做什麼解謎或任務？",
      "dialogues": {{
        "opening": "【開場對話】抵達第二關時 NPC 的對話。",
        "success": "【成功對話】解完第二關後 NPC 的對話。"
      }}
    }}
    // 請務必依序完成地點3(轉)與地點4(合)
  ]
}}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "請開始設計完整的任務與對話劇本，嚴格輸出 JSON："}
    ]

    print(f"🧠 [LLM] 正在為 {town_name} 一次性生成完整劇本與對話...")

    # 將 max_new_tokens 拉高至 2000，因為一次產生 4 關的對話會需要比較多長度
    for attempt in range(3):
        try:
            outputs = llm(messages, max_new_tokens=2000, temperature=0.7, do_sample=True)
            response_text = outputs[0]["generated_text"][-1]["content"]
            raw_json = _parse_llm_json(response_text)
            return raw_json
        except Exception as e:
            print(f"⚠️ 劇本生成失敗，重試中 ({attempt+1}/3)... 錯誤: {e}")

    raise ValueError("Llama-3 無法產生正確的劇本 JSON")















