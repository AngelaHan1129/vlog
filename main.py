import os
import subprocess
import requests
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
import uvicorn
from api.routes import router as vlog_router

app = FastAPI(
    title="智慧觀光 Vlog 引擎 (低耦合架構)",
    docs_url="/api/docs",     # 設定 Swagger UI 的對應路徑
    redoc_url="/api/redoc"    # 設定 ReDoc 的對應路徑
)

# --- 自動檢查並啟動 ComfyUI 服務的事件 ---
@app.on_event("startup")
async def startup_event():
    comfy_url = "http://127.0.0.1:8188"
    try:
        # 測試 ComfyUI 是否已經在運行
        response = requests.get(comfy_url, timeout=2)
        if response.status_code == 200:
            print("🎨 [ComfyUI] 偵測到 ComfyUI 已經在背景運行中！")
    except requests.exceptions.ConnectionError:
        print("⚠️ [ComfyUI] 尚未啟動，正在嘗試自動啟動 ComfyUI (Port 8188)...")
        comfy_dir = "/home/jackstar/playtaiwan/ComfyUI"
        if os.path.exists(comfy_dir):
            # 在背景啟動 ComfyUI
            subprocess.Popen(
                ["python", "main.py"],
                cwd=comfy_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            print("🚀 [ComfyUI] 已成功於背景自動啟動！")
        else:
            print(f"❌ 找不到 ComfyUI 資料夾：{comfy_dir}，請確認路徑。")

# 強制修正 OpenAPI 規格，確保檔案上傳元件在 Swagger 中正確渲染，避免顯示亂碼
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version="0.1.0",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# 將 api/routes.py 寫好的端點掛載上來
app.include_router(vlog_router, prefix="/api")

if __name__ == "__main__":
    # 使用 HTTP 啟動伺服器 (Port 2026)
    uvicorn.run("main:app", host="0.0.0.0", port=2026, reload=True)
