import os
from neo4j import GraphDatabase

# Neo4j 資料庫連線設定 (對應你的 docker 容器設定)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "playtaiwan2026")

# 全域 Driver 快取
_driver = None

def _get_driver():
    global _driver
    if _driver is None:
        try:
            _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            _driver.verify_connectivity()
            print("✅ 成功連線至真實 Neo4j 圖形資料庫！")
        except Exception as e:
            print(f"⚠️ 無法連線至 Neo4j 資料庫，將啟用備用 fallback 機制: {e}")
            _driver = None
    return _driver

def search_neo4j_rag(spot_name: str, is_night_mode: bool = False) -> str:
    """
    真實的 Neo4j 檢索服務：
    透過 Cypher 查詢 Spot 節點及其關聯的商家與夜間活動。
    """
    driver = _get_driver()
    
    # 若資料庫尚未啟動或連線失敗，提供安全的預設文案
    if driver is None:
        return f"【景點背景】{spot_name} 是一處充滿南投在地文化特色的旅遊景點。"

    # Cypher 查詢語法
    cypher_query = """
    MATCH (s:Spot {name: $spot_name})
    OPTIONAL MATCH (s)-[:HAS_MERCHANT]->(m:Merchant)
    RETURN s.description AS description, 
           s.night_event AS night_event, 
           collect(m.name) AS merchants
    """

    try:
        with driver.session() as session:
            result = session.run(cypher_query, spot_name=spot_name)
            record = result.single()

            if not record or not record["description"]:
                return f"【景點背景】{spot_name} 是一處充滿南投在地文化特色的旅遊景點。"

            description = record["description"]
            night_event = record["night_event"]
            merchants = record["merchants"]

            # 組合內容給 LLM 參考
            context = f"【景點特色】{description}\n"

            if is_night_mode and night_event:
                context += f"【夜間互動】{night_event}\n"

            if merchants and len(merchants) > 0 and merchants[0] is not None:
                context += f"【周邊推薦商家】{', '.join(merchants)}"
            else:
                context += "【周邊推薦商家】在地特色手作工坊與茶室"

            print(f"🔍 [Neo4j] 成功撈取 {spot_name} 的關聯脈絡")
            return context

    except Exception as e:
        print(f"❌ Neo4j 查詢失敗 ({spot_name}): {e}")
        return f"【景點背景】{spot_name} 是一處充滿南投在地文化特色的旅遊景點。"
