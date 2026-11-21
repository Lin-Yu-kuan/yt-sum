#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

# 補充 Homebrew (Apple Silicon / Intel) 與常見 Python 安裝路徑
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:$PATH"

echo "=== YT-Sum 知識導航儀 (macOS) ==="

if [ ! -d "$BACKEND_DIR" ]; then
    echo "[錯誤] 找不到 backend 資料夾，請確認檔案結構完整。"
    read -r -p "按 Enter 鍵關閉..."
    exit 1
fi

cd "$BACKEND_DIR"

# 尋找 Python 3.10 以上版本
PYTHON_BIN=""
for candidate in python3 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
            PYTHON_BIN="$(command -v "$candidate")"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[錯誤] 找不到 Python 3.10 以上版本。"
    echo "請先安裝 Python 3.10+："
    echo "  方法 1 (Homebrew)：brew install python"
    echo "  方法 2 (官方安裝檔)：https://www.python.org/downloads/"
    read -r -p "按 Enter 鍵關閉..."
    exit 1
fi

echo "[1/4] 使用 Python：$PYTHON_BIN"

if [ ! -x ".venv/bin/python" ]; then
    echo "[2/4] 首次啟動：建立虛擬環境並安裝必要套件（約需 1~2 分鐘）..."
    "$PYTHON_BIN" -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
else
    echo "[2/4] Python 虛擬環境已就緒。"
fi

if command -v ffmpeg >/dev/null 2>&1; then
    echo "[3/4] 已偵測到 ffmpeg，完整支援 MP4/MP3 下載與無字幕音訊分析。"
else
    echo "[提示] 尚未安裝 ffmpeg。核心知識分析可正常使用；"
    echo "       若需下載 MP3 或高畫質 MP4，請於終端機執行：brew install ffmpeg"
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp ".env.example" ".env"
    echo "[提示] 已建立 backend/.env，稍後可於網頁右上角 Key 按鈕輸入 Gemini API Key。"
fi

echo "[4/4] 啟動伺服器於 http://localhost:8000 ..."
(
    for _ in $(seq 1 30); do
        if curl -sf "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
    open "http://localhost:8000"
) &

echo "服務運作中（關閉此終端機視窗即停止服務）。"
exec .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
