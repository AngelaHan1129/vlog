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


# ============================================================
# 1. RAG 檢索服務 (供 LLM 產生 Vlog 腳本使用)
# ============================================================
def search_neo4j_rag(spot_name: str, is_night_mode: bool = False) -> str:
    """
    動態讀取活動(Event)、景點(Attraction)、餐飲(Restaurant)或旅宿(Hotel)的資料，
    並自動關聯地理位置(City)、標籤(Tag)與料理類型(Cuisine)提供給 LLM 作為脈絡。
    """
    driver = _get_driver()
    
    if driver is None:
        return f"【景點背景】{spot_name} 是一處充滿台灣在地文化特色的旅遊節點。"

    # 強大的整合型 Cypher 查詢：
    # 1. 同時比對四種 Label 的名稱 (兼容 EventName 與 name)
    # 2. OPTIONAL MATCH 確保即使沒有關聯資料也不會報錯
    cypher_query = """
    MATCH (n)
    WHERE (n:Attraction OR n:Restaurant OR n:Hotel OR n:Event) 
      AND (n.name = $spot_name OR n.EventName = $spot_name)
    
    OPTIONAL MATCH (n)-[:LOCATED_IN_CITY]->(c:City)
    OPTIONAL MATCH (n)-[:HAS_TAG]->(t:Tag)
    OPTIONAL MATCH (n)-[:HAS_CUISINE]->(cu:Cuisine)
    
    RETURN 
        labels(n)[0] AS node_type,
        coalesce(n.description, n.Description) AS description,
        c.name AS city,
        collect(DISTINCT t.name) AS tags,
        collect(DISTINCT cu.name) AS cuisines
    LIMIT 1
    """

    try:
        with driver.session() as session:
            result = session.run(cypher_query, spot_name=spot_name)
            record = result.single()

            # 若查無資料的預設防呆
            if not record or not record["description"]:
                return f"【背景資訊】{spot_name} 是一處充滿在地風味的優質據點。"

            # 解析查詢結果
            node_type = record["node_type"]
            description = record["description"]
            city = record["city"] or "台灣"
            tags = [tag for tag in record["tags"] if tag]
            cuisines = [c for c in record["cuisines"] if c]

            # 動態組裝給 LLM 的上下文 (RAG Context)
            type_ch = {"Attraction": "景點", "Restaurant": "餐廳", "Hotel": "旅宿", "Event": "活動"}.get(node_type, "據點")
            
            context = f"【{city}{type_ch}特色】{description}\n"
            
            if tags:
                context += f"【精選標籤】{', '.join(tags)}\n"
            if cuisines:
                context += f"【推薦料理】{', '.join(cuisines)}\n"

            print(f"🔍 [Neo4j] 成功撈取 {spot_name} 的關聯脈絡 (類別: {node_type})")
            return context

    except Exception as e:
        print(f"❌ Neo4j 查詢失敗 ({spot_name}): {e}")
        return f"【背景資訊】{spot_name} 是一處值得探索的在地名勝。"


# ============================================================
# 2. 唯讀 Cypher 查詢服務 (供 API 外部探索使用)
# ============================================================
def execute_readonly_cypher(query: str, parameters: dict = None) -> list:
    """
    執行唯讀的 Cypher 查詢。
    內建安全防護，阻擋破壞性語法。
    """
    if parameters is None:
        parameters = {}

    # 1. 基礎防護：檢查是否有破壞性關鍵字 (轉大寫後檢查)
    forbidden_keywords = [
        "DELETE", "DETACH", "REMOVE", "SET", "CREATE", 
        "MERGE", "DROP", "CALL APOC.EXPORT", "CALL APOC.LOAD"
    ]
    upper_query = query.upper()
    
    if any(kw in upper_query for kw in forbidden_keywords):
        raise ValueError("【安全警告】為保護資料庫，此 API 僅允許讀取操作 (MATCH)。禁止修改或刪除。")

    # 2. 取得連線
    driver = _get_driver()
    if not driver:
        raise ConnectionError("Neo4j 資料庫尚未連線或未啟動。")

    # 3. 執行唯讀查詢 (execute_read)
    try:
        with driver.session() as session:
            def read_tx(tx):
                result = tx.run(query, parameters)
                return result.data()
            
            records = session.execute_read(read_tx)
            
        return records
    except Exception as e:
        raise Exception(f"Cypher 語法執行錯誤: {str(e)}")

# ============================================================
# 3. 實境劇本自動生成之節點抽樣 (供後台企劃 API 使用)
# ============================================================
def fetch_locations_for_script(town_name: str, limit: int = 4) -> list:
    """
    依據鄉鎮名稱，從資料庫中隨機撈取指定數量的真實景點/餐廳。
    用作 AI 一鍵生成實境劇本 (md_story_node) 的地標錨點。
    """
    driver = _get_driver()
    if not driver:
        raise ConnectionError("Neo4j 資料庫未連線，無法撈取實體景點。")

    query = """
    MATCH (place)-[:LOCATED_IN_TOWN]->(t:Town {name: $town_name})
    WHERE place:Attraction OR place:Restaurant
    RETURN labels(place)[0] AS type, 
           place.name AS name, 
           place.description AS description, 
           place.address AS address
    ORDER BY rand()
    LIMIT $limit
    """
    
    try:
        with driver.session() as session:
            result = session.run(query, town_name=town_name, limit=limit)
            return [dict(record) for record in result]
    except Exception as e:
        print(f"⚠️ 獲取 {town_name} 劇本地點失敗: {e}")
        return []
