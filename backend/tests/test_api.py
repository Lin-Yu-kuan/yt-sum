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


def test_to_traditional_chinese_and_normalize_output():
    converted = gemini_service.to_traditional_chinese(
        "视频中的服务器内存与软件架构设计"
    )
    assert "影片" in converted
    assert "伺服器" in converted
    assert "記憶體" in converted
    assert "軟體" in converted
    assert "视频" not in converted

    sample = GeminiKnowledgeOutput(
        video_summary_one_liner="这部视频介绍服务器内存优化。",
        prerequisites=[
            {
                "id": "p1",
                "name": "服务器内存管理",
                "importance": "required",
                "why_needed": "理解系统内存分配",
                "plain_explanation": "就像软件向系统借用临时工作台。",
            }
        ],
        core_concepts=[
            {
                "id": "c1",
                "title": "缓存命中率",
                "timestamp": "01:20",
                "seconds": 80,
                "summary": "提升数据读取速度。",
                "example_in_video": "数据库查询优化案例",
                "depends_on": ["服务器内存管理"],
            }
        ],
        extensions=[
            {
                "id": "e1",
                "type": "vertical",
                "title": "操作系统分页机制",
                "description": "了解虚拟内存如何映射到物理内存。",
                "suggested_prompt": "请说明软件如何处理内存分页？",
            }
        ],
        graph_edges=[{"source_id": "p1", "target_id": "c1"}],
    )

    normalized = gemini_service.normalize_knowledge_to_zh_tw(sample)
    assert "影片" in normalized.video_summary_one_liner
    assert "伺服器" in normalized.prerequisites[0].name
    assert "軟體" in normalized.prerequisites[0].plain_explanation
    assert "快取" in normalized.core_concepts[0].title or "緩存" in normalized.core_concepts[0].title
    assert "資料庫" in normalized.core_concepts[0].example_in_video
    assert "伺服器" in normalized.core_concepts[0].depends_on[0]
    assert "作業系統" in normalized.extensions[0].title
    assert "軟體" in normalized.extensions[0].suggested_prompt


def test_extract_chapters_and_analyze_includes_transcript_and_chapters(monkeypatch):
    import main
    from services import youtube_service
    from services.youtube_service import TranscriptResult, VideoMetadata

    raw_chapters = [
        {"title": "主題一：介紹", "start_time": 0.0, "end_time": 65.0},
        {"title": "主題二：實戰", "start_time": 65.0, "end_time": 180.0},
    ]
    parsed_chapters = youtube_service._extract_chapters(raw_chapters)
    assert len(parsed_chapters) == 2
    assert parsed_chapters[1]["timestamp"] == "01:05"
    assert parsed_chapters[1]["start_seconds"] == 65

    sample_knowledge = GeminiKnowledgeOutput(
        video_summary_one_liner="影片摘要",
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
            title="Chapter Test",
            channel="Test",
            duration_seconds=180,
            chapters=parsed_chapters,
        ),
    )
    monkeypatch.setattr(
        main,
        "get_transcript",
        lambda vid: TranscriptResult(
            text="[00:00] Hello\n[01:05] World",
            source_label="English (人工字幕)",
            language_code="en",
            snippets=[
                {"start": 0.0, "duration": 2.0, "text": "Hello"},
                {"start": 65.0, "duration": 2.0, "text": "World"},
            ],
        ),
    )
    monkeypatch.setattr(main, "analyze_transcript_with_gemini", lambda **kwargs: sample_knowledge)
    monkeypatch.setattr(main, "save_history", lambda data: None)

    res = client.post(
        "/api/analyze",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "level": "intermediate"},
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["chapters"]) == 2
    assert body["chapters"][1]["title"] == "主題二：實戰"
    assert body["transcript_language"] == "en"
    assert len(body["transcript_lines"]) == 2
    assert body["transcript_lines"][1]["seconds"] == 65
    # 英文影片初次解析不預先翻譯，保持零增量延遲
    assert body["transcript_zh_tw_lines"] == []


