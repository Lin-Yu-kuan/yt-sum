import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Literal

from google import genai
from google.genai import types

from schemas import (
    ChatMessage,
    ConceptGuideItem,
    ConceptOverview,
    GeminiConceptGuidesOutput,
    GeminiKnowledgeOutput,
    GeminiTranscriptOutput,
)

try:
    from opencc import OpenCC
except ImportError:  # pragma: no cover - 執行環境未安裝時安全降級
    OpenCC = None  # type: ignore[assignment]

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
USER_CONFIG_DIR = PROJECT_ROOT / "data"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"
FALLBACK_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
)


LEVEL_INSTRUCTIONS = {
    "beginner": "使用者為【初學者】，請務必抓出所有專有名詞與基礎背景當作前置觀念，用生活化比喻做白話科普。",
    "intermediate": "使用者【有基礎/程式或領域常識】，請略過過於基礎的常識，聚焦在真正會卡住理解的核心前置概念與架構邏輯。",
    "advanced": "使用者為【進階領域專家】，前置觀念僅列高階關鍵依賴，重點放在深入原理、數學/系統權衡與前沿延伸研究。",
}

SYSTEM_PROMPT = """你是一位頂尖的知識架構師與學習導師，專門幫助學習者「真正看懂」YouTube 知識型與技術型影片。
請勿只做流水帳式的章節摘要！你的任務是分析整部影片的知識依賴脈絡，並嚴格遵守以下語言與結構規範：

【強制語言規範】
- 無論影片原始語言是英文、簡體中文、日文或其他任何語言，所有 JSON 欄位內容一律必須使用【台灣繁體中文】（正體中文）撰寫，嚴禁出現任何簡體字。
- 請採用台灣技術與日常慣用詞彙（例如：伺服器、軟體、影片、記憶體、資料庫、演算法、網路、程式、介面）。
- 專有名詞可於繁體中文後方以括號保留英文原文（例如：「注意力機制 (Attention)」）。

請輸出以下結構：
1. **前置觀念（Prerequisites）**：
   - 找出「若不先懂這些觀念，直接看這部影片會聽不懂或一知半解」的關鍵概念（3~5個）。
   - 說明「為什麼看這部片前需要它」，並提供「1分鐘白話科普（含比喻）」。
2. **影片摘要（Core Concepts）**：
   - 按時間軸拆解並摘要影片各段講述的核心重點（3~7個）。
   - 附上準確的 `[mm:ss]` 時間點與總秒數 `seconds`，以及影片中的實例。
   - `depends_on` 填入這個觀念依賴哪些前置觀念或前一個觀念的名稱（供關聯圖使用）。
3. **延伸與深入研究（Extensions & Deep Dive）**：
   - 分為 `vertical`（縱向深究：底層原理、常見迷思、極限條件）與 `horizontal`（橫向延伸：跨領域應用、下一步學習路線）。
   - 每個項目都要附帶一個具體、高品質的 `suggested_prompt`，方便使用者一鍵發問深入研究。
4. **觀念依賴連線（graph_edges）**：
   - 建立 `前置 id -> 核心 id` 與 `核心 id -> 延伸 id` 的合理依賴連線，方便視覺化呈現。
"""


@lru_cache(maxsize=1)
def _get_opencc():
    if OpenCC is None:
        return None
    try:
        return OpenCC("s2twp")
    except Exception:
        return None


def to_traditional_chinese(text: str) -> str:
    """將文字確定性轉換為台灣繁體中文與慣用語，避免模型混用簡體字"""
    if not text:
        return text
    converter = _get_opencc()
    if converter is None:
        return text
    return converter.convert(text)


