
# 這是 Mock 資料庫
MOCK_GRAPH_DB = {
    "南投環湖茶園": {
        "description": "海拔800公尺，擁有百年製茶歷史，日夜溫差大，是台茶18號的故鄉。",
        "night_event": "【茶鄉夜遊】利用竹藝與AR投影，打造沈浸式光影茶道體驗。",
        "nearby_merchants": ["阿爸的手作茶坊", "雲霧茶室"]
    },
    "竹林秘境": {
        "description": "連綿的孟宗竹林，陽光透過竹葉灑下的光影效果非常適合攝影。",
        "night_event": "【竹林觀星】無光害環境，可體驗古法星空導覽。",
        "nearby_merchants": ["竹藝工作坊"]
    }
}

def search_neo4j_rag(spot_name: str, is_night_mode: bool = False) -> str:
    """
    Mock Neo4j 檢索服務：
    未來替換時，這裡改成真正的 Neo4j Driver 連線即可。
    """
    spot_data = MOCK_GRAPH_DB.get(spot_name)
    
    if not spot_data:
        return f"【景點背景】{spot_name} 是一處充滿南投在地文化特色的旅遊景點。"

    # 組合內容給 LLM 參考
    context = f"【景點特色】{spot_data['description']}\n"
    
    if is_night_mode:
        context += f"【夜間互動】{spot_data['night_event']}\n"
        
    context += f"【周邊推薦商家】{', '.join(spot_data['nearby_merchants'])}"
    
    print(f"🔍 [Mock Neo4j] 成功撈取 {spot_name} 的關聯脈絡")
    return context
