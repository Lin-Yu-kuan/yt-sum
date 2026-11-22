from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class PrerequisiteItem(BaseModel):
    """前置觀念項目：看懂這部影片前必須先具備的基礎概念"""
    id: str = Field(description="唯一識別碼，例如 p1, p2")
    name: str = Field(description="前置觀念名稱（必須使用台灣繁體中文，嚴禁簡體中文，可於括號附英文專有名詞）")
    importance: Literal["required", "recommended"] = Field(
        description="必要程度：required 為必備，recommended 為建議了解"
    )
    why_needed: str = Field(description="為什麼看這部影片前需要這個觀念（1~2句，必須使用台灣繁體中文，嚴禁簡體中文）")
    plain_explanation: str = Field(description="1 分鐘白話科普解說（含生活化比喻，2~4句，必須使用台灣繁體中文，嚴禁簡體中文）")


class CoreConceptItem(BaseModel):
    """影片核心觀念項目：拆解影片實際講述的知識骨幹"""
    id: str = Field(description="唯一識別碼，例如 c1, c2")
    title: str = Field(description="核心觀念標題（必須使用台灣繁體中文，嚴禁簡體中文）")
    timestamp: str = Field(description="影片對應時間點，格式 mm:ss 或 hh:mm:ss")
    seconds: int = Field(ge=0, description="對應時間點的總秒數，供播放器跳轉")
    summary: str = Field(description="核心邏輯與觀念拆解（2~4句，必須使用台灣繁體中文，嚴禁簡體中文）")
    example_in_video: str = Field(description="影片中講者舉的例子或補充說明（必須使用台灣繁體中文，嚴禁簡體中文）")
    depends_on: list[str] = Field(
        default_factory=list,
        description="此觀念依賴哪些前置觀念或前一個核心觀念的名稱（必須使用台灣繁體中文）",
    )


class ExtensionItem(BaseModel):
    """延伸與深入研究項目"""
    id: str = Field(description="唯一識別碼，例如 e1, e2")
    type: Literal["vertical", "horizontal"] = Field(
        description="vertical 為縱向深究（底層原理/迷思），horizontal 為橫向延伸（應用/跨領域）"
    )
    title: str = Field(description="延伸或深究主題標題（必須使用台灣繁體中文，嚴禁簡體中文）")
    description: str = Field(description="簡短說明為什麼值得深入或如何延伸（1~2句，必須使用台灣繁體中文，嚴禁簡體中文）")
    suggested_prompt: str = Field(
        description="可直接送給 AI 進行深入探討的具體提問提示詞（必須使用台灣繁體中文，嚴禁簡體中文）"
    )


class GraphEdge(BaseModel):
    """知識依賴圖連線"""
    source_id: str = Field(description="來源節點 id（例如 p1 或 c1）")
    target_id: str = Field(description="目標節點 id（例如 c1 或 e1）")


class GeminiKnowledgeOutput(BaseModel):
    """Gemini 結構化輸出格式"""
    video_summary_one_liner: str = Field(description="一句話總結整部影片的核心價值（必須使用台灣繁體中文，嚴禁簡體中文）")
    prerequisites: list[PrerequisiteItem] = Field(description="3~5 個最關鍵的前置觀念")
    core_concepts: list[CoreConceptItem] = Field(description="3~7 個影片核心觀念（按時間軸排列）")
    extensions: list[ExtensionItem] = Field(description="4~6 個縱向深究與橫向延伸方向")
    graph_edges: list[GraphEdge] = Field(description="前置 -> 核心 -> 延伸 的依賴連線")


class AnalyzeRequest(BaseModel):
    url: str = Field(description="YouTube 影片網址")
    level: Literal["beginner", "intermediate", "advanced"] = Field(
        default="intermediate",
        description="使用者背景程度",
    )
    api_key: str | None = Field(
        default=None,
        description="可選：前端傳入的自備 Gemini API Key，未傳則使用後端 .env",
    )


class ChapterItem(BaseModel):
    """YouTube 影片作者劃分的章節"""
    title: str
    timestamp: str
    start_seconds: int = Field(ge=0)
    end_seconds: int | None = None


class TranscriptLine(BaseModel):
    """單行時間軸逐字稿"""
    timestamp: str
    seconds: int = Field(ge=0)
    text: str


class ConceptOverview(BaseModel):
    """全片核心主軸講義：先回答觀眾最想搞懂的核心問題，並給出端到端完整閉環"""
    core_question: str = Field(
        default="",
        description="站在觀眾視角，這支影片最核心想解決的問題或學會的目標（1句話，台灣繁體中文）",
    )
    mental_model: str = Field(
        default="",
        description="用生活化比喻建立貫穿全片的整體心智模型（2~4句，讓讀者瞬間建立畫面感，台灣繁體中文）",
    )
    end_to_end_guide: str = Field(
        default="",
        description=(
            "不跳步、不切碎的端到端完整主軸解說（使用乾淨 Markdown：### 階段/步驟標題、編號清單、條列對比、**粗體重點**）。"
            "若是實作教學片，必須從起點串到『最終真正可用』的每一個必要步驟並說明少了會怎樣；"
            "若是原理科普片，必須串起『痛點 → 運作機制 → 結果』；"
            "若是觀點方法論片，必須串起『問題 → 判斷框架 → 落地做法』。"
        ),
    )
    pitfalls_and_tips: list[str] = Field(
        default_factory=list,
        description="2~4 條導師實戰提醒、操作禁忌、避坑指南或選型決策建議（台灣繁體中文）",
    )