def normalize_knowledge_to_zh_tw(output: GeminiKnowledgeOutput) -> GeminiKnowledgeOutput:
    """將解析結果中的所有文字欄位統一轉換為台灣繁體中文"""
    return output.model_copy(
        update={
            "video_summary_one_liner": to_traditional_chinese(output.video_summary_one_liner),
            "prerequisites": [
                item.model_copy(
                    update={
                        "name": to_traditional_chinese(item.name),
                        "why_needed": to_traditional_chinese(item.why_needed),
                        "plain_explanation": to_traditional_chinese(item.plain_explanation),
                    }
                )
                for item in output.prerequisites
            ],
            "core_concepts": [
                item.model_copy(
                    update={
                        "title": to_traditional_chinese(item.title),
                        "summary": to_traditional_chinese(item.summary),
                        "example_in_video": to_traditional_chinese(item.example_in_video),
                        "depends_on": [to_traditional_chinese(dep) for dep in item.depends_on],
                    }
                )
                for item in output.core_concepts
            ],
            "extensions": [
                item.model_copy(
                    update={
                        "title": to_traditional_chinese(item.title),
                        "description": to_traditional_chinese(item.description),
                        "suggested_prompt": to_traditional_chinese(item.suggested_prompt),
                    }
                )
                for item in output.extensions
            ],
        }
    )


def load_local_api_key() -> str:
    """從專案資料夾 (data/config.json) 讀取儲存的 API Key"""
    try:
        if USER_CONFIG_FILE.exists():
            data = json.loads(USER_CONFIG_FILE.read_text(encoding="utf-8"))
            key = str(data.get("gemini_api_key") or "").strip()
            if key and key != "your_gemini_api_key_here":
                return key
    except Exception:
        pass
    return ""


def save_local_api_key(api_key: str) -> None:
    """將 Gemini API Key 永久儲存於使用者本機資料夾"""
    cleaned = api_key.strip()
    if not cleaned:
        raise ValueError("API Key 不可為空")
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if USER_CONFIG_FILE.exists():
        try:
            existing = json.loads(USER_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing["gemini_api_key"] = cleaned
    USER_CONFIG_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def has_configured_api_key() -> bool:
    env_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if env_key and env_key != "your_gemini_api_key_here":
        return True
    return bool(load_local_api_key())


def _get_client(api_key_override: str | None = None) -> genai.Client:
    api_key = (
        (api_key_override or "").strip()
        or load_local_api_key()
        or (os.getenv("GEMINI_API_KEY") or "").strip()
    )
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError(
            "尚未設定 GEMINI_API_KEY。請在頁面上方 Key 設定並儲存，或於 backend/.env 填入。"
        )
    return genai.Client(api_key=api_key)


def _get_model_name() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"


def _candidate_models() -> list[str]:
    """依優先順序建立不重複的候選模型清單"""
    primary = _get_model_name()
    ordered: list[str] = []
    for name in (primary, *FALLBACK_MODELS):
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def _is_transient_gemini_error(exc: Exception) -> bool:
    """判斷是否為暫時性負載／限流錯誤（503 / 429 / 連線逾時）"""
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status in {429, 500, 502, 503, 504}:
        return True
    msg = str(exc).upper()
    return any(
        token in msg
        for token in ("503", "UNAVAILABLE", "HIGH DEMAND", "429", "RESOURCE_EXHAUSTED", "TIMED OUT")
    )


def _generate_with_fallback(
    client: genai.Client,
    contents: object,
    config: types.GenerateContentConfig,
):
    """呼叫 Gemini API，遇到 503/429 等暫時性錯誤時自動切換備援模型"""
    models = _candidate_models()
    last_exc: Exception | None = None
    for idx, model_name in enumerate(models):
        try:
            return client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            last_exc = exc
            has_next = idx < len(models) - 1
            if has_next and _is_transient_gemini_error(exc):
                time.sleep(0.5)
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("無法呼叫 Gemini 模型")


def _format_chapters_context(chapters: list[dict] | None) -> str:
    """將 YouTube 作者章節整理為精簡參考文字，協助第二層核心觀念對齊時間軸"""
    if not chapters:
        return ""
    lines = [
        f"- [{ch.get('timestamp', '00:00')}] {ch.get('title', '')}"
        for ch in chapters[:40]
        if ch.get("title")
    ]
    if not lines:
        return ""
    return "YouTube 作者劃分章節參考（請參考此時間軸對齊 core_concepts 時間點）：\n" + "\n".join(lines) + "\n\n"


def analyze_transcript_with_gemini(
    video_title: str,
    transcript_text: str,
    level: Literal["beginner", "intermediate", "advanced"],
    api_key_override: str | None = None,
    chapters: list[dict] | None = None,
) -> GeminiKnowledgeOutput:
    """使用逐字稿呼叫 Gemini 產出結構化三層知識"""
    client = _get_client(api_key_override)

    # 避免極長影片超出單次輸入建議上限，保留前 120,000 字元
    trimmed_transcript = transcript_text[:120_000]
    chapters_hint = _format_chapters_context(chapters)
    prompt = (
        f"影片標題：{video_title}\n"
        f"學習者背景設定：{LEVEL_INSTRUCTIONS[level]}\n"
        "請務必全程使用【台灣繁體中文】（正體中文）輸出所有欄位內容，嚴禁使用簡體中文。\n\n"
        f"{chapters_hint}"
        f"以下是影片逐字稿（含時間戳記）：\n{trimmed_transcript}"
    )

    response = _generate_with_fallback(
        client=client,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=GeminiKnowledgeOutput,
            temperature=0.3,
        ),
    )

    parsed = (
        response.parsed
        if response.parsed is not None
        else GeminiKnowledgeOutput.model_validate_json(response.text)
    )
    return normalize_knowledge_to_zh_tw(parsed)


