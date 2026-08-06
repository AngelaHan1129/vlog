
## 專案結構

```text
vlog_generator/
├── .venv/                  # 虛擬環境（不要上傳 Git）
├── assets/                 # 素材資料夾
│   ├── images/             # 存放靜態觀光照片 (例如: images.jpg)
│   ├── audio/              # 存放 TTS 旁白音檔 (例如: NHU05104289.wav)
│   └── bgm/                # 存放背景音樂 (例如: bbc_galapagos.mp3)
├── output/                 # 影片輸出資料夾 (系統生成時會自動建立與存放)
├── core/                   # 核心設定層
│   └── config.py           # 全域路徑與常數設定 (VLOG_WIDTH, FPS, DIR 等)
├── services/               # 業務邏輯層 (只做運算，不管 API)
│   ├── moviepy_service.py  # 負責 MoviePy 影片合成的背景處理邏輯
│   └── ltx_service.py      # (預留) 未來放 LTX-Video 圖生影片的 AI 邏輯
├── api/                    # 路由層 (只管接單，不管運算)
│   └── routes.py           # FastAPI 端點 (包含 /create_vlog)
├── main.py               aa  # 最乾淨的程式進入點 (負責啟動伺服器)
├── requirements.txt        # 依賴套件清單
└── .gitignore              # Git 忽略清單 (忽略 .venv 和 output 等)
```

## 1. 建立虛擬環境

### Windows（PowerShell）

```powershell
# 進入專案資料夾
cd vlog_generator

# 建立虛擬環境
python -m venv .venv

# 啟動虛擬環境
.venv\Scripts\Activate.ps1
```

### Windows（cmd）

```cmd
cd vlog_generator
python -m venv .venv
.venv\Scripts\activate
```

### macOS / Linux

```bash
cd vlog_generator
python3 -m .venv venv
source .venv/bin/activate
```

啟動成功後，終端機前面會出現 `(.venv)`。 [docs.python](https://docs.python.org/zh-tw/3/library/venv.html)

## 2. 安裝依賴

```bash
pip install moviepy
```

## 3.1. 產生 requirements.txt

```bash
pip freeze > requirements.txt
```
## 3.2. 產生 requirements.txt

```bash
pip install -r requirements.txt
```

你的 `requirements.txt` 應該會長這樣：

```txt
moviepy==2.1.1
decorator==5.1.1
imageio==2.35.1
imageio-ffmpeg==0.5.0
numpy==2.1.0
pillow==11.0.0
proglog==0.1.10
```

## 4. 之後別人要使用

別人拿到你的專案後，只需要：

```bash
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
```

## 5. .gitignore 設定

建立 `.gitignore` 檔案，避免把虛擬環境上傳到 Git：

```gitignore
# Python virtual environment
.venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
ENV/

# Output files
output/

# OS files
.DS_Store
Thumbs.db
```

## 6. 停用虛擬環境

```bash
deactivate
```

## 完整流程範例

```bash
# 1. 建立專案
mkdir vlog_generator
cd vlog_generator

# 2. 建立虛擬環境
python -m venv .venv

# 3. 啟動虛擬環境
# Windows
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

# 4. 安裝依賴
pip install moviepy

# 5. 產生 requirements.txt
pip freeze > requirements.txt

# 6. 把你的 main.py、config.py 放進來
# 7. 執行程式
python main.py

# 8. 完成後停用
deactivate
```