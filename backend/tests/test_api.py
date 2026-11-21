from fastapi.testclient import TestClient
import pytest

from main import app
from schemas import GeminiKnowledgeOutput
from services import gemini_service, history_service
from services.youtube_service import (
    extract_video_id,
    format_timestamp,
    format_transcript_as_srt,
)


client = TestClient(app)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=42", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_extract_video_id_valid(url: str, expected: str):
    assert extract_video_id(url) == expected


def test_extract_video_id_invalid():
    with pytest.raises(ValueError):
        extract_video_id("https://example.com/not-youtube")


def test_format_timestamp():
    assert format_timestamp(65) == "01:05"
    assert format_timestamp(3661) == "01:01:01"


def test_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert isinstance(data["ffmpeg_available"], bool)
    assert isinstance(data["gemini_key_configured"], bool)


def test_knowledge_schema_validation():
    sample = {
        "video_summary_one_liner": "介紹 Attention 機制的核心原理。",
        "prerequisites": [
            {
                "id": "p1",
                "name": "向量與點積",
                "importance": "required",
                "why_needed": "計算字詞相似度",
                "plain_explanation": "把詞變成箭頭，方向越像分數越高。",
            }
        ],
        "core_concepts": [
            {
                "id": "c1",
                "title": "Self-Attention",
                "timestamp": "05:42",
                "seconds": 342,
                "summary": "讓句子裡的字彼此計算關聯度。",
                "example_in_video": "代名詞指代消歧",
                "depends_on": ["向量與點積"],
            }
        ],
        "extensions": [
            {
                "id": "e1",
                "type": "vertical",
                "title": "縮放因子 sqrt(d_k)",
                "description": "避免點積過大導致梯度消失。",
                "suggested_prompt": "請解釋為什麼要除以根號 d_k？",
            }
        ],
        "graph_edges": [
            {"source_id": "p1", "target_id": "c1"},
            {"source_id": "c1", "target_id": "e1"},
        ],
    }
    parsed = GeminiKnowledgeOutput.model_validate(sample)
    assert parsed.core_concepts[0].seconds == 342


def test_save_and_load_local_api_key(tmp_path, monkeypatch):
    cfg_dir = tmp_path / ".yt-sum"
    cfg_file = cfg_dir / "config.json"
    monkeypatch.setattr(gemini_service, "USER_CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(gemini_service, "USER_CONFIG_FILE", cfg_file)

    res = client.post("/api/config/key", json={"api_key": "test-key-123"})
    assert res.status_code == 200
    assert res.json()["gemini_key_configured"] is True
    assert gemini_service.load_local_api_key() == "test-key-123"


def test_format_transcript_as_srt():
    srt = format_transcript_as_srt(
        [{"start": 1.5, "duration": 2.0, "text": "你好世界"}]
    )
    assert "1\n00:00:01,500 --> 00:00:03,500\n你好世界" in srt


def test_history_crud(tmp_path, monkeypatch):
    hist_dir = tmp_path / "history"
    monkeypatch.setattr(history_service, "HISTORY_DIR", hist_dir)

    sample_analysis = {
        "video_id": "dQw4w9WgXcQ",
        "title": "Test Video",
        "channel": "Test Channel",
        "duration_seconds": 120,
        "transcript_source": "zh-TW",
        "level": "intermediate",
        "video_summary_one_liner": "測試總結",
        "prerequisites": [{"id": "p1"}],
        "core_concepts": [],
        "extensions": [],
        "graph_edges": [],
        "transcript_excerpt": "excerpt",
    }
    history_service.save_history(sample_analysis)

    listing = client.get("/api/history")
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 1
    assert listing.json()["items"][0]["video_id"] == "dQw4w9WgXcQ"

    upd = client.put(
        "/api/history/dQw4w9WgXcQ/state",
        json={"mastered_ids": ["p1"], "chat_messages": [{"role": "user", "content": "hi"}]},
    )
    assert upd.status_code == 200

    detail = client.get("/api/history/dQw4w9WgXcQ")
    assert detail.status_code == 200
    assert detail.json()["mastered_ids"] == ["p1"]

    dele = client.delete("/api/history/dQw4w9WgXcQ")
    assert dele.status_code == 200
    assert client.get("/api/history").json()["items"] == []


def test_download_status_not_found():
    res = client.get("/api/download/status/nonexistent-task")
    assert res.status_code == 404
    assert client.post("/api/download/pause/nonexistent-task").status_code == 404
    assert client.post("/api/download/resume/nonexistent-task").status_code == 404
    assert client.post("/api/download/cancel/nonexistent-task").status_code == 404


def _spawn_sleep_process():
    import subprocess
    import sys

    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def test_download_pause_kills_process_and_stays_paused(tmp_path, monkeypatch):
    import threading
    import time
    import main
    from services.youtube_service import DownloadPausedError

    monkeypatch.setattr(main, "DOWNLOADS_DIR", tmp_path)
    started = threading.Event()
    spawned_procs = []

    def fake_download_media(url, fmt, output_dir, progress_callback=None, control_check=None, process_callback=None):
        proc = _spawn_sleep_process()
        spawned_procs.append(proc)
        try:
            process_callback(proc)
            started.set()
            while True:
                if control_check() == "pause":
                    raise DownloadPausedError("paused")
                if control_check() == "cancel":
                    raise main.DownloadCancelledError("cancelled")
                time.sleep(0.05)
        finally:
            if proc.poll() is None:
                main.terminate_process_tree(proc)

    monkeypatch.setattr(main, "download_media", fake_download_media)

    res = client.post(
        "/api/download/start",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "format": "mp4"},
    )
    assert res.status_code == 200
    task_id = res.json()["task_id"]
    assert started.wait(timeout=3.0)

    pause_res = client.post(f"/api/download/pause/{task_id}")
    assert pause_res.status_code == 200
    assert pause_res.json()["status"] == "paused"

    time.sleep(0.2)
    assert spawned_procs[0].poll() is not None
    status = client.get(f"/api/download/status/{task_id}").json()
    assert status["status"] == "paused"

    # 測試重覆呼叫 resume 不會重複啟動
    started.clear()
    res_resume_1 = client.post(f"/api/download/resume/{task_id}")
    assert res_resume_1.status_code == 200
    assert started.wait(timeout=3.0)
    res_resume_2 = client.post(f"/api/download/resume/{task_id}")
    assert res_resume_2.status_code == 200
    assert len(spawned_procs) == 2

    # 最後終止清理
    cancel_res = client.post(f"/api/download/cancel/{task_id}")
    assert cancel_res.status_code == 200
    time.sleep(0.2)
    assert spawned_procs[1].poll() is not None
    assert client.post(f"/api/download/resume/{task_id}").status_code == 409