def analyze_youtube_url_with_gemini(
    video_title: str,
    youtube_url: str,
    level: Literal["beginner", "intermediate", "advanced"],
    api_key_override: str | None = None,
    chapters: list[dict] | None = None,
) -> GeminiKnowledgeOutput:
    """當無法抓取字幕或本機 IP 受限時，直接將公開 YouTube 網址交由 Gemini 多模態解析"""
    client = _get_client(api_key_override)

    chapters_hint = _format_chapters_context(chapters)
    prompt = (
        f"影片標題：{video_title}\n"
        f"學習者背景設定：{LEVEL_INSTRUCTIONS[level]}\n"
        f"{chapters_hint}"
        "無法取得此影片的文字逐字稿（可能無字幕或本機受限），"
        "請直接觀看與聆聽這支 YouTube 影片的視訊與音訊內容，推估對應的時間點（`[mm:ss]` 與 `seconds`），"
        "並嚴格按照系統指令產出三層知識結構。所有輸出內容必須使用【台灣繁體中文】，嚴禁簡體中文。"
    )
    contents = types.Content(
        parts=[
            types.Part(file_data=types.FileData(file_uri=youtube_url)),
            types.Part.from_text(text=prompt),
        ]
    )
    response = _generate_with_fallback(
        client=client,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=GeminiKnowledgeOutput,
            temperature=0.3,
        ),
    )
    parsed = (
        response.parsed
        if response.parsed is not None
        else GeminiKnowledgeOutput.model_validate_json(response.text)
    )
    return normalize_knowledge_to_zh_tw(parsed)


def analyze_audio_with_gemini(
    video_title: str,
    audio_path: Path,
    level: Literal["beginner", "intermediate", "advanced"],
    api_key_override: str | None = None,
    chapters: list[dict] | None = None,
) -> GeminiKnowledgeOutput:
    """無字幕備援：上傳音訊檔給 Gemini 進行多模態分析"""
    client = _get_client(api_key_override)

    uploaded = client.files.upload(file=str(audio_path))
    try:
        chapters_hint = _format_chapters_context(chapters)
        prompt = (
            f"影片標題：{video_title}\n"
            f"學習者背景設定：{LEVEL_INSTRUCTIONS[level]}\n"
            f"{chapters_hint}"
            "這部影片沒有提供文字字幕，請直接聆聽音訊內容，推估對應的時間點（秒數），"
            "並嚴格按照系統指令產出三層知識結構。所有輸出內容必須使用【台灣繁體中文】，嚴禁簡體中文。"
        )
        response = _generate_with_fallback(
            client=client,
            contents=[uploaded, prompt],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=GeminiKnowledgeOutput,
                temperature=0.3,
            ),
        )
        parsed = (
            response.parsed
            if response.parsed is not None
            else GeminiKnowledgeOutput.model_validate_json(response.text)
        )
        return normalize_knowledge_to_zh_tw(parsed)
    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass


