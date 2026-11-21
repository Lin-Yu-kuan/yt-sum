#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:$PATH"

REPO_URL="https://github.com/Lin-Yu-kuan/yt-sum.git"
ZIP_URL="https://github.com/Lin-Yu-kuan/yt-sum/archive/refs/heads/main.zip"
INSTALL_DIR="${YTSUM_DIR:-$HOME/YT-Sum}"
OS_NAME="$(uname -s)"

TTY_OK=0
if ( : </dev/tty ) 2>/dev/null; then
    TTY_OK=1
fi

has_clt() {
    if [ "$OS_NAME" != "Darwin" ]; then
        return 0
    fi
    xcode-select -p >/dev/null 2>&1
}

prompt_yes_no() {
    local prompt="$1"
    local default_ans="${2:-Y}"
    local ans=""

    if [ "$TTY_OK" -eq 0 ]; then
        [ "$default_ans" = "Y" ] && return 0 || return 1
    fi

    printf "%s " "$prompt" >/dev/tty
    IFS= read -r ans </dev/tty || ans=""
    if [ -z "$ans" ]; then
        [ "$default_ans" = "Y" ] && return 0 || return 1
    fi
    case "$ans" in
        [Yy]|[Yy][Ee][Ss]) return 0 ;;
        *) return 1 ;;
    esac
}

resolve_optional_bool() {
    local val="${1:-}"
    case "$val" in
        1|true|TRUE|y|Y|yes|YES) echo "1" ;;
        0|false|FALSE|n|N|no|NO) echo "0" ;;
        *) echo "" ;;
    esac
}

find_python310() {
    local clt_ok=1
    if ! has_clt; then
        clt_ok=0
    fi

    local candidates=(
        "/opt/homebrew/bin/python3"
        "/usr/local/bin/python3"
        "/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
    )

    local fw_dir
    for fw_dir in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3; do
        if [ -x "$fw_dir" ]; then
            candidates+=("$fw_dir")
        fi
    done

    local cmd resolved
    for cmd in python3 python3.13 python3.12 python3.11 python3.10; do
        if command -v "$cmd" >/dev/null 2>&1; then
            resolved="$(command -v "$cmd")"
            candidates+=("$resolved")
        fi
    done

    local seen=""
    local cand
    for cand in "${candidates[@]}"; do
        [ -x "$cand" ] || continue
        case " $seen " in
            *" $cand "*) continue ;;
        esac
        seen="$seen $cand"

        # macOS 尚未安裝 Xcode Command Line Tools 時，呼叫 /usr/bin/python3 會彈出安裝提示框
        if [ "$OS_NAME" = "Darwin" ] && [ "$clt_ok" -eq 0 ] && [ "$cand" = "/usr/bin/python3" ]; then
            continue
        fi

        if "$cand" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
            echo "$cand"
            return 0
        fi
    done
    return 1
}

echo "=== YT-Sum 知識導航儀一鍵安裝程式 ==="
echo "安裝目錄：$INSTALL_DIR"

# Step 1: 偵測 Python 3.10+
echo ""
echo "[1/5] 檢查 Python 3.10 以上版本..."
PYTHON_BIN="$(find_python310 || true)"

if [ -z "$PYTHON_BIN" ]; then
    if command -v brew >/dev/null 2>&1 && [ "$TTY_OK" -eq 1 ]; then
        if prompt_yes_no "找不到 Python 3.10+。是否透過 Homebrew 自動安裝 Python？[Y/n]" "Y"; then
            echo "正在執行 brew install python..."
            brew install python
            PYTHON_BIN="$(find_python310 || true)"
        fi
    fi
fi

if [ -z "$PYTHON_BIN" ]; then
    echo "[錯誤] 找不到可用的 Python 3.10 以上版本。"
    echo "請先安裝 Python 3.10+ 後再重新執行本指令："
    if [ "$OS_NAME" = "Darwin" ]; then
        echo "  方法 1 (Homebrew)：brew install python"
        echo "  方法 2 (官方安裝檔)：https://www.python.org/downloads/"
    else
        echo "  請使用系統套件管理器安裝 python3 (>= 3.10) 與 python3-venv，或前往 https://www.python.org/downloads/"
    fi
    exit 1