def test_download_cancel_cleans_partial_files(tmp_path, monkeypatch):
    import threading
    import time
    import main

    monkeypatch.setattr(main, "DOWNLOADS_DIR", tmp_path)
    video_id = "dQw4w9WgXcQ"
    part_file = tmp_path / f"Test Video [{video_id}].mp4.part"
    ytdl_file = tmp_path / f"Test Video [{video_id}].mp4.ytdl"
    stream_file = tmp_path / f"Test Video [{video_id}].f137.mp4"
    for f in (part_file, ytdl_file, stream_file):
        f.write_bytes(b"partial")

    started = threading.Event()
    spawned_procs = []

    def fake_download_media(url, fmt, output_dir, progress_callback=None, control_check=None, process_callback=None):
        proc = _spawn_sleep_process()
        spawned_procs.append(proc)
        try:
            process_callback(proc)
            started.set()
            while True:
                if control_check() == "cancel":
                    raise main.DownloadCancelledError("cancelled")
                time.sleep(0.05)
        finally:
            if proc.poll() is None:
                main.terminate_process_tree(proc)

    monkeypatch.setattr(main, "download_media", fake_download_media)

    task_id = client.post(
        "/api/download/start",
        json={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "mp4"},
    ).json()["task_id"]
    assert started.wait(timeout=3.0)

    cancel_res = client.post(f"/api/download/cancel/{task_id}")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

    time.sleep(0.2)
    assert spawned_procs[0].poll() is not None
    assert not part_file.exists()
    assert not ytdl_file.exists()
    assert not stream_file.exists()


def test_download_startup_race_and_generation_isolation(tmp_path, monkeypatch):
    import threading
    import time
    import main
    from services.youtube_service import DownloadPausedError

    monkeypatch.setattr(main, "DOWNLOADS_DIR", tmp_path)
    allow_set_proc = threading.Event()
    proc_registered = threading.Event()
    spawned_procs = []

    def fake_download_media(url, fmt, output_dir, progress_callback=None, control_check=None, process_callback=None):
        proc = _spawn_sleep_process()
        spawned_procs.append(proc)
        try:
            allow_set_proc.wait(timeout=3.0)
            process_callback(proc)
            proc_registered.set()
            if control_check() == "pause":
                raise DownloadPausedError("paused")
            if control_check() == "cancel":
                raise main.DownloadCancelledError("cancelled")
            # 模擬舊執行緒被 kill 後回報異常
            raise RuntimeError("killed")
        finally:
            if proc.poll() is None:
                main.terminate_process_tree(proc)

    monkeypatch.setattr(main, "download_media", fake_download_media)

    task_id = client.post(
        "/api/download/start",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "format": "mp4"},
    ).json()["task_id"]

    # 在 process_callback 執行前就按下暫停
    pause_res = client.post(f"/api/download/pause/{task_id}")
    assert pause_res.status_code == 200
    allow_set_proc.set()
    assert proc_registered.wait(timeout=3.0)
    time.sleep(0.2)

    # 即使暫停時 proc 尚未註冊，_set_proc 與 finally 仍應立即終止該子行程
    assert spawned_procs[0].poll() is not None
    assert client.get(f"/api/download/status/{task_id}").json()["status"] == "paused"

    # 立刻 resume，舊執行緒若較晚退出也不應覆寫新世代為 error
    resume_res = client.post(f"/api/download/resume/{task_id}")
    assert resume_res.status_code == 200
    time.sleep(0.1)
    assert client.get(f"/api/download/status/{task_id}").json()["status"] in {"running", "error"}
    client.post(f"/api/download/cancel/{task_id}")