_TRANSCRIBE_PROMPT_TEMPLATE = """影片標題：{video_title}
這部影片沒有提供官方文字字幕，請你仔細聆聽語音內容，產出完整的時間軸逐字稿。
請嚴格遵守以下規則：
1. 【語意斷句】：以完整語意句或約 15～30 秒為一個段落切分（避免每隔 1～2 秒就切一行，以節省篇幅並保持閱讀流暢）。
2. 【時間戳記】：每段提供準確的起始時間 `timestamp`（格式 `mm:ss` 或 `hh:mm:ss`）與對應整數秒數 `seconds`。
3. 【語言規範】：保持影片原本的口語語言；若口語為中文，請一律輸出【台灣繁體中文】（正體中文），嚴禁簡體中文。
4. 【忠實聽寫】：只記錄實際聽到的講話內容，不要加入無關的評論或摘要。"""


def _format_secs_mmss(seconds: int) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _normalize_transcribed_lines(parsed: GeminiTranscriptOutput) -> tuple[str, list[dict]]:
    """清理並正規化 Gemini 多模態聽寫逐字稿輸出"""
    lang = (parsed.language_code or "").strip() or "zh-TW"
    is_zh = lang.lower().startswith("zh")
    normalized: list[dict] = []
    for item in parsed.lines:
        text = (item.text or "").strip()
        if not text:
            continue
        if is_zh:
            text = to_traditional_chinese(text)
        secs = max(0, int(item.seconds))
        ts = (item.timestamp or "").strip() or _format_secs_mmss(secs)
        normalized.append({"timestamp": ts, "seconds": secs, "text": text})
    normalized.sort(key=lambda x: x["seconds"])
    if not normalized:
        raise RuntimeError("AI 語音聽寫未回傳任何有效逐字稿內容。")
    return lang, normalized


def transcribe_audio_with_gemini(
    video_title: str,
    audio_path: Path,
    api_key_override: str | None = None,
) -> tuple[str, list[dict]]:
    """優先使用純音訊檔案呼叫 Gemini 多模態聽寫逐字稿（大幅節省 Input Token）"""
    client = _get_client(api_key_override)
    uploaded = client.files.upload(file=str(audio_path))
    try:
        prompt = _TRANSCRIBE_PROMPT_TEMPLATE.format(video_title=video_title)
        response = _generate_with_fallback(
            client=client,
            contents=[uploaded, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeminiTranscriptOutput,
                temperature=0.2,
            ),
        )
        parsed = (
            response.parsed
            if response.parsed is not None
            else GeminiTranscriptOutput.model_validate_json(response.text)
        )
        return _normalize_transcribed_lines(parsed)
    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass


def transcribe_youtube_url_with_gemini(
    video_title: str,
    youtube_url: str,
    api_key_override: str | None = None,
) -> tuple[str, list[dict]]:
    """備援：當本機無法擷取音訊時，直接透過 YouTube URL 請 Gemini 聽寫逐字稿"""
    client = _get_client(api_key_override)
    prompt = _TRANSCRIBE_PROMPT_TEMPLATE.format(video_title=video_title)
    contents = types.Content(
        parts=[
            types.Part(file_data=types.FileData(file_uri=youtube_url)),
            types.Part.from_text(text=prompt),
        ]
    )
    response = _generate_with_fallback(
        client=client,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeminiTranscriptOutput,
            temperature=0.2,
        ),
    )
    parsed = (
        response.parsed
        if response.parsed is not None
        else GeminiTranscriptOutput.model_validate_json(response.text)
    )
    return _normalize_transcribed_lines(parsed)


