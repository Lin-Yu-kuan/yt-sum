import os
import re
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from schemas import (
    AnalyzeRequest,
    ChapterItem,
    ChatRequest,
    ChatResponse,
    DownloadRequest,
    TranscriptLine,
    TranslateTranscriptRequest,
    TranslateTranscriptResponse,
    VideoAnalysisResponse,
)
from services.gemini_service import (
    analyze_audio_with_gemini,
    analyze_transcript_with_gemini,
    analyze_youtube_url_with_gemini,
    chat_follow_up,
    has_configured_api_key,
    save_local_api_key,
    to_traditional_chinese,
    translate_transcript_lines_to_zh_tw,
    translate_transcript_to_zh_tw,
)
from services.history_service import (
    delete_history,
    get_history,
    list_history,
    save_history,
    update_history_state,
    update_history_transcript,
)
from services.youtube_service import (
    DownloadCancelledError,
    DownloadPausedError,
    cleanup_partial_files,
    download_media,
    extract_audio_for_gemini,
    extract_video_id,
    format_timestamp,
    format_transcript_as_srt,
    format_ytdlp_error,
    get_transcript,
    get_video_metadata,
    has_configured_cookies,
    has_ffmpeg,
    terminate_process_tree,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOAD_TASKS: dict[str, dict] = {}

app = FastAPI(title="YT-Sum Knowledge Navigator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


class SaveKeyRequest(BaseModel):
    api_key: str


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "ffmpeg_available": has_ffmpeg(),
        "gemini_key_configured": has_configured_api_key(),
        "cookies_configured": has_configured_cookies(),
        "model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
    }


@app.post("/api/config/key")
def save_api_key(req: SaveKeyRequest):
    try:
        save_local_api_key(req.api_key)
        return {"status": "ok", "gemini_key_configured": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _snippets_to_lines(snippets: list[dict]) -> list[TranscriptLine]:
    return [
        TranscriptLine(
            timestamp=format_timestamp(s["start"]),
            seconds=max(0, int(s["start"])),
            text=str(s["text"]),
        )
        for s in snippets
    ]


@app.post("/api/analyze", response_model=VideoAnalysisResponse)
def analyze_video(req: AnalyzeRequest):
    try:
        video_id = extract_video_id(req.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    meta = get_video_metadata(canonical_url, video_id)
    transcript = get_transcript(video_id)

    try:
        if transcript is not None:
            knowledge = analyze_transcript_with_gemini(
                video_title=meta.title,
                transcript_text=transcript.text,
                level=req.level,
                api_key_override=req.api_key,
                chapters=meta.chapters,
            )
            source_label = transcript.source_label
            excerpt = transcript.text[:15_000]
        else:
            # 無字幕或本機 IP 受限：優先使用 Gemini 原生 YouTube URL 直讀，失敗再退回音訊擷取
            try:
                knowledge = analyze_youtube_url_with_gemini(
                    video_title=meta.title,
                    youtube_url=canonical_url,
                    level=req.level,
                    api_key_override=req.api_key,
                    chapters=meta.chapters,
                )
                source_label = "Gemini 直接解析 YouTube 影片"
                excerpt = knowledge.video_summary_one_liner
            except ValueError:
                raise
            except Exception as url_exc:
                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        audio_path = extract_audio_for_gemini(canonical_url, Path(tmp))
                        knowledge = analyze_audio_with_gemini(
                            video_title=meta.title,
                            audio_path=audio_path,
                            level=req.level,
                            api_key_override=req.api_key,
                            chapters=meta.chapters,
                        )
                    source_label = "無字幕（由音訊直接解析）"
                    excerpt = knowledge.video_summary_one_liner
                except ValueError:
                    raise
                except Exception as audio_exc:
                    raise RuntimeError(
                        f"影片直讀失敗（{url_exc}）；音訊備援亦失敗：{format_ytdlp_error(str(audio_exc))}"
                    ) from audio_exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Gemini 分析失敗：{format_ytdlp_error(str(exc))}",
        ) from exc

    transcript_lines = _snippets_to_lines(transcript.snippets) if transcript is not None else []
    transcript_lang = transcript.language_code if transcript is not None else ""
    transcript_zh_tw_lines: list[TranscriptLine] = []
    if transcript is not None and transcript_lang.lower() in {"zh-tw", "zh-hant"}:
        transcript_zh_tw_lines = [
            TranscriptLine(
                timestamp=line.timestamp,
                seconds=line.seconds,
                text=to_traditional_chinese(line.text),
            )
            for line in transcript_lines
        ]

    result = VideoAnalysisResponse(
        video_id=meta.video_id,
        title=meta.title,
        channel=meta.channel,
        duration_seconds=meta.duration_seconds,
        transcript_source=source_label,
        level=req.level,
        video_summary_one_liner=knowledge.video_summary_one_liner,
        prerequisites=knowledge.prerequisites,
        core_concepts=knowledge.core_concepts,
        extensions=knowledge.extensions,
        graph_edges=knowledge.graph_edges,
        transcript_excerpt=excerpt,
        chapters=[ChapterItem(**ch) for ch in meta.chapters],
        transcript_language=transcript_lang,
        transcript_lines=transcript_lines,
        transcript_zh_tw_lines=transcript_zh_tw_lines,
    )
    save_history(result.model_dump())
    return result


@app.post("/api/chat", response_model=ChatResponse)
def chat_about_video(req: ChatRequest):
    try:
        answer = chat_follow_up(
            video_title=req.video_title,
            video_context=req.video_context,
            history=req.history,
            question=req.question,
            api_key_override=req.api_key,
        )
        return ChatResponse(answer=answer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"對話生成失敗：{exc}") from exc


@app.post("/api/download")
def download_video_or_audio(req: DownloadRequest):
    try:
        video_id = extract_video_id(req.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        file_path = download_media(canonical_url, req.format, DOWNLOADS_DIR)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=format_ytdlp_error(str(exc))) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"下載失敗：{format_ytdlp_error(str(exc))}") from exc

    media_type = "audio/mpeg" if req.format == "mp3" else "video/mp4"
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
    )