def test_strip_ansi_and_format_ytdlp_error():
    from services.youtube_service import format_ytdlp_error, strip_ansi

    raw = "\x1b[0;31mERROR:\x1b[0m [youtube] 1IWTM9wFc5E: Sign in to confirm you’re not a bot."
    assert strip_ansi(raw) == "ERROR: [youtube] 1IWTM9wFc5E: Sign in to confirm you’re not a bot."
    friendly = format_ytdlp_error(raw)
    assert "反機器人驗證" in friendly
    assert "\x1b" not in friendly


def test_resolve_ytdlp_cookie_source_priority(tmp_path, monkeypatch):
    from services import youtube_service

    env_cookie = tmp_path / "env_cookies.txt"
    env_cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    default_cookie = tmp_path / "default_cookies.txt"
    default_cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    monkeypatch.setattr(youtube_service, "DEFAULT_COOKIES_PATHS", (default_cookie,))
    monkeypatch.setenv("YOUTUBE_COOKIES_FILE", str(env_cookie))
    monkeypatch.delenv("YOUTUBE_COOKIES_FROM_BROWSER", raising=False)
    assert youtube_service.resolve_ytdlp_cookie_source() == ("file", str(env_cookie))

    monkeypatch.delenv("YOUTUBE_COOKIES_FILE", raising=False)
    assert youtube_service.resolve_ytdlp_cookie_source() == ("file", str(default_cookie))

    default_cookie.unlink()
    monkeypatch.setenv("YOUTUBE_COOKIES_FROM_BROWSER", "chrome")
    assert youtube_service.resolve_ytdlp_cookie_source() == ("browser", "chrome")


def test_get_video_metadata_falls_back_to_oembed(monkeypatch):
    from services import youtube_service

    class BrokenYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            raise RuntimeError("bot check")

    monkeypatch.setattr(youtube_service.yt_dlp, "YoutubeDL", BrokenYDL)
    monkeypatch.setattr(
        youtube_service,
        "_fetch_oembed_metadata",
        lambda url: ("測試影片標題", "測試頻道"),
    )

    meta = youtube_service.get_video_metadata("https://www.youtube.com/watch?v=1IWTM9wFc5E", "1IWTM9wFc5E")
    assert meta.title == "測試影片標題"
    assert meta.channel == "測試頻道"


def test_analyze_falls_back_to_gemini_youtube_url_when_transcript_unavailable(monkeypatch):
    import main
    from services.youtube_service import VideoMetadata

    sample = GeminiKnowledgeOutput(
        video_summary_one_liner="Gemini 直接解析 YouTube 影片摘要。",
        prerequisites=[],
        core_concepts=[],
        extensions=[],
        graph_edges=[],
    )

    monkeypatch.setattr(
        main,
        "get_video_metadata",
        lambda url, vid: VideoMetadata(
            video_id=vid,
            title="Windows Server 2025",
            channel="詹姆斯的技術世界",
            duration_seconds=0,
        ),
    )
    monkeypatch.setattr(main, "get_transcript", lambda vid: None)
    monkeypatch.setattr(
        main,
        "analyze_youtube_url_with_gemini",
        lambda **kwargs: sample,
    )
    monkeypatch.setattr(
        main,
        "extract_audio_for_gemini",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不應觸發 yt-dlp 音訊下載")),
    )
    monkeypatch.setattr(main, "save_history", lambda data: None)

    res = client.post(
        "/api/analyze",
        json={"url": "https://www.youtube.com/watch?v=1IWTM9wFc5E", "level": "intermediate"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Windows Server 2025"
    assert body["transcript_source"] == "Gemini 直接解析 YouTube 影片"
    assert body["video_summary_one_liner"] == "Gemini 直接解析 YouTube 影片摘要。"


def test_gemini_fallback_on_503(monkeypatch):
    calls = []

    class FakeModels:
        def generate_content(self, model, contents, config):
            calls.append(model)
            if len(calls) == 1:
                raise RuntimeError("503 UNAVAILABLE. high demand")
            return type("Resp", (), {"text": "ok", "parsed": None})()

    fake_client = type("FakeClient", (), {"models": FakeModels()})()
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setattr(gemini_service.time, "sleep", lambda _: None)

    resp = gemini_service._generate_with_fallback(
        client=fake_client,
        contents="hi",
        config=gemini_service.types.GenerateContentConfig(temperature=0.2),
    )
    assert resp.text == "ok"
    assert calls == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