def chat_follow_up(
    video_title: str,
    video_context: str,
    history: list[ChatMessage],
    question: str,
    api_key_override: str | None = None,
) -> str:
    """處理 APP 內建深入追問對話"""
    client = _get_client(api_key_override)

    system = (
        "你是一位親切且專業的學習導師，請嚴格使用【台灣繁體中文】（正體中文與台灣慣用詞彙，嚴禁簡體中文）"
        "回答使用者針對這部影片觀念的深入提問。"
        "回答請清晰有條理，善用白話比喻與具體例子，避免空泛。\n\n"
        f"目前研究的影片：{video_title}\n"
        f"影片脈絡參考：\n{video_context[:30_000]}"
    )

    contents: list[types.Content] = []
    for msg in history[-10:]:
        role = "user" if msg.role == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg.content)]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=question)]))

    response = _generate_with_fallback(
        client=client,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.5,
        ),
    )
    return to_traditional_chinese(response.text) if response.text else "抱歉，暫時無法產生回覆，請再試一次。"


def translate_transcript_to_zh_tw(
    transcript_text: str,
    api_key_override: str | None = None,
) -> str:
    """將逐字稿（保留時間戳記或 SRT 編號）翻譯／轉換為台灣繁體中文"""
    client = _get_client(api_key_override)

    prompt = (
        "請將以下 YouTube 影片逐字稿完整翻譯並轉換為【台灣繁體中文】（使用台灣慣用詞彙，例如：伺服器、網域、軟體、影片）。\n"
        "重要規則：\n"
        "1. 必須嚴格保留原有的時間戳記（例如 `[01:23]` 或 SRT 時間軸 `00:01:23,000 --> ...`）與段落行數結構。\n"
        "2. 只輸出轉換後的逐字稿內容，不要加上任何多餘的開場白或結語。\n\n"
        f"{transcript_text[:120_000]}"
    )

    response = _generate_with_fallback(
        client=client,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2),
    )
    converted = to_traditional_chinese((response.text or "").strip())
    return converted or to_traditional_chinese(transcript_text)


_NUMBERED_LINE_RE = re.compile(r"^\[(\d+)\]\s*(.+)$")