def test_translate_transcript_endpoint_uses_opencc_and_cache(tmp_path, monkeypatch):
    import main

    hist_dir = tmp_path / "history"
    monkeypatch.setattr(history_service, "HISTORY_DIR", hist_dir)

    video_id = "dQw4w9WgXcQ"
    history_service.save_history(
        {
            "video_id": video_id,
            "title": "簡中測試",
            "channel": "Test",
            "duration_seconds": 60,
            "transcript_source": "中文",
            "level": "intermediate",
            "video_summary_one_liner": "測試",
            "prerequisites": [],
            "core_concepts": [],
            "extensions": [],
            "graph_edges": [],
            "transcript_excerpt": "",
            "transcript_language": "zh-CN",
            "transcript_lines": [
                {"timestamp": "00:00", "seconds": 0, "text": "欢迎来到服务器内存课程"},
            ],
            "transcript_zh_tw_lines": [],
        }
    )

    # 簡中走 OpenCC，不應呼叫 Gemini client
    monkeypatch.setattr(
        gemini_service,
        "_get_client",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("簡中轉換不應呼叫 Gemini")),
    )

    res1 = client.post("/api/transcript/translate", json={"video_id": video_id})
    assert res1.status_code == 200
    body1 = res1.json()
    assert body1["cached"] is False
    assert "伺服器" in body1["transcript_zh_tw_lines"][0]["text"]
    assert "記憶體" in body1["transcript_zh_tw_lines"][0]["text"]

    # 第二次呼叫直接命中快取
    res2 = client.post("/api/transcript/translate", json={"video_id": video_id})
    assert res2.status_code == 200
    assert res2.json()["cached"] is True