def _spawn_download_thread(task_id: str, generation: int) -> None:
    def _run():
        task = DOWNLOAD_TASKS[task_id]
        lock: threading.Lock = task["lock"]

        def _update(pct: int, stage: str):
            with lock:
                # 暫停、終止或世代已切換後不再覆寫進度
                if task["generation"] == generation and task["control"] == "run":
                    task["percent"] = max(task["percent"], pct)
                    task["stage"] = stage

        def _control():
            with lock:
                if task["generation"] != generation:
                    return "cancel"
                return task["control"]

        def _set_proc(proc):
            should_kill = False
            with lock:
                if task["generation"] == generation and task["control"] == "run":
                    task["proc"] = proc
                else:
                    should_kill = True
            if should_kill:
                terminate_process_tree(proc)

        try:
            file_path = download_media(
                task["url"],
                task["format"],
                DOWNLOADS_DIR,
                progress_callback=_update,
                control_check=_control,
                process_callback=_set_proc,
            )
            with lock:
                if task["generation"] == generation and task["control"] == "run":
                    task["status"] = "done"
                    task["percent"] = 100
                    task["stage"] = "處理完成，正在儲存檔案..."
                    task["filename"] = file_path.name
                    task["file_path"] = str(file_path)
        except DownloadPausedError:
            with lock:
                if task["generation"] == generation and task["control"] == "pause":
                    task["status"] = "paused"
                    task["stage"] = f"已暫停於 {task['percent']}%（可點繼續接續下載）"
        except DownloadCancelledError:
            should_cleanup = False
            with lock:
                if task["generation"] == generation or task["status"] == "cancelled":
                    if task["generation"] == generation:
                        task["status"] = "cancelled"
                        task["stage"] = "已終止下載"
                    should_cleanup = task["status"] == "cancelled"
            if should_cleanup:
                cleanup_partial_files(DOWNLOADS_DIR, task["video_id"])
        except Exception as exc:
            with lock:
                if task["generation"] == generation and task["control"] == "run":
                    task["status"] = "error"
                    task["error"] = format_ytdlp_error(str(exc))
        finally:
            with lock:
                if task["generation"] == generation:
                    task["proc"] = None

    threading.Thread(target=_run, daemon=True).start()


