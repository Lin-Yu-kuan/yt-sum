import json
import re
from datetime import datetime, timezone
from pathlib import Path

from services.gemini_service import to_traditional_chinese


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HISTORY_DIR = PROJECT_ROOT / "data" / "history"


def _safe_video_path(video_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("無效的 Video ID")
    return HISTORY_DIR / f"{video_id}.json"


def save_history(
    analysis: dict,
    mastered_ids: list[str] | None = None,
    chat_messages: list[dict] | None = None,
) -> dict:
    """將影片分析結果與學習進度儲存於專案 data/history/"""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = _safe_video_path(analysis["video_id"])

    existing_mastered: list[str] = []
    existing_chat: list[dict] = []
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            existing_mastered = old.get("mastered_ids", [])
            existing_chat = old.get("chat_messages", [])
        except Exception:
            pass

    record = {
        "analysis": analysis,
        "mastered_ids": mastered_ids if mastered_ids is not None else existing_mastered,
        "chat_messages": chat_messages if chat_messages is not None else existing_chat,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def _normalize_analysis_to_zh_tw(analysis: dict) -> dict:
    """確保載入的歷史解析內容統一為台灣繁體中文（保留原文逐字稿不動）"""
    normalized = dict(analysis)
    for key in ("title", "video_summary_one_liner"):
        if isinstance(normalized.get(key), str):
            normalized[key] = to_traditional_chinese(normalized[key])

    if isinstance(normalized.get("prerequisites"), list):
        normalized["prerequisites"] = [
            {
                **item,
                **{
                    k: to_traditional_chinese(item[k])
                    for k in ("name", "why_needed", "plain_explanation")
                    if isinstance(item.get(k), str)
                },
            }
            if isinstance(item, dict)
            else item
            for item in normalized["prerequisites"]
        ]

    if isinstance(normalized.get("core_concepts"), list):
        new_concepts = []
        for item in normalized["core_concepts"]:
            if not isinstance(item, dict):
                new_concepts.append(item)
                continue
            updated = {
                **item,
                **{
                    k: to_traditional_chinese(item[k])
                    for k in ("title", "summary", "example_in_video")
                    if isinstance(item.get(k), str)
                },
            }
            if isinstance(item.get("depends_on"), list):
                updated["depends_on"] = [
                    to_traditional_chinese(dep) if isinstance(dep, str) else dep
                    for dep in item["depends_on"]
                ]
            new_concepts.append(updated)
        normalized["core_concepts"] = new_concepts

    if isinstance(normalized.get("extensions"), list):
        normalized["extensions"] = [
            {
                **item,
                **{
                    k: to_traditional_chinese(item[k])
                    for k in ("title", "description", "suggested_prompt")
                    if isinstance(item.get(k), str)
                },
            }
            if isinstance(item, dict)
            else item
            for item in normalized["extensions"]
        ]

    if isinstance(normalized.get("chapters"), list):
        normalized["chapters"] = [
            {
                **ch,
                "title": to_traditional_chinese(ch["title"]),
            }
            if isinstance(ch, dict) and isinstance(ch.get("title"), str)
            else ch
            for ch in normalized["chapters"]
        ]

    if isinstance(normalized.get("concept_guides"), list):
        normalized["concept_guides"] = [
            {
                **item,
                **{
                    k: to_traditional_chinese(item[k])
                    for k in ("title", "one_line_definition", "detailed_explanation")
                    if isinstance(item.get(k), str)
                },
            }
            if isinstance(item, dict)
            else item
            for item in normalized["concept_guides"]
        ]

    return normalized


def _normalize_record_to_zh_tw(record: dict) -> dict:
    """正規化整筆歷史紀錄中的分析與 AI 回覆為台灣繁體中文"""
    normalized = dict(record)
    if isinstance(normalized.get("analysis"), dict):
        normalized["analysis"] = _normalize_analysis_to_zh_tw(normalized["analysis"])
    if isinstance(normalized.get("chat_messages"), list):
        normalized["chat_messages"] = [
            {
                **msg,
                "content": to_traditional_chinese(msg["content"]),
            }
            if isinstance(msg, dict)
            and msg.get("role") != "user"
            and isinstance(msg.get("content"), str)
            else msg
            for msg in normalized["chat_messages"]
        ]
    return normalized


def list_history() -> list[dict]:
    """列出所有已保存的解析紀錄摘要（依時間由新到舊）"""
    if not HISTORY_DIR.exists():
        return []
    items: list[dict] = []
    for file_path in HISTORY_DIR.glob("*.json"):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            a = data.get("analysis", {})
            items.append(
                {
                    "video_id": a.get("video_id", file_path.stem),
                    "title": to_traditional_chinese(a.get("title", "未命名影片")),
                    "channel": a.get("channel", ""),
                    "level": a.get("level", "intermediate"),
                    "video_summary_one_liner": to_traditional_chinese(
                        a.get("video_summary_one_liner", "")
                    ),
                    "saved_at": data.get("saved_at", ""),
                    "mastered_count": len(data.get("mastered_ids", [])),
                    "prereq_count": len(a.get("prerequisites", [])),
                }
            )
        except Exception:
            continue
    items.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    return items


def get_history(video_id: str) -> dict | None:
    path = _safe_video_path(video_id)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    normalized = _normalize_record_to_zh_tw(raw)
    if normalized != raw:
        path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def update_history_state(
    video_id: str,
    mastered_ids: list[str],
    chat_messages: list[dict],
) -> bool:
    path = _safe_video_path(video_id)
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    data["mastered_ids"] = mastered_ids
    data["chat_messages"] = chat_messages
    data["saved_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def update_history_transcript(
    video_id: str,
    transcript_lines: list[dict] | None = None,
    transcript_zh_tw_lines: list[dict] | None = None,
    transcript_language: str | None = None,
    transcript_excerpt: str | None = None,
    transcript_source: str | None = None,
) -> bool:
    """將逐字稿原文或繁中翻譯快取寫回本機歷史紀錄"""
    path = _safe_video_path(video_id)
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    analysis = data.setdefault("analysis", {})
    if transcript_lines is not None:
        analysis["transcript_lines"] = transcript_lines
    if transcript_zh_tw_lines is not None:
        analysis["transcript_zh_tw_lines"] = transcript_zh_tw_lines
    if transcript_language is not None:
        analysis["transcript_language"] = transcript_language
    if transcript_excerpt is not None:
        analysis["transcript_excerpt"] = transcript_excerpt
    if transcript_source is not None:
        analysis["transcript_source"] = transcript_source
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def update_history_concept_guides(
    video_id: str,
    concept_guides: list[dict],
) -> bool:
    """將按需生成的觀念解說快取寫回本機歷史紀錄"""
    path = _safe_video_path(video_id)
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    analysis = data.setdefault("analysis", {})
    analysis["concept_guides"] = concept_guides
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def delete_history(video_id: str) -> bool:
    path = _safe_video_path(video_id)
    if not path.exists():
        return False
    path.unlink()
    return True
