from fastapi import FastAPI
import uvicorn
from api.routes import router as vlog_router

app = FastAPI(title="智慧觀光 Vlog 引擎 (低耦合架構)")

# 將 api/routes.py 寫好的端點掛載上來
app.include_router(vlog_router, prefix="/api")

if __name__ == "__main__":
    # 使用 HTTP 啟動伺服器 (避開憑證問題)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)