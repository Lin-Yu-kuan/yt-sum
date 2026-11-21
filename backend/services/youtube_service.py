import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, quote, urlparse

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi


PREFERRED_LANGS = ["zh-TW", "zh-Hant", "zh", "zh-Hans", "zh-CN", "en", "en-US", "ja"]
BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent
DEFAULT_COOKIES_PATHS = (
    PROJECT_ROOT / "data" / "cookies.txt",
    BACKEND_ROOT / "cookies.txt",
)
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


class DownloadPausedError(Exception):
    """使用者暫停下載"""


class DownloadCancelledError(Exception):
    """使用者終止下載"""


@dataclass
class VideoMetadata:
    video_id: str
    title: str
    channel: str
    duration_seconds: int
    chapters: list[dict] = field(default_factory=list)


@dataclass
class TranscriptResult:
    text: str
    source_label: str
    language_code: str
    snippets: list[dict]


def has_ffmpeg() -> bool:
    """檢查系統是否已安裝 ffmpeg"""
    return shutil.which("ffmpeg") is not None


def strip_ansi(text: str) -> str:
    """移除終端機 ANSI 控制字元（例如 [0;31m）"""
    return ANSI_ESCAPE_RE.sub("", text or "").strip()


def format_ytdlp_error(raw_error: str) -> str:
    """清理 yt-dlp 錯誤訊息並提供明確的繁體中文指引"""
    cleaned = strip_ansi(raw_error)
    lower = cleaned.lower()
    if "sign in to confirm" in lower or "not a bot" in lower:
        return (
            "YouTube 觸發反機器人驗證（Sign in to confirm you're not a bot），"
            "目前無法透過本機 IP 直接存取串流。建議先關閉 VPN 或稍後再試；"
            "若需使用 MP4/MP3 下載功能，請將瀏覽器匯出的 cookies.txt 放置於 "
            "`data/cookies.txt`（或 `backend/cookies.txt`），"
            "或在 `backend/.env` 設定 `YOUTUBE_COOKIES_FILE` / `YOUTUBE_COOKIES_FROM_BROWSER`。"
        )
    return cleaned or "yt-dlp 執行失敗"


def resolve_ytdlp_cookie_source() -> tuple[str, str] | None:
    """依序偵測環境變數與預設路徑中的 YouTube Cookies 設定"""
    env_file = (os.getenv("YOUTUBE_COOKIES_FILE") or "").strip()
    if env_file:
        cookie_path = Path(env_file).expanduser()
        if cookie_path.is_file():
            return ("file", str(cookie_path))

    for candidate in DEFAULT_COOKIES_PATHS:
        if candidate.is_file():
            return ("file", str(candidate))

    browser = (os.getenv("YOUTUBE_COOKIES_FROM_BROWSER") or "").strip()
    if browser:
        return ("browser", browser)
    return None


def has_configured_cookies() -> bool:
    """回報目前是否已偵測到可用的 YouTube Cookies 設定"""
    return resolve_ytdlp_cookie_source() is not None


def _apply_ytdlp_cookie_opts(ydl_opts: dict) -> dict:
    """為 yt_dlp.YoutubeDL options 套用可用的 Cookies 設定"""
    source = resolve_ytdlp_cookie_source()
    if not source:
        return ydl_opts
    kind, value = source
    if kind == "file":
        ydl_opts["cookiefile"] = value
    elif kind == "browser":
        ydl_opts["cookiesfrombrowser"] = (value,)
    return ydl_opts


def _apply_ytdlp_cookie_cli(cmd: list[str]) -> list[str]:
    """為 yt-dlp CLI 指令套用可用的 Cookies 參數"""
    source = resolve_ytdlp_cookie_source()
    if not source:
        return cmd
    kind, value = source
    if kind == "file":
        cmd.extend(["--cookies", value])
    elif kind == "browser":
        cmd.extend(["--cookies-from-browser", value])
    return cmd