fi

PY_VER="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}")')"
echo "已找到 Python $PY_VER ($PYTHON_BIN)"

# Step 2: 下載或更新 YT-Sum
echo ""
echo "[2/5] 下載 / 更新 YT-Sum..."
HAS_REAL_GIT=0
if [ "${YTSUM_FORCE_ZIP:-0}" != "1" ] && command -v git >/dev/null 2>&1; then
    GIT_PATH="$(command -v git)"
    if [ "$OS_NAME" != "Darwin" ] || has_clt || [ "$GIT_PATH" != "/usr/bin/git" ]; then
        HAS_REAL_GIT=1
    fi
fi

if [ "$HAS_REAL_GIT" -eq 1 ] && [ -d "$INSTALL_DIR/.git" ]; then
    echo "偵測到 Git 安裝，正在透過 git pull --ff-only 更新..."
    git -C "$INSTALL_DIR" pull --ff-only
elif [ "$HAS_REAL_GIT" -eq 1 ] && [ ! -e "$INSTALL_DIR" ]; then
    mkdir -p "$(dirname "$INSTALL_DIR")"
    echo "正在透過 git clone 下載至 $INSTALL_DIR..."
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
else
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT
    TMP_ZIP="$TMP_DIR/yt-sum.zip"
    EXTRACT_DIR="$TMP_DIR/extract"
    mkdir -p "$EXTRACT_DIR"

    echo "正在從 GitHub 下載最新版本壓縮檔..."
    curl -fsSL "$ZIP_URL" -o "$TMP_ZIP"

    if command -v ditto >/dev/null 2>&1; then
        ditto -xk "$TMP_ZIP" "$EXTRACT_DIR"
    elif command -v unzip >/dev/null 2>&1; then
        unzip -q "$TMP_ZIP" -d "$EXTRACT_DIR"
    else
        "$PYTHON_BIN" -m zipfile -e "$TMP_ZIP" "$EXTRACT_DIR"
    fi

    SRC_DIR="$EXTRACT_DIR/yt-sum-main"
    if [ ! -f "$SRC_DIR/backend/main.py" ]; then
        SRC_DIR=""
        for d in "$EXTRACT_DIR"/*; do
            if [ -d "$d" ] && [ -f "$d/backend/main.py" ]; then
                SRC_DIR="$d"
                break
            fi
        done
    fi

    if [ -z "$SRC_DIR" ] || [ ! -f "$SRC_DIR/backend/main.py" ]; then
        echo "[錯誤] 解壓後的壓縮檔結構不完整（找不到 backend/main.py）。"
        exit 1
    fi

    mkdir -p "$INSTALL_DIR"
    rm -rf "$INSTALL_DIR/frontend/out"

    YT_SRC_DIR="$SRC_DIR" YT_INSTALL_DIR="$INSTALL_DIR" "$PYTHON_BIN" - <<'PYEOF'
import os
import shutil
from pathlib import Path

src_root = Path(os.environ["YT_SRC_DIR"])
dst_root = Path(os.environ["YT_INSTALL_DIR"])

skip_root_dirs = {"data"}
skip_backend_items = {".env", ".venv", "cookies.txt", "downloads"}
skip_frontend_dirs = {"node_modules", ".next"}

for root, dirs, files in os.walk(src_root):
    rel_dir = Path(root).relative_to(src_root)
    parts = rel_dir.parts

    if not parts:
        dirs[:] = [d for d in dirs if d not in skip_root_dirs]
    elif parts[0] == "backend" and len(parts) == 1:
        dirs[:] = [d for d in dirs if d not in skip_backend_items]
    elif parts[0] == "frontend" and len(parts) == 1:
        dirs[:] = [d for d in dirs if d not in skip_frontend_dirs]

    target_dir = dst_root / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    for fname in files:
        if parts == ("backend",) and fname in skip_backend_items:
            continue
        shutil.copy2(Path(root) / fname, target_dir / fname)
PYEOF
    echo "檔案已同步至 $INSTALL_DIR（完整保留原有的 .env、.venv 與 data/ 紀錄）。"
fi

chmod +x "$INSTALL_DIR"/*.command "$INSTALL_DIR/install.sh" 2>/dev/null || true
if [ "$OS_NAME" = "Darwin" ] && command -v xattr >/dev/null 2>&1; then
    xattr -dr com.apple.quarantine "$INSTALL_DIR" >/dev/null 2>&1 || true
fi

# Step 3: 建立 / 更新虛擬環境與套件
echo ""
echo "[3/5] 設定 Python 虛擬環境與相依套件..."
BACKEND_DIR="$INSTALL_DIR/backend"
cd "$BACKEND_DIR"

if [ ! -x ".venv/bin/python" ]; then
    "$PYTHON_BIN" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp ".env.example" ".env"
fi

# Step 4: 檢查選用元件 ffmpeg
echo ""
echo "[4/5] 檢查選用元件 FFmpeg..."
if command -v ffmpeg >/dev/null 2>&1; then
    echo "[OK] 已偵測到 FFmpeg，完整支援 MP4/MP3 下載與無字幕音訊分析。"
else
    echo "[提示] 尚未安裝 FFmpeg（選用）。核心 AI 知識分析已可正常使用；"
    if [ "$OS_NAME" = "Darwin" ]; then
        echo "       若之後需要下載 MP3 或 1080p+ 高畫質 MP4，請執行：brew install ffmpeg"
    else
        echo "       若之後需要下載 MP3 或 1080p+ 高畫質 MP4，請使用系統套件管理器安裝 ffmpeg。"
    fi
fi

# Step 5: 啟動服務
echo ""
echo "[5/5] 設定啟動方式..."
if [ "$OS_NAME" = "Darwin" ]; then
    AUTOSTART_CHOICE="$(resolve_optional_bool "${YTSUM_AUTOSTART:-}")"
    if [ -z "$AUTOSTART_CHOICE" ]; then
        if prompt_yes_no "是否安裝登入自動啟動背景常駐服務（免開終端機，適合搭配桌面 PWA）？[Y/n]" "Y"; then
            AUTOSTART_CHOICE="1"
        else
            AUTOSTART_CHOICE="0"
        fi
    fi

    if [ "$AUTOSTART_CHOICE" = "1" ]; then
        YTSUM_NO_PAUSE=1 YTSUM_NO_OPEN="${YTSUM_NO_OPEN:-0}" bash "$INSTALL_DIR/install_autostart.command" --no-pause
    else
        echo "已略過背景常駐。之後隨時可到 $INSTALL_DIR 雙擊 run_app.command 啟動。"
        if [ "${YTSUM_NO_OPEN:-0}" != "1" ] && [ "$TTY_OK" -eq 1 ]; then
            if prompt_yes_no "現在就開啟 YT-Sum 嗎？[Y/n]" "Y"; then
                open "$INSTALL_DIR/run_app.command" >/dev/null 2>&1 || true
            fi
        fi
    fi
else
    echo "非 macOS 環境，請執行以下指令啟動後端服務："
    echo "  cd \"$BACKEND_DIR\" && .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000"
fi

# Step 6: 完成摘要
echo ""
echo "=== 安裝完成！ ==="
echo "安裝位置：$INSTALL_DIR"
echo "服務網址：http://localhost:8000"
echo ""
echo "初次使用 30 秒設定："
echo "  1. 點擊網頁右上角「Key」按鈕，填入免費 Gemini API Key (https://aistudio.google.com/)"
echo "  2. 點擊「安裝 App」（Chrome/Edge）或 Safari「檔案 → 加入 Dock」安裝為桌面 PWA"
echo ""
echo "日後要更新至最新版本（會保留所有筆記與 API Key），重新執行同一行安裝指令即可："
echo "  curl -fsSL https://raw.githubusercontent.com/Lin-Yu-kuan/yt-sum/main/install.sh | bash"