def translate_transcript_lines_to_zh_tw(
    lines: list[dict],
    language_code: str = "",
    api_key_override: str | None = None,
) -> list[dict]:
    """將逐字稿行列表轉換／翻譯為台灣繁體中文，保留每行的時間軸與秒數"""
    if not lines:
        return []

    lang = (language_code or "").lower()
    # 簡體或繁體中文直接走本機 OpenCC 毫秒轉換，零 API 負擔
    if lang.startswith("zh"):
        return [
            {
                "timestamp": line["timestamp"],
                "seconds": int(line["seconds"]),
                "text": to_traditional_chinese(str(line.get("text") or "")),
            }
            for line in lines
        ]

    client = _get_client(api_key_override)
    translated_texts: list[str] = [str(line.get("text") or "") for line in lines]
    batch_size = 100

    for start in range(0, len(lines), batch_size):
        batch = lines[start : start + batch_size]
        numbered_block = "\n".join(
            f"[{idx}] {str(item.get('text') or '').replace(chr(10), ' ').strip()}"
            for idx, item in enumerate(batch)
        )
        prompt = (
            "請將以下帶編號的影片逐字稿逐行翻譯成自然流暢的【台灣繁體中文】（使用台灣慣用詞彙，嚴禁簡體字）。\n"
            "規則：\n"
            "1. 必須嚴格保留每行開頭的 `[編號]` 格式（例如 `[0] ...`），每行對應一行，不可合併或拆行。\n"
            "2. 只輸出翻譯後的行內容，不要加任何說明或結語。\n\n"
            f"{numbered_block}"
        )
        response = _generate_with_fallback(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
        for raw_line in (response.text or "").splitlines():
            m = _NUMBERED_LINE_RE.match(raw_line.strip())
            if not m:
                continue
            rel_idx = int(m.group(1))
            if 0 <= rel_idx < len(batch):
                translated_texts[start + rel_idx] = to_traditional_chinese(m.group(2).strip())

    return [
        {
            "timestamp": line["timestamp"],
            "seconds": int(line["seconds"]),
            "text": translated_texts[idx],
        }
        for idx, line in enumerate(lines)
    ]


CONCEPT_GUIDES_SYSTEM_PROMPT = """你是一位親切、思路極度清晰的 1 對 1 頂尖學習導師。
使用者已經看過影片的時間軸分段摘要，最討厭看到把完整流程或因果鏈切得零零碎碎、只講名詞卻讓人看完問「So What？這些要怎麼串起來真正使用？」的百科摘要。

你的任務是站在「真正想學會、想搞懂這支影片的觀眾」立場，先建立全片端到端完整閉環，再深化拆解關鍵環節，產出兩層結構化的學習導師講義：

【第一層：全片核心主軸講義 (`concept_overview`)】
1. `core_question`（觀眾核心目標）：
   - 先反推：點進這支影片的人，看完最想能做到什麼、解決什麼痛點或真正搞懂什麼？（1 句話精準定錨）
2. `mental_model`（整體心智模型）：
   - 用一個貫穿全片的生活化比喻先建立直覺畫面（2~4 句），讓學習者在進入細節前先看懂大局與各元件之間的關係。
3. `end_to_end_guide`（不跳步、不切碎的端到端完整主軸）：
   - 依影片性質提供完整因果／操作閉環，**絕對不可漏掉讓成果真正可用或形成閉環的關鍵步驟**：
     * **實作／操作教學型影片**：必須從「起點準備」一路串到「最終真正可用、看得到成果」的每一個必要階段（例如建置儲存架構時，從整合實體資源、建立邏輯配置，到最後必須格式化並掛載代號才能讀寫，缺一不可），並清楚說明每一步**為什麼非做不可／少了這步會怎樣**。
     * **原理／技術架構型影片**：必須完整串起「舊架構痛點 → 輸入條件 → 核心機制如何逐步運作轉換 → 產出結果與邊界」。
     * **觀點／方法論／商業型影片**：必須完整串起「核心問題 → 判斷框架 → 實務落地步驟」。
   - 排版規則：必須使用乾淨 Markdown（`### 階段標題`、編號步驟 `1. 2. 3.`、條列、` **粗體重點** `、`` `介面名稱/指令` ``），段落簡潔，**嚴禁超過 3 行的純文字牆**。
4. `pitfalls_and_tips`（導師小提醒 / 避坑指南）：
   - 提煉 2~4 條實戰提醒、操作順序禁忌（例如刪除或復原必須遵守的先後順序）、常見迷思、或新手選型決策建議。

【第二層：關鍵環節深化拆解 (`concept_guides`，2~4 個)】
- **不要**把上面主軸已經交代過的步驟重複寫成流水帳！
- 只挑選主軸中「需要展開比較的選項（如多種模式的效能/成本/容錯對比）、底層關鍵原理、或重要進階維護操作（如動態擴充、生命週期管理）」作為深化卡。
- `role_in_big_picture`：必須直接回答「So What？」——說明這個觀念掛在主軸的哪個位置？不懂它實戰上會卡住什麼或做錯什麼決定？（1~2 句）。
- `one_line_definition`：一句話精準定義其本質。
- `detailed_explanation`：使用乾淨 Markdown（`###` 小標題、條列對比、必要時使用 Markdown 比較表格 `| 方案 | ... |`、`**粗體重點**`），深入淺出把差異、為什麼與實戰取捨講透徹，禁止純文字牆。

【強制語言規範】
- 所有內容一律必須使用【台灣繁體中文】（正體中文與台灣慣用詞彙，例如：伺服器、軟體、影片、記憶體、資料庫、演算法、網路、程式、介面、磁碟區、映象），嚴禁簡體中文。
- 專有名詞可於繁體中文後方以括號保留英文原文（例如：「存放集區 (Storage Pool)」）。"""


def normalize_concept_guides_to_zh_tw(
    guides: list[ConceptGuideItem],
) -> list[ConceptGuideItem]:
    """將觀念解說列表中的所有文字欄位轉換為台灣繁體中文"""
    return [
        item.model_copy(
            update={
                "title": to_traditional_chinese(item.title),
                "role_in_big_picture": to_traditional_chinese(item.role_in_big_picture),
                "one_line_definition": to_traditional_chinese(item.one_line_definition),
                "detailed_explanation": to_traditional_chinese(item.detailed_explanation),
            }
        )
        for item in guides
    ]


def normalize_concept_output_to_zh_tw(
    output: GeminiConceptGuidesOutput,
) -> GeminiConceptGuidesOutput:
    """將完整觀念解說輸出（含主軸講義與關鍵深化）轉換為台灣繁體中文"""
    overview = output.concept_overview
    normalized_overview: ConceptOverview | None = None
    if overview is not None:
        normalized_overview = overview.model_copy(
            update={
                "core_question": to_traditional_chinese(overview.core_question),
                "mental_model": to_traditional_chinese(overview.mental_model),
                "end_to_end_guide": to_traditional_chinese(overview.end_to_end_guide),
                "pitfalls_and_tips": [
                    to_traditional_chinese(tip) for tip in overview.pitfalls_and_tips
                ],
            }
        )
    return output.model_copy(
        update={
            "concept_overview": normalized_overview,
            "concept_guides": normalize_concept_guides_to_zh_tw(output.concept_guides),
        }
    )


def generate_concept_guides_with_gemini(
    video_title: str,
    context_text: str,
    level: Literal["beginner", "intermediate", "advanced"] = "intermediate",
    api_key_override: str | None = None,
) -> GeminiConceptGuidesOutput:
    """依據影片逐字稿或脈絡，生成端到端核心主軸講義與關鍵環節深化拆解"""
    client = _get_client(api_key_override)
    prompt = (
        f"影片標題：{video_title}\n"
        f"學習者背景設定：{LEVEL_INSTRUCTIONS.get(level, LEVEL_INSTRUCTIONS['intermediate'])}\n"
        "請綜觀以下全片逐字稿與脈絡，從觀眾想真正學會與落地的角度，整理出「全片核心主軸講義（端到端完整閉環）」以及「關鍵環節深化拆解」。\n\n"
        f"{context_text[:120_000]}"
    )
    response = _generate_with_fallback(
        client=client,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=CONCEPT_GUIDES_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=GeminiConceptGuidesOutput,
            temperature=0.45,
        ),
    )
    parsed = (
        response.parsed
        if response.parsed is not None
        else GeminiConceptGuidesOutput.model_validate_json(response.text)
    )
    return normalize_concept_output_to_zh_tw(parsed)


