from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
import uvicorn
from api.routes import router as vlog_router

app = FastAPI(
    title="智慧觀光 Vlog 引擎 (低耦合架構)",
    docs_url="/api/docs",     # 設定 Swagger UI 的對應路徑
    redoc_url="/api/redoc"    # 設定 ReDoc 的對應路徑
)

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
    # 使用 HTTP 啟動伺服器 (避開憑證問題)
    uvicorn.run("main:app", host="0.0.0.0", port=2026, reload=True)
