# YT-Sum 知識導航儀

一套跑在本地端的 **YouTube 知識導航 Web App**（Next.js + FastAPI + Google Gemini API）。
不同於傳統只做「時間軸＋章節摘要」的工具，本專案專注於拆解理解影片所需的知識結構：

1. **第一層：前置必備觀念（掃雷區）**：點出沒先搞懂就容易卡住的觀念、原因與 1 分鐘白話科普，支援「我已掌握」過濾。
2. **第二層：影片核心觀念（知識骨幹）**：拆解重點與影片實例，點擊 `[mm:ss]` 時間戳記即可控制左側內嵌播放器跳轉。
3. **第三層：延伸與深入研究（探索樹）**：提供縱向深究與橫向延伸方向，支援**APP 內建追問**與**一鍵複製 Prompt 帶去 Gemini 網頁版**。
4. **附加實用工具**：支援 `yt-dlp + ffmpeg` 下載 MP4 / MP3（無字幕影片亦會自動透過音訊交由 Gemini 分析）、以及一鍵匯出 `.md` 筆記。

---

## 專案結構

```text
yt-sum/
├── backend/                  # Python FastAPI 後端 (localhost:8000)
│   ├── main.py               # API 入口 (/api/analyze, /api/chat, /api/download, /api/health)
│   ├── schemas.py            # Gemini Structured Output Pydantic 模型
│   └── services/
│       ├── youtube_service.py # 字幕抓取、yt-dlp + ffmpeg 下載與音訊擷取
│       └── gemini_service.py  # Google Gemini API 串接
├── frontend/                 # Next.js (App Router + Tailwind) 前端 (localhost:3000)
└── start.ps1                 # Windows 一鍵啟動腳本
```

---

## 快速啟動

### Windows 使用者

1. **設定 Gemini API Key**：
   複製 `backend/.env.example` 為 `backend/.env`，填入你的 `GEMINI_API_KEY`（也可以啟動後直接在網頁右上角 **Key** 按鈕輸入）。
2. **一鍵啟動**：
   - **一般使用（推薦）**：雙擊 `run_app.bat`，會自動啟動後端並開啟 `http://localhost:8000`（使用預編譯前端，無需啟動 Node.js）。
   - **開發模式（前後端熱重載）**：執行 `.\start.ps1`，並開啟 `http://localhost:3000`。

### macOS 使用者（免裝 Node.js）

1. **前置環境**：確認 Mac 已安裝 Python 3.10+（可透過 `brew install python` 或 [python.org](https://www.python.org/downloads/) 安裝）；若需要下載 MP3 或 1080p+ MP4，建議同步安裝 `brew install ffmpeg`。
2. **一鍵啟動**：直接雙擊 `run_app.command`，首次會自動建立虛擬環境、安裝依賴並開啟 `http://localhost:8000`。
3. **初次授權（若 macOS 提示無法打開或沒有權限）**：
   - 方法一：對 `run_app.command` **按住 Control 鍵點選（右鍵）→ 打開**。
   - 方法二：在終端機切換到專案資料夾後執行：
     ```bash
     chmod +x run_app.command
     ./run_app.command
     ```

---

## 安裝為桌面 PWA App

本專案已支援 **PWA（Progressive Web App）**，可安裝成獨立無網址列的桌面視窗（使用時仍需保持 `run_app.bat` 或 `run_app.command` 在背景執行）：

- **Windows / macOS（Chrome / Edge）**：開啟 `http://localhost:8000` 後，點擊右上角 **「安裝 App」** 按鈕（或網址列右側的安裝圖示）。
- **macOS Safari（macOS Sonoma 以上）**：開啟 `http://localhost:8000` 後，點選 Safari 上方選單列 **「檔案 → 加入 Dock」**（或點擊網頁右上角「安裝 App」查看指引）。

---

## 打包分享給 Mac 朋友（Windows 端）

若你修改了程式或想將含共用 API Key 的可攜版私下傳給使用 Mac 的朋友，可在 Windows 專案根目錄執行：

```powershell
.\pack_for_mac.ps1
```

腳本會自動排除 `.venv`、`node_modules`、`data/` 與快取，產出乾淨的 `YT-Sum-macOS-portable.zip`，並詢問是否將你的 `backend/.env`（共用 API Key）一併包入。

> ⚠️ **安全提醒**：若選擇將 `backend/.env` 包入壓縮檔，請**僅限私下傳送**給信任的朋友，切勿上傳至公開網路或 Git 儲存庫。
