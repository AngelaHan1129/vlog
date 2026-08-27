import torch
import json
import random
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
    tpl = TEMPLATES.get(template, TEMPLATES.get("user_vlog", {"name": "一般生活紀錄", "tone": "自然"}))

    extra_info = ""
    if "user" in template or "visitor" in template:
        extra_info += f"【遊玩時間】：{play_time}\n" if play_time else ""
        extra_info += f"【完成任務】：{game_tasks}\n" if game_tasks else ""
    elif "merchant" in template or "promo" in template:
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

    outputs = llm(messages, max_new_tokens=1024, temperature=0.7, do_sample=True)

    response = outputs[0]["generated_text"][-1]["content"]
    start, end = response.find("{"), response.rfind("}") + 1

    try:
        return json.loads(response[start:end])
    except Exception as e:
        print(f"❌ LLM JSON 解析失敗: {e}\n原始輸出: {response}")
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

    if node_type == "dialogue":
        req = DialogueInput(**payload_dict)
        npc = req.npcs[0] if req.npcs else type("Dummy", (), {"npc_id": "npc_01", "name": "神秘引導員", "role": "NPC"})()

        sys_prompt = f"""你是一個實境遊戲的劇情 AI 引擎。請務必嚴格輸出一個純 JSON 物件（不要包含任何 Markdown 標記或額外文字），用來回應玩家的對話與推進劇情。

【當前地點】：{req.location.name} ({req.location.address}) - {req.location.description}
【當前目標】：{req.node_context.goal}
【場景描述】：{req.node_context.scene_description}
【扮演 NPC】：{npc.name} ({getattr(npc, 'role', 'NPC')})。
【玩家輸入】：{req.player_input}

【輸出 JSON 結構規範（請務必包含以下所有欄位，型態需完全相符）】：
{{
  "location_id": "{req.location.location_id}",
  "node_id": "{req.node_id}",
  "narration": {{
    "opening_hook": "吸引玩家的短旁白懸念 (繁體中文)",
    "scene_description": "當前場景的進一步氛圍描述 (繁體中文)",
    "historical_note": null
  }},
  "npc_dialogue": [
    {{
      "npc_id": "{getattr(npc, 'npc_id', 'npc_01')}",
      "line": "NPC 回應玩家的台詞 (繁體中文)",
      "emotion": "happy",
      "handoff_to": null
    }}
  ],
  "player_choices": [
    {{
      "choice_id": "choice_1",
      "text": "引導玩家繼續下一步的選項按鈕文字 (繁體中文)"
    }}
  ]
}}
*(注意：emotion 欄位的值僅限：happy, neutral, angry, sad, excited 之一)*
"""

        msgs = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"玩家剛才說：「{req.player_input}」。請根據上述規範產生對應的 JSON 回應。"}
        ]

        for attempt in range(max_retries):
            try:
                outputs = llm(
                    msgs,
                    max_new_tokens=req.max_tokens or 400,
                    temperature=req.temperature or 0.7,
                    do_sample=True
                )
                raw_json = _parse_llm_json(outputs[0]["generated_text"][-1]["content"])

                if "location_id" not in raw_json or not raw_json["location_id"]:
                    raw_json["location_id"] = req.location.location_id
                if "node_id" not in raw_json or not raw_json["node_id"]:
                    raw_json["node_id"] = req.node_id

                parsed = DialogueOutput(**raw_json)
                return parsed.model_dump()
            except Exception as e:
                print(f"⚠️ [Dialogue] 驗證失敗 ({attempt+1}/{max_retries}): {e}")

        print("❌ [Dialogue] 觸發 Fallback")
        return DialogueOutput(
            location_id=req.location.location_id, node_id=req.node_id,
            narration={"opening_hook": "周圍的空氣似乎凝結了。", "scene_description": "場景中暫時沒有變化。", "historical_note": None},
            npc_dialogue=[{"npc_id": getattr(npc, 'npc_id', 'npc_01'), "line": "不好意思，我剛剛恍神了，你能再說一次嗎？", "emotion": "neutral", "handoff_to": None}],
            player_choices=[{"choice_id": "retry", "text": "再試一次"}]
        ).model_dump()

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
                outputs = llm(msgs, max_new_tokens=req.max_tokens or 400, temperature=req.temperature or 0.7, do_sample=True)
                raw_json = _parse_llm_json(outputs[0]["generated_text"][-1]["content"])

                if "day_index" not in raw_json:
                    raw_json["day_index"] = req.day_index

                parsed = OvernightTransitionOutput(**raw_json)
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

    elif node_type == "narration":
        req = NarrationInput(**payload_dict)
        sys_prompt = "你是一個旁白修飾引擎。請微調並輸出JSON。"
        msgs = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"旁白原文：{req.script_text}\n請輸出JSON："}]

        for attempt in range(max_retries):
            try:
                outputs = llm(msgs, max_new_tokens=req.max_tokens or 400, temperature=req.temperature or 0.7, do_sample=True)
                raw_json = _parse_llm_json(outputs[0]["generated_text"][-1]["content"])

                if "node_id" not in raw_json: raw_json["node_id"] = req.node_id
                if "day_index" not in raw_json: raw_json["day_index"] = req.day_index

                parsed = NarrationOutputNode(**raw_json)
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
# 4. 後台工具：結合 Neo4j 開放資料的實境劇本與NPC對話自動生成 (支援多參數與動態動線)
# ============================================================
def generate_script_blueprint(
    city_name: str,
    town_name: str,
    locations: list,
    traveler_count: int = 1,
    preferences: list = [],
    transportation: list = [],
    is_night: bool = False
) -> dict:
    llm = _get_llm()
    node_count = len(locations)

    locations_text = ""
    for idx, loc in enumerate(locations):
        node_type_ch = {"Attraction": "景點", "Restaurant": "特色餐廳", "Hotel": "在地旅宿"}.get(loc['type'], "據點")
        tags_str = f"、特色標籤：{', '.join(loc['tags'])}" if loc.get('tags') else ""
        cuisines_str = f"、推薦料理：{', '.join(loc['cuisines'])}" if loc.get('cuisines') else ""
        ticket_str = f"、門票資訊：{loc['ticket_info']}" if loc.get('ticket_info') else ""

        locations_text += f"- 第 {idx+1} 站 [{node_type_ch}]: {loc['name']}\n"
        locations_text += f"  介紹摘要: {loc['description'][:200]}...\n"
        locations_text += f"  真實資料: 地址 {loc['address']}{tags_str}{cuisines_str}{ticket_str}\n\n"

    mode_title = "夜間尋密與過夜線" if is_night else "白天主線探索"

    # 隨機挑選 NPC 避免永遠都是薯光
    npc_pool = [
        {"name": "薯光", "role": "充滿朝氣的新生代引導者，善於解開謎題、點燃線索"},
        {"name": "珍奶奶", "role": "掌管地方數十年的記憶與失落古老配方的守密人"},
        {"name": "阿達力", "role": "機靈靈通的在地走透透達人，熟悉大街小巷與美食情報"},
        {"name": "墨先生", "role": "博學嚴謹的文史工作者，擅長解讀古地圖與歷史檔案"},
        {"name": "霓霓", "role": "對美感與光影極度敏銳的街頭藝術家，專門引導光影觀察與夜遊探索"},
        {"name": "阿吉伯", "role": "外冷內熱的傳統工藝老師傅，重視手作與傳承"}
    ]
    selected_npc = random.choice(npc_pool)

    pref_str = "、".join(preferences) if preferences else "綜合體驗"
    trans_str = "、".join(transportation) if transportation else "大眾運輸與步行"

    system_prompt = f"""你是一位頂尖的中文歷史懸疑小說家與劇作家。
【絕對最高指令】：
1. 本次生成的所有欄位內容（包含標題、前言、大綱、角色介紹、任務說明、NPC開場白、過關對話等）**必須 100% 使用純正的繁體中文 (zh-TW) 撰寫**。
2. **絕對嚴禁出現任何英文字母、英文單字或英文句子**。如果需要描述外國語彙或裝飾，請全部用中文字表達！

【任務目標】：請根據以下目標地區與真實地點，自行發揮創意構思一個引人入勝的解謎冒險主題，並為這 **{node_count} 個地點** 創作一篇情節豐富、細節飽滿的長篇解謎劇本（{mode_title}）。
- 目標地區：{city_name} {town_name}
- 旅程人數：{traveler_count} 人
- 旅客偏好：{pref_str}
- 交通方式：{trans_str}

【指定擔任主角的 NPC】：
- 姓名：{selected_npc['name']}
- 身分：{selected_npc['role']}

【指定站點清單 (共 {node_count} 站)】：
{locations_text}

請嚴格輸出純 JSON 格式 (不要包含任何 Markdown 標記，且所有內容必須是 100% 純繁體中文)：
{{
  "title": "富有詩意、懸疑感且精采吸睛的劇本名稱（純繁體中文）",
  "preface": "大約100字以內的前言，作為整篇故事的前導介紹，懸疑吸引人但不完全劇透（絕對不能有英文）...",
  "synopsis": "四到五句、極具史詩感與懸疑氛圍的故事大綱（絕對不能有英文）...",
  "is_night_mode": {str(is_night).lower()},
  "npc": {{
    "name": "{selected_npc['name']}",
    "role": "{selected_npc['role']}",
    "intro": "詳細的角色小傳（絕對不能有英文）"
  }},
  "nodes": [
    {{
      "node_order": 1,
      "place_name": "對應清單中的站點真實名稱",
      "location_codename": "一個非地點名稱卻能詩意描述該地點的代名稱（例如：紅瓦書院）",
      "node_title": "充滿意境的關卡標題（純繁體中文）",
      "task_type": "3. 採訪蒐證型",
      "task_description": "融合地點歷史與解謎線索的深度任務說明（至少 80-120 字，絕對不能有英文）...",
      "dialogues": {{
        "opening": "長篇且充滿懸疑感的開場對白（至少 4-5 句，絕對不能有英文）...",
        "success": "過關時的讚許以及預告下一站危機的對白（絕對不能有英文）..."
      }}
    }}
  ]
}}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "請嚴格遵守繁體中文指令，並自主發想精彩主題，產出一篇內容豐富、百分之百純繁體中文的長篇解謎劇本 JSON："}
    ]

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 將 max_new_tokens 稍微調降至 2500，加快生成速度並避免 Cloudflare 逾時
            outputs = llm(messages, max_new_tokens=2500, temperature=0.7, do_sample=True)
            response = outputs[0]["generated_text"][-1]["content"]
            start, end = response.find("{"), response.rfind("}") + 1
            if start != -1 and end != 0:
                return json.loads(response[start:end])
        except Exception as e:
            print(f"⚠️ 劇本藍圖生成失敗，重試中 ({attempt+1}/{max_retries})... 錯誤: {e}")

    return {
        "story_id": "fallback_01",
        "title": f"{town_name}時光迷局",
        "preface": "一段未知的歷史迷局，正等待著你的雙腳去解開...",
        "synopsis": "探索在地文化的精采旅程。",
        "is_night_mode": is_night,
        "nodes": []
    }