def test_history_endpoints_normalize_simplified_chinese_to_zh_tw(tmp_path, monkeypatch):
    hist_dir = tmp_path / "history"
    monkeypatch.setattr(history_service, "HISTORY_DIR", hist_dir)

    video_id = "1IWTM9wFc5E"
    history_service.save_history(
        analysis={
            "video_id": video_id,
            "title": "服务器磁盘与软件管理",
            "channel": "Test",
            "duration_seconds": 120,
            "transcript_source": "Chinese (Simplified)",
            "level": "intermediate",
            "video_summary_one_liner": "本影片完整解析基本磁盘设定与动态磁盘架构，深入探讨镜像与企业级存储应用。",
            "prerequisites": [
                {
                    "id": "p1",
                    "name": "磁盘阵列基础",
                    "importance": "required",
                    "why_needed": "涉及跨区、等量、镜像与容错。",
                    "plain_explanation": "把多颗硬盘组成团队提升效能与备份。",
                }
            ],
            "core_concepts": [
                {
                    "id": "c1",
                    "title": "动态磁盘架构",
                    "timestamp": "01:00",
                    "seconds": 60,
                    "summary": "说明软件如何管理内存与磁盘分区。",
                    "example_in_video": "建立镜像磁盘区",
                    "depends_on": ["磁盘阵列基础"],
                }
            ],
            "extensions": [
                {
                    "id": "e1",
                    "type": "vertical",
                    "title": "企业级存储容错",
                    "description": "了解服务器硬盘损坏时的重建流程。",
                    "suggested_prompt": "请说明镜像与 RAID-5 的差异。",
                }
            ],
            "graph_edges": [{"source_id": "p1", "target_id": "c1"}],
            "transcript_excerpt": "欢迎来到服务器课程",
            "chapters": [{"title": "基本磁盘设定", "timestamp": "00:00", "start_seconds": 0}],
            "transcript_language": "zh-CN",
            "transcript_lines": [{"timestamp": "00:00", "seconds": 0, "text": "欢迎来到服务器课程"}],
            "transcript_zh_tw_lines": [],
        },
        chat_messages=[
            {"role": "user", "content": "请解释什么是镜像？"},
            {"role": "assistant", "content": "镜像就是将数据同时写入两颗磁盘以提供容错。"},
        ],
    )

    list_res = client.get("/api/history")
    assert list_res.status_code == 200
    summary_item = list_res.json()["items"][0]
    assert "磁碟" in summary_item["video_summary_one_liner"]
    assert "架构" not in summary_item["video_summary_one_liner"]
    assert "架構" in summary_item["video_summary_one_liner"]
    assert "伺服器" in summary_item["title"]

    detail_res = client.get(f"/api/history/{video_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    analysis = detail["analysis"]
    assert "磁碟" in analysis["video_summary_one_liner"]
    assert "映象" in analysis["prerequisites"][0]["why_needed"]
    assert "記憶體" in analysis["core_concepts"][0]["summary"]
    assert "伺服器" in analysis["extensions"][0]["description"]
    assert "磁碟" in analysis["chapters"][0]["title"]
    # 原文逐字稿應保持原樣，供使用者切換原文檢視
    assert analysis["transcript_lines"][0]["text"] == "欢迎来到服务器课程"
    # 助理回覆轉為繁體，使用者提問保留原樣
    assert "磁碟" in detail["chat_messages"][1]["content"]
    assert detail["chat_messages"][0]["content"] == "请解释什么是镜像？"


def _sample_knowledge_output() -> GeminiKnowledgeOutput:
    return GeminiKnowledgeOutput.model_validate(
        {
            "video_summary_one_liner": "無字幕影片知識總結。",
            "prerequisites": [
                {
                    "id": "p1",
                    "name": "基礎概念",
                    "importance": "required",
                    "why_needed": "理解後續內容",
                    "plain_explanation": "白話說明。",
                }
            ],
            "core_concepts": [
                {
                    "id": "c1",
                    "title": "核心重點",
                    "timestamp": "00:30",
                    "seconds": 30,
                    "summary": "重點摘要。",
                    "example_in_video": "影片範例",
                    "depends_on": ["基礎概念"],
                }
            ],
            "extensions": [
                {
                    "id": "e1",
                    "type": "vertical",
                    "title": "延伸思考",
                    "description": "深入理解。",
                    "suggested_prompt": "請進一步解釋。",
                }
            ],
            "graph_edges": [{"source_id": "p1", "target_id": "c1"}],
        }
    )


def test_analyze_no_subtitle_short_video_auto_transcribes(tmp_path, monkeypatch):
    import main as main_module
    from services.youtube_service import VideoMetadata

    monkeypatch.setattr(history_service, "HISTORY_DIR", tmp_path / "history")
    monkeypatch.setattr(
        main_module,
        "get_video_metadata",
        lambda url, vid: VideoMetadata(
            video_id=vid,
            title="Short No Subtitle Video",
            channel="Test Channel",
            duration_seconds=300,
        ),
    )
    monkeypatch.setattr(main_module, "get_transcript", lambda vid: None)
    monkeypatch.setattr(
        main_module,
        "analyze_youtube_url_with_gemini",
        lambda **kwargs: _sample_knowledge_output(),
    )
    monkeypatch.setattr(
        main_module,
        "_ai_transcribe_no_subtitle",
        lambda **kwargs: (
            "en",
            [{"timestamp": "00:00", "seconds": 0, "text": "Hello everyone."}],
            "AI 語音聽寫（純音訊）",
        ),
    )

    res = client.post(
        "/api/analyze",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "level": "intermediate"},
    )
    assert res.status_code == 200
    body = res.json()
    assert "AI 語音聽寫（純音訊）" in body["transcript_source"]
    assert body["transcript_language"] == "en"
    assert len(body["transcript_lines"]) == 1
    assert body["transcript_lines"][0]["text"] == "Hello everyone."
    assert "Hello everyone." in body["transcript_excerpt"]