@app.post("/api/download/start")
def start_media_download(req: DownloadRequest):
    try:
        video_id = extract_video_id(req.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if req.format == "mp3" and not has_ffmpeg():
        raise HTTPException(
            status_code=400,
            detail="本機尚未安裝 ffmpeg，無法轉檔為 MP3。請先安裝 FFmpeg。",
        )

    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    task_id = uuid.uuid4().hex
    DOWNLOAD_TASKS[task_id] = {
        "lock": threading.Lock(),
        "generation": 0,
        "proc": None,
        "status": "running",
        "control": "run",
        "percent": 0,
        "stage": "準備下載任務...",
        "filename": None,
        "file_path": None,
        "format": req.format,
        "url": canonical_url,
        "video_id": video_id,
        "error": None,
    }
    _spawn_download_thread(task_id, 0)
    return {"task_id": task_id}


@app.post("/api/download/pause/{task_id}")
def pause_media_download(task_id: str):
    task = DOWNLOAD_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="找不到下載任務")
    with task["lock"]:
        if task["status"] in {"done", "cancelled", "error"}:
            return {"status": task["status"]}
        task["control"] = "pause"
        task["status"] = "paused"
        task["stage"] = f"已暫停於 {task['percent']}%（可點繼續接續下載）"
        proc = task.get("proc")
        task["proc"] = None
    terminate_process_tree(proc)
    return {"status": "paused"}


@app.post("/api/download/resume/{task_id}")
def resume_media_download(task_id: str):
    task = DOWNLOAD_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="找不到下載任務")
    with task["lock"]:
        if task["status"] == "done":
            return {"status": "done"}
        if task["status"] == "cancelled":
            raise HTTPException(status_code=409, detail="下載已終止，無法繼續")
        if task["status"] == "running" and task["control"] == "run":
            return {"status": "running"}
        task["generation"] += 1
        generation = task["generation"]
        task["control"] = "run"
        task["status"] = "running"
        task["error"] = None
        task["stage"] = f"從 {task['percent']}% 繼續下載中..."
    _spawn_download_thread(task_id, generation)
    return {"status": "running"}


@app.post("/api/download/cancel/{task_id}")
def cancel_media_download(task_id: str):
    task = DOWNLOAD_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="找不到下載任務")
    with task["lock"]:
        task["generation"] += 1
        task["control"] = "cancel"
        task["status"] = "cancelled"
        task["stage"] = "已終止下載"
        proc = task.get("proc")
        task["proc"] = None
        video_id = task["video_id"]
    terminate_process_tree(proc)
    cleanup_partial_files(DOWNLOADS_DIR, video_id)
    return {"status": "cancelled"}


@app.get("/api/download/status/{task_id}")
def get_download_status(task_id: str):
    task = DOWNLOAD_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="找不到下載任務")
    return {
        "status": task["status"],
        "percent": task["percent"],
        "stage": task["stage"],
        "filename": task["filename"],
        "error": task["error"],
    }


