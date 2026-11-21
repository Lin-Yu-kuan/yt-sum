# YT-Sum 知識導航儀

一套跑在本地端的 **YouTube 知識導航 Web App**（Next.js + FastAPI + Google Gemini API）。
不同於傳統只做「時間軸＋章節摘要」的工具，本專案專注於拆解理解影片所需的知識結構：

1. **第一層：前置必備觀念（掃雷區）**：點出沒先搞懂就容易卡住的觀念、原因與 1 分鐘白話科普，支援「我已掌握」過濾。
2. **第二層：影片核心觀念（知識骨幹）**：拆解重點與影片實例，點擊 `[mm:ss]` 時間戳記即可控制左側內嵌播放器跳轉。
3. **第三層：延伸與深入研究（探索樹）**：提供縱向深究與橫向延伸方向，支援**APP 內建追問**與**一鍵複製 Prompt 帶去 Gemini 網頁版**。
4. **附加實用工具**：支援 `yt-dlp + ffmpeg` 下載 MP4 / MP3（無字幕影片亦會自動透過音訊交由 Gemini 分析）、以及一鍵匯出 `.md` 筆記。

---

## 一鍵下載安裝（最推薦，免裝 Node.js）

> **前置需求**：電腦僅需有 **Python 3.10 以上版本**（Windows 若尚未安裝，腳本可協助透過 `winget` 一鍵安裝；macOS 可用 `brew install python` 或 [python.org](https://www.python.org/downloads/)）。**一般使用不需要安裝 Node.js**。

### Windows 一鍵安裝（PowerShell）

打開 Windows「**終端機**」或「**PowerShell**」，貼上並執行以下指令：

```powershell
irm https://raw.githubusercontent.com/Lin-Yu-kuan/yt-sum/main/install.ps1 | iex
```

### macOS 一鍵安裝（終端機 Terminal）

打開 macOS「**終端機（Terminal）**」，貼上並執行以下指令：

```bash
curl -fsSL https://raw.githubusercontent.com/Lin-Yu-kuan/yt-sum/main/install.sh | bash
```

### 一鍵腳本會自動完成什麼？

1. **檢查 Python 3.10+** 環境。
2. **下載最新版 YT-Sum** 至你的個人資料夾（預設為 `~/YT-Sum`，Windows 約為 `C:\Users\<你的名稱>\YT-Sum`）。
3. **自動建立虛擬環境並安裝必要 Python 套件**（完全不影響系統其他 Python 專案）。
4. **詢問是否開啟「背景常駐模式」**（推薦選 `Y`，開機即在背景無聲啟動後端，之後直接點桌面 App 就能用）。
5. **啟動服務並自動開啟** `http://localhost:8000`。

### 一鍵更新 & 自訂安裝路徑

- **更新至最新版**：重新執行上面同一行安裝指令即可，腳本會自動更新程式與預編譯前端，並**完整保留你的 `data/` 歷史筆記與 `backend/.env` API Key**。
- **自訂安裝資料夾**（選用）：可在執行前設定 `YTSUM_DIR` 環境變數：
  - Windows PowerShell：`$env:YTSUM_DIR="D:\Apps\YT-Sum"; irm https://raw.githubusercontent.com/Lin-Yu-kuan/yt-sum/main/install.ps1 | iex`
  - macOS Terminal：`YTSUM_DIR="$HOME/Applications/YT-Sum" curl -fsSL https://raw.githubusercontent.com/Lin-Yu-kuan/yt-sum/main/install.sh | bash`

---

## 第一次開啟：30 秒完成設定

1. **填入 Gemini API Key**：開啟 `http://localhost:8000` 後，點擊右上角 **Key** 按鈕，貼上從 [Google AI Studio](https://aistudio.google.com/) 申請的免費 API Key（會自動永久儲存在本機 `backend/.env`）。
2. **安裝為桌面獨立 App（PWA）**：點擊網頁右上角 **「安裝 App」**（Chrome / Edge），或使用 Safari 選單列 **「檔案 → 加入 Dock」**。
3. **選用：安裝 FFmpeg（下載 MP3 / 1080p+ MP4 用）**：核心 AI 知識分析不需 FFmpeg 即可運作；若需要高畫質合併或轉檔 MP3，請執行：
   - **Windows**：`winget install Gyan.FFmpeg`
   - **macOS**：`brew install ffmpeg`

---

## 不想開終端機？免指令下載方式

若不習慣使用終端機指令，也可以直接下載壓縮檔手動啟動：

1. **[點此下載 YT-Sum 最新版 ZIP](https://github.com/Lin-Yu-kuan/yt-sum/archive/refs/heads/main.zip)**，解壓縮到自己喜歡的資料夾（例如桌面或文件資料夾）。
2. 確認已安裝 Python 3.10+ 後，直接雙擊啟動腳本：
   - **Windows**：
     - 雙擊 `install_autostart.bat`（安裝背景常駐並立刻啟動，推薦搭配桌面 PWA）
     - 或雙擊 `run_app.bat`（單次開啟小黑框執行，關閉視窗即停止）
   - **macOS**：
     - 雙擊 `install_autostart.command`（安裝登入自動啟動 LaunchAgent 並立刻啟動）
     - 或雙擊 `run_app.command`（單次開啟終端機執行）
   - **macOS 初次授權（若提示無法打開或沒有權限）**：
     - 方法一：對 `.command` 檔案**按住 Control 鍵點選（右鍵）→ 打開**。
     - 方法二：在終端機切換到解壓後的資料夾執行：
       ```bash
       xattr -dr com.apple.quarantine .
       chmod +x *.command
       ./run_app.command
       ```

---

## 安裝為桌面 PWA App

本專案已支援 **PWA（Progressive Web App）**，可安裝成獨立無網址列的桌面視窗：

- **Windows / macOS（Chrome / Edge）**：開啟 `http://localhost:8000` 後，點擊右上角 **「安裝 App」** 按鈕（或網址列右側的安裝圖示）。
- **macOS Safari（macOS Sonoma 以上）**：開啟 `http://localhost:8000` 後，點選 Safari 上方選單列 **「檔案 → 加入 Dock」**（或點擊網頁右上角「安裝 App」查看指引）。
- **離線唯讀快取**：只要在連線狀態下瀏覽或開啟過的歷史筆記，即使暫時關閉後端服務，桌面 PWA 仍可讀取瀏覽器快取中的清單與筆記（唯讀）；啟動後端後約 3 秒會自動重連同步。

---

## 背景常駐管理與移除

桌面 PWA 仍需要本機的 Python FastAPI 後端提供 AI 解析與下載能力。安裝時若略過背景常駐，或日後想調整／移除，可使用資料夾內的腳本：

- **Windows**：
  - 安裝開機無黑框背景常駐並立即啟動：雙擊 `install_autostart.bat`（或執行 `powershell -ExecutionPolicy Bypass -File .\install_autostart.ps1`）
  - 停止並移除開機常駐：雙擊 `uninstall_autostart.bat`（或執行 `powershell -ExecutionPolicy Bypass -File .\uninstall_autostart.ps1`）
- **macOS**：
  - 安裝登入自動啟動 LaunchAgent 並立即啟動：雙擊 `install_autostart.command`
  - 停止並移除背景常駐：雙擊 `uninstall_autostart.command`
- **完全移除專案**：先執行一次對應平台的 `uninstall_autostart` 腳本停止背景服務與開機啟動項目，再將整個安裝資料夾（預設 `~/YT-Sum`）刪除即可。

---

## 開發者模式（前後端熱重載）

若你要修改前端或後端程式碼並進行開發：

1. **取得原始碼**：
   ```bash
   git clone https://github.com/Lin-Yu-kuan/yt-sum.git
   cd yt-sum
   ```
2. **設定環境與啟動**：
   - 複製 `backend/.env.example` 為 `backend/.env`，填入 `GEMINI_API_KEY`（也可以啟動後在網頁右上角 **Key** 輸入）。
   - 確認本機 `backend/.venv` 與 `frontend/node_modules` 已就緒後，在 Windows 執行：
     ```powershell
     .\start.ps1
     ```
     並開啟 `http://localhost:3000`（FastAPI 後端運行於 `http://localhost:8000`）。
3. **同步預編譯前端**：由於一鍵安裝版與 `run_app.*` 直接掛載 `frontend/out/` 靜態輸出，若修改了 `frontend/` 程式碼，提交前請先執行建置：
   ```bash
   cd frontend
   npm run build
   ```

---

## 專案結構

```text
yt-sum/
├── install.ps1                  # Windows 一鍵下載安裝／更新腳本
├── install.sh                   # macOS / Unix 一鍵下載安裝／更新腳本
├── run_app.bat                  # Windows 單次啟動腳本
├── run_app.command              # macOS 單次啟動腳本
├── install_autostart.bat        # Windows 背景常駐安裝入口
├── install_autostart.ps1        # Windows 背景常駐安裝邏輯
├── install_autostart.command    # macOS LaunchAgent 背景常駐安裝腳本
├── uninstall_autostart.bat      # Windows 移除背景常駐入口
├── uninstall_autostart.ps1      # Windows 移除背景常駐邏輯
├── uninstall_autostart.command  # macOS 移除背景常駐腳本
├── start.ps1                    # Windows 開發模式（前後端熱重載）
├── pack_for_mac.ps1             # Windows 打包 macOS 可攜版 ZIP 工具
├── backend/                     # Python FastAPI 後端 (localhost:8000)
│   ├── main.py                  # API 入口與靜態前端掛載
│   ├── schemas.py               # Gemini Structured Output Pydantic 模型
│   ├── .env.example             # 環境變數範本
│   ├── requirements.txt         # Python 相依套件清單
│   └── services/
│       ├── youtube_service.py   # 字幕抓取、yt-dlp + ffmpeg 下載與音訊擷取
│       ├── gemini_service.py    # Google Gemini API 串接
│       └── history_service.py   # 本機歷史筆記儲存管理
└── frontend/                    # Next.js (App Router + Tailwind) 前端
    ├── src/                     # 前端原始碼 (開發模式 localhost:3000)
    └── out/                     # 預編譯靜態前端（供一鍵啟動與 PWA 使用）
```

---

## 打包分享給 Mac 朋友（Windows 端）

若你修改了程式或想將含共用 API Key 的可攜版私下傳給使用 Mac 的朋友，可在 Windows 專案根目錄執行：

```powershell
.\pack_for_mac.ps1
```

腳本會自動排除 `.venv`、`node_modules`、`data/` 與快取，產出乾淨的 `YT-Sum-macOS-portable.zip`，並詢問是否將你的 `backend/.env`（共用 API Key）一併包入。

> ⚠️ **安全提醒**：若選擇將 `backend/.env` 包入壓縮檔，請**僅限私下傳送**給信任的朋友，切勿上傳至公開網路或 Git 儲存庫。
