import os
from neo4j import GraphDatabase

_driver = None

def _get_driver():
    global _driver
    if _driver is None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "playtaiwan2026")
        try:
            _driver = GraphDatabase.driver(uri, auth=(user, password))
            _driver.verify_connectivity()
            print("✅ 成功連線至真實 Neo4j 圖形資料庫！")
        except Exception as e:
            print(f"❌ Neo4j 連線失敗: {e}")
            _driver = None
    return _driver

def execute_readonly_cypher(query: str, parameters: dict = None):
    driver = _get_driver()
    if not driver:
        raise ConnectionError("Neo4j 資料庫未連線。")

    if not query.strip().upper().startswith("MATCH"):
        raise ValueError("安全性限制：僅允許執行 MATCH 查詢語法。")

    with driver.session() as session:
        result = session.run(query, parameters or {})
        return [dict(record) for record in result]

def search_neo4j_rag(keyword: str, **kwargs) -> str:
    """
    根據關鍵字檢索 Neo4j 中的在地知識。
    使用 **kwargs 接收其他未使用的參數（如 is_night_mode 等），避免多餘參數傳入時報錯。
    """
    driver = _get_driver()
    if not driver:
        return "Neo4j 未連線，無法提供在地背景知識。"

    query = """
    MATCH (n)
    WHERE n.name CONTAINS $keyword OR n.EventName CONTAINS $keyword
    RETURN COALESCE(n.name, n.EventName) AS name,
           COALESCE(n.description, n.Description, "暫無介紹") AS desc,
           COALESCE(n.address, n.TrafficInfo, "無地址") AS addr
    LIMIT 3
    """
    try:
        with driver.session() as session:
            result = session.run(query, keyword=keyword)
            contexts = []
            for record in result:
                contexts.append(f"地點: {record['name']}\n地址: {record['addr']}\n介紹: {record['desc'][:200]}...")
            return "\n---\n".join(contexts) if contexts else "查無相關在地知識。"
    except Exception as e:
        return f"RAG 檢索發生錯誤: {e}"

def fetch_locations_for_script(town_name: str, limit: int = 4, is_night: bool = False) -> list:
    """
    動態旅遊動線規劃：
    - 白天模式：依據 limit 動態分配 [景點, 餐廳, 景點, 旅宿]
    - 夜間模式：優先撈取夜間活動、餐廳或旅宿相關節點
    """
    driver = _get_driver()
    if not driver:
        raise ConnectionError("Neo4j 資料庫未連線，無法撈取實體景點。")

    query_template = """
    MATCH (place)-[:LOCATED_IN_TOWN]->(t:Town {name: $town_name})
    WHERE place:%s
    OPTIONAL MATCH (place)-[:HAS_TAG]->(tag:Tag)
    OPTIONAL MATCH (place)-[:HAS_CUISINE]->(cu:Cuisine)
    RETURN labels(place)[0] AS type,
           COALESCE(place.name, "未知名稱") AS name,
           COALESCE(place.description, "暫無介紹") AS description,
           COALESCE(place.address, "無地址") AS address,
           place.ticket_info AS ticket_info,
           collect(DISTINCT tag.name) AS tags,
           collect(DISTINCT cu.name) AS cuisines
    ORDER BY rand()
    LIMIT 1
    """

    target_labels = []

    if is_night:
        target_labels = ["Restaurant", "Attraction", "Hotel"]
        while len(target_labels) < limit:
            target_labels.insert(1, "Attraction")
        target_labels = target_labels[:limit]
    else:
        if limit == 1:
            target_labels = ["Attraction"]
        elif limit == 2:
            target_labels = ["Attraction", "Restaurant"]
        elif limit == 3:
            target_labels = ["Attraction", "Restaurant", "Hotel"]
        else:
            target_labels.append("Attraction")
            middle_count = limit - 2
            restaurant_count = max(1, middle_count // 2)
            attraction_count = middle_count - restaurant_count
            for _ in range(attraction_count):
                target_labels.append("Attraction")
            for _ in range(restaurant_count):
                target_labels.append("Restaurant")
            target_labels.append("Hotel")

    while len(target_labels) < limit:
        target_labels.insert(1, "Attraction")
    target_labels = target_labels[:limit]

    combined_locations = []
    try:
        with driver.session() as session:
            for label in target_labels:
                current_query = query_template % label
                result = session.run(current_query, town_name=town_name)
                record = result.single()
                if record:
                    combined_locations.append(dict(record))
                else:
                    fb_result = session.run(query_template % "Attraction", town_name=town_name)
                    fb_record = fb_result.single()
                    if fb_record:
                        combined_locations.append(dict(fb_record))

        print(f"📍 [Neo4j] 為 {town_name} ('夜間模式'={is_night}) 規劃了 {len(combined_locations)} 站動線: {target_labels}")
        return combined_locations
    except Exception as e:
        print(f"⚠️ 動態獲取劇本地點失敗: {e}")
        return []