def generate_concept_guides_from_youtube_url(
    video_title: str,
    youtube_url: str,
    level: Literal["beginner", "intermediate", "advanced"] = "intermediate",
    api_key_override: str | None = None,
    summary_hint: str = "",
) -> GeminiConceptGuidesOutput:
    """無逐字稿時的備援：直接請 Gemini 觀看 YouTube 影片生成完整觀念解說"""
    client = _get_client(api_key_override)
    hint_block = f"\n既有影片摘要參考：\n{summary_hint[:10_000]}\n" if summary_hint else ""
    prompt = (
        f"影片標題：{video_title}\n"
        f"學習者背景設定：{LEVEL_INSTRUCTIONS.get(level, LEVEL_INSTRUCTIONS['intermediate'])}\n"
        f"{hint_block}"
        "請直接觀看與聆聽這支 YouTube 影片，從觀眾想真正學會與落地的角度，整理出「全片核心主軸講義（端到端完整閉環）」以及「關鍵環節深化拆解」。"
    )
    contents = types.Content(
        parts=[
            types.Part(file_data=types.FileData(file_uri=youtube_url)),
            types.Part.from_text(text=prompt),
        ]
    )
    response = _generate_with_fallback(
        client=client,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=CONCEPT_GUIDES_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=GeminiConceptGuidesOutput,
            temperature=0.45,
        ),
    )
    parsed = (
        response.parsed
        if response.parsed is not None
        else GeminiConceptGuidesOutput.model_validate_json(response.text)
    )
    return normalize_concept_output_to_zh_tw(parsed)