@app.get("/api/download/file/{task_id}")
def get_download_file(task_id: str):
    task = DOWNLOAD_TASKS.get(task_id)
    if not task or task["status"] != "done" or not task["file_path"]:
        raise HTTPException(status_code=404, detail="檔案尚未就緒或已過期")
    file_path = Path(task["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="找不到輸出檔案")
    media_type = "audio/mpeg" if task["format"] == "mp3" else "video/mp4"
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
    )


class TranscriptDownloadRequest(BaseModel):
    url: str
    format: Literal["txt", "srt"] = "txt"
    translate_to_zh_tw: bool = False
    api_key: str | None = None


@app.post("/api/transcript/download")
def download_transcript(req: TranscriptDownloadRequest):
    try:
        video_id = extract_video_id(req.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    meta = get_video_metadata(canonical_url, video_id)
    transcript = get_transcript(video_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail="此影片沒有提供任何文字字幕，無法下載逐字稿。")

    content = (
        format_transcript_as_srt(transcript.snippets)
        if req.format == "srt"
        else transcript.text + "\n"
    )

    is_already_zh_tw = transcript.language_code.lower() in {"zh-tw", "zh-hant"}
    if req.translate_to_zh_tw and not is_already_zh_tw:
        try:
            content = translate_transcript_to_zh_tw(content, api_key_override=req.api_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"繁體中文轉換失敗：{exc}") from exc

    safe_title = re.sub(r'[\\/:*?"<>|]+', "_", meta.title)[:60].strip() or video_id
    suffix = "_zh-TW" if req.translate_to_zh_tw else ""
    filename = f"{safe_title} [{video_id}]{suffix}.{req.format}"
    encoded_name = quote(filename)

    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@app.post("/api/transcript/translate", response_model=TranslateTranscriptResponse)
def translate_saved_transcript(req: TranslateTranscriptRequest):
    try:
        video_id = extract_video_id(req.video_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = get_history(video_id)
    analysis = (record or {}).get("analysis", {})
    orig_lines = analysis.get("transcript_lines") or []
    zh_lines = analysis.get("transcript_zh_tw_lines") or []
    lang = str(analysis.get("transcript_language") or "")

    if zh_lines:
        return TranslateTranscriptResponse(
            video_id=video_id,
            transcript_language=lang,
            transcript_lines=[TranscriptLine(**item) for item in orig_lines],
            transcript_zh_tw_lines=[TranscriptLine(**item) for item in zh_lines],
            cached=True,
        )

    if not orig_lines:
        transcript = get_transcript(video_id)
        if transcript is None:
            raise HTTPException(
                status_code=404,
                detail="此影片沒有提供文字字幕，無法取得逐字稿。",
            )
        orig_lines = [line.model_dump() for line in _snippets_to_lines(transcript.snippets)]
        lang = transcript.language_code

    try:
        translated = translate_transcript_lines_to_zh_tw(
            orig_lines,
            language_code=lang,
            api_key_override=req.api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"繁體中文轉換失敗：{exc}") from exc

    update_history_transcript(
        video_id=video_id,
        transcript_lines=orig_lines,
        transcript_zh_tw_lines=translated,
        transcript_language=lang,
    )

    return TranslateTranscriptResponse(
        video_id=video_id,
        transcript_language=lang,
        transcript_lines=[TranscriptLine(**item) for item in orig_lines],
        transcript_zh_tw_lines=[TranscriptLine(**item) for item in translated],
        cached=False,
    )


class HistoryStateUpdateRequest(BaseModel):
    mastered_ids: list[str] = Field(default_factory=list)
    chat_messages: list[dict] = Field(default_factory=list)


@app.get("/api/history")
def get_history_list():
    return {"items": list_history()}


@app.get("/api/history/{video_id}")
def get_history_detail(video_id: str):
    try:
        record = get_history(video_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="找不到此影片的保存紀錄")
    return record


@app.put("/api/history/{video_id}/state")
def save_history_state(video_id: str, req: HistoryStateUpdateRequest):
    try:
        updated = update_history_state(video_id, req.mastered_ids, req.chat_messages)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="找不到此影片的保存紀錄")
    return {"status": "ok"}


@app.delete("/api/history/{video_id}")
def remove_history_item(video_id: str):
    try:
        deleted = delete_history(video_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="找不到此影片的保存紀錄")
    return {"status": "ok"}


FRONTEND_OUT_DIR = BASE_DIR.parent / "frontend" / "out"
if FRONTEND_OUT_DIR.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_OUT_DIR), html=True),
        name="frontend",
    )