def test_analyze_no_subtitle_long_video_skips_auto_and_supports_on_demand(tmp_path, monkeypatch):
    import main as main_module
    from services.youtube_service import VideoMetadata

    monkeypatch.setattr(history_service, "HISTORY_DIR", tmp_path / "history")
    monkeypatch.setattr(
        main_module,
        "get_video_metadata",
        lambda url, vid: VideoMetadata(
            video_id=vid,
            title="Long No Subtitle Video",
            channel="Test Channel",
            duration_seconds=1800,  # 30 分鐘，超過 20 分鐘門檻
        ),
    )
    monkeypatch.setattr(main_module, "get_transcript", lambda vid: None)
    monkeypatch.setattr(
        main_module,
        "analyze_youtube_url_with_gemini",
        lambda **kwargs: _sample_knowledge_output(),
    )

    ai_calls = {"count": 0}

    def _fake_ai_transcribe(**kwargs):
        ai_calls["count"] += 1
        return (
            "zh-TW",
            [{"timestamp": "00:10", "seconds": 10, "text": "這是長片按需聽寫測試。"}],
            "AI 語音聽寫（純音訊）",
        )

    monkeypatch.setattr(main_module, "_ai_transcribe_no_subtitle", _fake_ai_transcribe)

    res = client.post(
        "/api/analyze",
        json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "level": "intermediate"},
    )
    assert res.status_code == 200
    assert res.json()["transcript_lines"] == []
    assert ai_calls["count"] == 0

    # 按需點擊觸發聽寫
    tr_res = client.post("/api/transcript/transcribe", json={"video_id": "dQw4w9WgXcQ"})
    assert tr_res.status_code == 200
    tr_body = tr_res.json()
    assert tr_body["cached"] is False
    assert len(tr_body["transcript_lines"]) == 1
    assert tr_body["transcript_zh_tw_lines"][0]["text"] == "這是長片按需聽寫測試。"
    assert ai_calls["count"] == 1

    # 再次呼叫應命中本機快取（0 token）
    tr_res2 = client.post("/api/transcript/transcribe", json={"video_id": "dQw4w9WgXcQ"})
    assert tr_res2.status_code == 200
    assert tr_res2.json()["cached"] is True
    assert ai_calls["count"] == 1

    # 無原生字幕但已有快取時，應可正常匯出 SRT
    dl_res = client.post(
        "/api/transcript/download",
        json={"url": "dQw4w9WgXcQ", "format": "srt", "translate_to_zh_tw": True},
    )
    assert dl_res.status_code == 200
    assert "00:00:10,000 -->" in dl_res.text
    assert "這是長片按需聽寫測試。" in dl_res.text
    assert ai_calls["count"] == 1


def test_user_data_paths_under_project_data_dir():
    from pathlib import Path
    import main as main_module
    from services import youtube_service

    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / "data"
    legacy_home_dir = Path.home() / ".yt-sum"

    assert history_service.HISTORY_DIR == data_dir / "history"
    assert gemini_service.USER_CONFIG_DIR == data_dir
    assert gemini_service.USER_CONFIG_FILE == data_dir / "config.json"
    assert main_module.DOWNLOADS_DIR == data_dir / "downloads"
    assert youtube_service.DEFAULT_COOKIES_PATHS[0] == data_dir / "cookies.txt"

    for p in (
        history_service.HISTORY_DIR,
        gemini_service.USER_CONFIG_DIR,
        main_module.DOWNLOADS_DIR,
        *youtube_service.DEFAULT_COOKIES_PATHS,
    ):
        assert legacy_home_dir not in p.parents and p != legacy_home_dir


def test_pwa_assets_served_with_no_cache():
    manifest_res = client.get("/manifest.json")
    assert manifest_res.status_code == 200
    assert "no-cache" in manifest_res.headers.get("cache-control", "").lower()
    manifest = manifest_res.json()
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"

    sw_res = client.get("/sw.js")
    assert sw_res.status_code == 200
    assert "no-cache" in sw_res.headers.get("cache-control", "").lower()
    assert "/api/" in sw_res.text


def test_terminate_process_tree_handles_none():
    from services.youtube_service import terminate_process_tree

    terminate_process_tree(None)