class ConceptGuideItem(BaseModel):
    """依附於核心主軸的關鍵觀念／環節深化拆解"""
    id: str = Field(description="唯一識別碼，例如 g1, g2")
    title: str = Field(description="觀念或關鍵環節名稱（必須使用台灣繁體中文，可於括號附英文專有名詞）")
    role_in_big_picture: str = Field(
        default="",
        description="回答 So What：這個觀念掛在主軸的哪個位置？不懂它會卡住什麼或做錯什麼決定？（1~2句，台灣繁體中文）",
    )
    one_line_definition: str = Field(
        description="一句話精準定義此觀念（必須使用台灣繁體中文，嚴禁簡體中文）"
    )
    detailed_explanation: str = Field(
        description=(
            "使用乾淨 Markdown（### 小標題、條列清單、比較表格、**粗體重點**）展開主軸中值得深化的選項比較、"
            "底層原理或進階操作，避免超過 3 行的純文字牆（必須使用台灣繁體中文，嚴禁簡體中文）"
        )
    )


class VideoAnalysisResponse(BaseModel):
    video_id: str
    title: str
    channel: str
    duration_seconds: int
    transcript_source: str
    level: Literal["beginner", "intermediate", "advanced"]
    video_summary_one_liner: str
    prerequisites: list[PrerequisiteItem]
    core_concepts: list[CoreConceptItem]
    extensions: list[ExtensionItem]
    graph_edges: list[GraphEdge]
    transcript_excerpt: str = Field(description="供後續追問對話使用的影片脈絡摘要")
    chapters: list[ChapterItem] = Field(default_factory=list, description="YouTube 作者劃分章節")
    transcript_language: str = Field(default="", description="原始字幕語言代碼")
    transcript_lines: list[TranscriptLine] = Field(default_factory=list, description="原文逐字稿行列表")
    transcript_zh_tw_lines: list[TranscriptLine] = Field(
        default_factory=list, description="繁體中文逐字稿行列表（按需翻譯後快取）"
    )
    concept_overview: ConceptOverview | None = Field(
        default=None, description="全片核心主軸講義（按需生成後快取）"
    )
    concept_guides: list[ConceptGuideItem] = Field(
        default_factory=list, description="依附於主軸的關鍵環節深化拆解（按需生成後快取）"
    )


class TranslateTranscriptRequest(BaseModel):
    video_id: str
    api_key: str | None = None


class TranscribeTranscriptRequest(BaseModel):
    video_id: str
    api_key: str | None = None


class GeminiTranscriptOutput(BaseModel):
    """Gemini 多模態聽寫逐字稿結構化輸出"""
    language_code: str = Field(
        default="zh-TW",
        description="影片口語主要語言代碼，例如 en、zh-TW、ja",
    )
    lines: list[TranscriptLine] = Field(
        default_factory=list,
        description="按時間順序排列的語意分段逐字稿，每段約 15~30 秒或一個完整語意句",
    )


class TranslateTranscriptResponse(BaseModel):
    video_id: str
    transcript_language: str = ""
    transcript_lines: list[TranscriptLine] = Field(default_factory=list)
    transcript_zh_tw_lines: list[TranscriptLine] = Field(default_factory=list)
    cached: bool = False


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class GeminiConceptGuidesOutput(BaseModel):
    """Gemini 按需生成的完整觀念解說（主軸閉環 + 關鍵深化）"""
    concept_overview: ConceptOverview | None = Field(
        default=None,
        description="貫穿全片的核心問題、心智模型、端到端完整主軸與避坑指南",
    )
    concept_guides: list[ConceptGuideItem] = Field(
        default_factory=list,
        description="2~4 個依附於主軸的關鍵環節深化拆解（例如方案比較、進階操作、底層原理），避免與主軸重複流水帳",
    )


class GenerateConceptGuidesRequest(BaseModel):
    video_id: str
    api_key: str | None = None
    force: bool = False


class GenerateConceptGuidesResponse(BaseModel):
    video_id: str
    concept_overview: ConceptOverview | None = None
    concept_guides: list[ConceptGuideItem] = Field(default_factory=list)
    cached: bool = False


class ChatRequest(BaseModel):
    video_title: str
    video_context: str
    history: list[ChatMessage] = Field(default_factory=list)
    question: str
    api_key: str | None = None


class ChatResponse(BaseModel):
    answer: str


class DownloadRequest(BaseModel):
    url: str
    format: Literal["mp4", "mp3"]