def _fetch_oembed_metadata(url: str) -> tuple[str, str] | None:
    """透過 YouTube 官方 oEmbed API 取得影片標題與頻道名稱（不需登入、不受串流風控影響）"""
    oembed_url = f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json"
    req = urllib.request.Request(
        oembed_url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        title = str(data.get("title") or "").strip()
        author = str(data.get("author_name") or "").strip()
        if title or author:
            return (title, author)
    except Exception:
        pass
    return None


def extract_video_id(url: str) -> str:
    """從各種 YouTube 網址格式中提取 11 碼 Video ID"""
    raw = url.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
        return raw

    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if host == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            return vid

    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            vid = parse_qs(parsed.query).get("v", [""])[0]
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                return vid
        for prefix in ("/shorts/", "/embed/", "/live/", "/v/"):
            if parsed.path.startswith(prefix):
                vid = parsed.path[len(prefix):].split("/")[0]
                if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                    return vid

    raise ValueError("無法辨識的 YouTube 影片網址，請確認連結是否正確。")


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _extract_chapters(raw_chapters: object) -> list[dict]:
    """將 yt-dlp 回傳的 chapters 整理為標準化章節清單"""
    if not isinstance(raw_chapters, list):
        return []
    chapters: list[dict] = []
    for item in raw_chapters:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        start_seconds = max(0, int(float(item.get("start_time") or 0)))
        end_raw = item.get("end_time")
        end_seconds = max(start_seconds, int(float(end_raw))) if end_raw is not None else None
        chapters.append(
            {
                "title": title,
                "timestamp": format_timestamp(start_seconds),
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
            }
        )
    chapters.sort(key=lambda ch: ch["start_seconds"])
    return chapters


def get_video_metadata(url: str, video_id: str) -> VideoMetadata:
    """透過 yt-dlp 取得影片標題、頻道、長度與作者章節（失敗時以 YouTube oEmbed 備援）"""
    ydl_opts = _apply_ytdlp_cookie_opts(
        {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
    )
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return VideoMetadata(
                video_id=video_id,
                title=info.get("title") or f"YouTube 影片 ({video_id})",
                channel=info.get("uploader") or info.get("channel") or "未知頻道",
                duration_seconds=int(info.get("duration") or 0),
                chapters=_extract_chapters(info.get("chapters")),
            )
    except Exception:
        oembed = _fetch_oembed_metadata(url)
        if oembed is not None:
            oembed_title, oembed_author = oembed
            return VideoMetadata(
                video_id=video_id,
                title=oembed_title or f"YouTube 影片 ({video_id})",
                channel=oembed_author or "未知頻道",
                duration_seconds=0,
            )
        return VideoMetadata(
            video_id=video_id,
            title=f"YouTube 影片 ({video_id})",
            channel="未知頻道",
            duration_seconds=0,
        )


def get_transcript(video_id: str) -> TranscriptResult | None:
    """嘗試抓取 YouTube 字幕並格式化為含時間戳記的逐字稿"""
    ytt_api = YouTubeTranscriptApi()
    try:
        transcript_list = ytt_api.list(video_id)
    except Exception:
        return None

    selected = None
    try:
        selected = transcript_list.find_transcript(PREFERRED_LANGS)
    except Exception:
        # 若無指定語言，退而取清單中的第一份字幕
        for item in transcript_list:
            selected = item
            break

    if selected is None:
        return None

    try:
        fetched = selected.fetch()
    except Exception:
        return None

    snippets = [
        {
            "start": float(snippet.start),
            "duration": float(snippet.duration),
            "text": snippet.text.strip(),
        }
        for snippet in fetched
        if snippet.text and snippet.text.strip()
    ]
    if not snippets:
        return None

    lines = [
        f"[{format_timestamp(s['start'])}] {s['text']}"
        for s in snippets
    ]
    kind = "自動字幕" if selected.is_generated else "人工字幕"
    return TranscriptResult(
        text="\n".join(lines),
        source_label=f"{selected.language} ({kind})",
        language_code=selected.language_code,
        snippets=snippets,
    )


def _format_srt_time(seconds: float) -> str:
    ms_total = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(ms_total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def format_transcript_as_srt(snippets: list[dict]) -> str:
    """將字幕片段轉成標準 SRT 字幕格式"""
    blocks: list[str] = []
    for idx, s in enumerate(snippets, start=1):
        start = float(s["start"])
        duration = max(0.5, float(s.get("duration") or 2.0))
        start_str = _format_srt_time(start)
        end_str = _format_srt_time(start + duration)
        blocks.append(f"{idx}\n{start_str} --> {end_str}\n{s['text']}")
    return "\n\n".join(blocks) + "\n"


def extract_audio_for_gemini(url: str, temp_dir: Path) -> Path:
    """當影片無字幕時，使用 yt-dlp 擷取音訊檔供 Gemini 多模態分析"""
    temp_dir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(temp_dir / "%(id)s.%(ext)s")
    ydl_opts: dict = _apply_ytdlp_cookie_opts(
        {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": out_tmpl,
            "quiet": True,
            "no_warnings": True,
        }
    )
    if has_ffmpeg():
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "96",
            }
        ]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        vid = info.get("id", "audio")

    for candidate in temp_dir.glob(f"{vid}.*"):
        if candidate.is_file():
            return candidate
    raise RuntimeError("無法擷取影片音訊以進行無字幕分析。")


def cleanup_partial_files(output_dir: Path, video_id: str) -> None:
    """終止下載時清理殘留的 .part / .ytdl / 分離串流暫存檔"""
    if not output_dir.exists():
        return
    id_marker = f"[{video_id}]"
    patterns = (
        f"*{id_marker}*.part*",
        f"*{id_marker}*.ytdl",
        f"*{id_marker}*.temp.*",
    )
    for pattern in patterns:
        for p in output_dir.glob(pattern):
            try:
                p.unlink()
            except Exception:
                pass
    # yt-dlp 尚未合併的分離串流檔（例如 title [id].f137.mp4 / .f140.m4a / .f251.webm）
    stream_re = re.compile(r"\.f\d+\.[^.]+$", re.IGNORECASE)
    for p in output_dir.glob(f"*{id_marker}*"):
        if p.is_file() and stream_re.search(p.name):
            try:
                p.unlink()
            except Exception:
                pass


def terminate_process_tree(
    proc: subprocess.Popen | None,
    wait_timeout: float = 3.0,
) -> None:
    """立即終止 yt-dlp 及其子行程 (ffmpeg) 並等待釋放檔案控制代碼"""
    if proc is None:
        return
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            res = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if res.returncode != 0 and proc.poll() is None:
                proc.kill()
        else:
            proc.terminate()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    try:
        proc.wait(timeout=wait_timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=1.0)
        except Exception:
            pass
    except Exception:
        pass


def download_media(
    url: str,
    fmt: Literal["mp4", "mp3"],
    output_dir: Path,
    progress_callback: Callable[[int, str], None] | None = None,
    control_check: Callable[[], Literal["run", "pause", "cancel"]] | None = None,
    process_callback: Callable[[subprocess.Popen], None] | None = None,
) -> Path:
    """使用 yt-dlp 子行程 + ffmpeg 下載為 MP4 或 MP3（支援即時暫停與終止）"""
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_available = has_ffmpeg()

    if fmt == "mp3" and not ffmpeg_available:
        raise RuntimeError(
            "本機尚未安裝 ffmpeg，無法轉檔為 MP3。請執行 `winget install Gyan.FFmpeg` 安裝後重試。"
        )

    def _check_control() -> None:
        if not control_check:
            return
        state = control_check()
        if state == "pause":
            raise DownloadPausedError("已暫停下載")
        if state == "cancel":
            raise DownloadCancelledError("已終止下載")

    _check_control()
    if progress_callback:
        progress_callback(2, "正在連線 YouTube 取得串流資訊...")

    video_id = extract_video_id(url)
    out_tmpl = str(output_dir / "%(title).80s [%(id)s].%(ext)s")
    target_ext = ".mp3" if fmt == "mp3" else ".mp4"

    cmd = [
        sys.executable,
        "-u",
        "-m",
        "yt_dlp",
        "--newline",
        "--continue",
        "--no-warnings",
        "--no-playlist",
        "-o",
        out_tmpl,
    ]
    if fmt == "mp3":
        cmd.extend(["-f", "bestaudio/best", "-x", "--audio-format", "mp3", "--audio-quality", "192K"])
    else:
        fmt_selector = (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            if ffmpeg_available
            else "best[ext=mp4]/best"
        )
        cmd.extend(["-f", fmt_selector, "--merge-output-format", "mp4"])
    _apply_ytdlp_cookie_cli(cmd)
    cmd.append(url)

    proc_env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=proc_env,
    )

    pct_re = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%(?:.*?at\s+([^\s]+))?")
    last_lines: list[str] = []

    try:
        if process_callback:
            process_callback(proc)
        _check_control()

        if proc.stdout:
            for raw_line in proc.stdout:
                _check_control()
                line = raw_line.strip()
                if not line:
                    continue
                last_lines.append(line)
                if len(last_lines) > 8:
                    last_lines.pop(0)

                m = pct_re.search(line)
                if m and progress_callback:
                    pct = float(m.group(1))
                    speed = m.group(2)
                    speed_str = f" · {speed}" if speed else ""
                    progress_callback(
                        min(95, max(1, int(pct))),
                        f"下載串流中 {pct:.1f}%{speed_str}",
                    )
                elif (
                    "[Merger]" in line
                    or "[ExtractAudio]" in line
                    or "[ffmpeg]" in line
                ) and progress_callback:
                    progress_callback(97, "FFmpeg 合併／轉檔中...")

        returncode = proc.wait()
        _check_control()

        if returncode != 0:
            detail = last_lines[-1] if last_lines else f"exit code {returncode}"
            raise RuntimeError(f"下載失敗：{detail}")
    finally:
        if proc.stdout:
            try:
                proc.stdout.close()
            except Exception:
                pass
        if proc.poll() is None:
            terminate_process_tree(proc)

    matches = sorted(
        output_dir.glob(f"*[{video_id}]*{target_ext}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if matches:
        return matches[0]
    raise RuntimeError("下載完成但找不到輸出檔案，請稍後再試。")