def test_generate_concept_guides_caches_and_normalizes_zh_tw(tmp_path, monkeypatch):
    import main as main_module
    from schemas import (
        ConceptGuideItem,
        ConceptOverview,
        GeminiConceptGuidesOutput,
    )

    hist_dir = tmp_path / "history"
    monkeypatch.setattr(history_service, "HISTORY_DIR", hist_dir)

    video_id = "dQw4w9WgXcQ"
    history_service.save_history(
        {
            "video_id": video_id,
            "title": "測試伺服器架構影片",
            "channel": "Test",
            "duration_seconds": 300,
            "transcript_source": "zh-TW",
            "level": "intermediate",
            "video_summary_one_liner": "介紹核心架構。",
            "prerequisites": [],
            "core_concepts": [
                {
                    "id": "c1",
                    "title": "快取機制",
                    "timestamp": "01:00",
                    "seconds": 60,
                    "summary": "說明記憶體快取。",
                    "example_in_video": "Redis 實例",
                    "depends_on": [],
                }
            ],
            "extensions": [],
            "graph_edges": [],
            "transcript_excerpt": (
                "這是一段超過一百二十個字元的完整逐字稿脈絡內容，用來測試觀念解說生成端點會直接採用完整逐字稿，"
                "不會前置塞入碎片化的分段摘要，並確保所有簡體字彙都能被正確轉換為台灣繁體中文與慣用語。"
                "記憶體與伺服器快取是系統效能優化的關鍵核心，透過減少磁碟隨機存取，可以讓整體架構的延遲大幅降低。"
            ),
            "transcript_lines": [],
            "transcript_zh_tw_lines": [],
        }
    )

    call_count = 0
    captured_contexts: list[str] = []

    def fake_generate(**kwargs):
        nonlocal call_count
        call_count += 1
        captured_contexts.append(kwargs.get("context_text", ""))
        raw = GeminiConceptGuidesOutput(
            concept_overview=ConceptOverview(
                core_question="如何从零配置服务器内存快取并让服务正式可用？",
                mental_model="把内存快取想象成书桌上的常用文件夹，不用每次都去仓库（磁盘）翻找。",
                end_to_end_guide="### 第一步：建立快取池\n1. 配置内存空间。\n### 第二步：挂载接口\n2. 绑定服务端口才能真正读写。",
                pitfalls_and_tips=[
                    "切勿分配超过实体内存上限，否则服务会崩溃。",
                    "删除快取前必须先卸载应用连线。",
                ],
            ),
            concept_guides=[
                ConceptGuideItem(
                    id="g1",
                    title="服务器内存快取",
                    role_in_big_picture="位于核心主轴的存储选型阶段，决定读取速度与稳定性。",
                    one_line_definition="把常用数据暂时放在内存以加速读取。",
                    detailed_explanation="### 运作机制\n- 减少频繁读写磁盘。\n- **提升软件响应速度**。",
                )
            ],
        )
        return gemini_service.normalize_concept_output_to_zh_tw(raw)

    monkeypatch.setattr(main_module, "generate_concept_guides_with_gemini", fake_generate)
    monkeypatch.setattr(
        main_module,
        "generate_concept_guides_from_youtube_url",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("不應走 YouTube URL 備援")),
    )

    # 首次呼叫：生成並寫入快取
    res1 = client.post("/api/concepts/generate", json={"video_id": video_id})
    assert res1.status_code == 200
    body1 = res1.json()
    assert body1["cached"] is False
    assert call_count == 1
    # 確認沒有前置塞入碎片化的 core_concepts「分段摘要參考」造成錨定偏誤
    assert "分段摘要參考" not in captured_contexts[0]

    ov1 = body1["concept_overview"]
    assert ov1 is not None
    assert "伺服器" in ov1["core_question"]
    assert "記憶體" in ov1["core_question"]
    assert "磁碟" in ov1["mental_model"]
    assert "掛載" in ov1["end_to_end_guide"]
    assert "實體記憶體" in ov1["pitfalls_and_tips"][0]

    assert len(body1["concept_guides"]) == 1
    g1 = body1["concept_guides"][0]
    assert "伺服器" in g1["title"]
    assert "位於" in g1["role_in_big_picture"]
    assert "記憶體" in g1["one_line_definition"]
    assert "磁碟" in g1["detailed_explanation"]
    assert "軟體" in g1["detailed_explanation"]

    # 二次呼叫：直接命中快取，不重打 Gemini
    res2 = client.post("/api/concepts/generate", json={"video_id": video_id})
    assert res2.status_code == 200
    assert res2.json()["cached"] is True
    assert res2.json()["concept_overview"]["core_question"] == ov1["core_question"]
    assert call_count == 1

    # force=True：強制重新生成
    res3 = client.post("/api/concepts/generate", json={"video_id": video_id, "force": True})
    assert res3.status_code == 200
    assert res3.json()["cached"] is False
    assert call_count == 2

    # 歷史詳細紀錄應已持久化 concept_overview 與 concept_guides
    saved = client.get(f"/api/history/{video_id}").json()
    assert saved["analysis"]["concept_overview"]["core_question"] == ov1["core_question"]
    assert len(saved["analysis"]["concept_guides"]) == 1

    # 向後相容測試：舊版快取沒有 concept_overview 時仍能正常載入回傳
    legacy_id = "8II52RQBxUE"
    history_service.save_history(
        {
            "video_id": legacy_id,
            "title": "舊版紀錄",
            "channel": "Test",
            "duration_seconds": 100,
            "transcript_source": "zh-TW",
            "level": "intermediate",
            "video_summary_one_liner": "舊版測試。",
            "prerequisites": [],
            "core_concepts": [],
            "extensions": [],
            "graph_edges": [],
            "transcript_excerpt": "x" * 200,
            "concept_guides": [
                {
                    "id": "g_old",
                    "title": "舊版觀念",
                    "one_line_definition": "舊版定義",
                    "detailed_explanation": "舊版內文",
                }
            ],
        }
    )
    legacy_res = client.post("/api/concepts/generate", json={"video_id": legacy_id})
    assert legacy_res.status_code == 200
    legacy_body = legacy_res.json()
    assert legacy_body["cached"] is True
    assert legacy_body["concept_overview"] is None
    assert legacy_body["concept_guides"][0]["title"] == "舊版觀念"


