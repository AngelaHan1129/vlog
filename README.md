# 建立虛擬環境
python -m venv .venv

# 啟動虛擬環境
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 安裝依賴
pip install -r requirements.txt

# 執行程式
python main.py