def test_health_includes_version_and_no_store_headers(monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "_get_frontend_build_id", lambda: "testbuild123")
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["frontend_build_id"] == "testbuild123"
    assert isinstance(body["backend_stale"], bool)
    assert isinstance(body["backend_started_at"], str)

    monkeypatch.setattr(main_module, "_is_backend_stale", lambda: True)
    assert client.get("/api/health").json()["backend_stale"] is True

    sw_res = client.get("/sw.js")
    assert "no-store" in sw_res.headers.get("cache-control", "").lower()


def test_system_restart_localhost_only(monkeypatch):
    import main as main_module

    remote_client = TestClient(app, client=("10.0.0.8", 54321))
    assert remote_client.post("/api/system/restart").status_code == 403

    called = {"spawned": False, "exited": False}
    monkeypatch.setattr(
        main_module,
        "_spawn_detached_restart",
        lambda: called.__setitem__("spawned", True),
    )
    monkeypatch.setattr(
        main_module.os,
        "_exit",
        lambda code: called.__setitem__("exited", True),
    )
    monkeypatch.setattr(main_module.time, "sleep", lambda _: None)

    class ImmediateThread:
        def __init__(self, target=None, daemon=None):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    monkeypatch.setattr(main_module.threading, "Thread", ImmediateThread)

    local_client = TestClient(app, client=("127.0.0.1", 54321))
    res = local_client.post("/api/system/restart")
    assert res.status_code == 200
    assert res.json()["status"] == "restarting"
    assert called["spawned"] is True
    assert called["exited"] is True
