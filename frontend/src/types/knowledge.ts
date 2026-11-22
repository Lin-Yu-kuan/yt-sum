export type UserLevel = "beginner" | "intermediate" | "advanced";

export interface PrerequisiteItem {
  id: string;
  name: string;
  importance: "required" | "recommended";
  why_needed: string;
  plain_explanation: string;
}

export interface CoreConceptItem {
  id: string;
  title: string;
  timestamp: string;
  seconds: number;
  summary: string;
  example_in_video: string;
  depends_on: string[];
}

export interface ExtensionItem {
  id: string;
  type: "vertical" | "horizontal";
  title: string;
  description: string;
  suggested_prompt: string;
}

export interface GraphEdge {
  source_id: string;
  target_id: string;
}

export interface ChapterItem {
  title: string;
  timestamp: string;
  start_seconds: number;
  end_seconds?: number | null;
}

export interface TranscriptLine {
  timestamp: string;
  seconds: number;
  text: string;
}

export interface ConceptGuideItem {
  id: string;
  title: string;
  one_line_definition: string;
  detailed_explanation: string;
}

export interface GenerateConceptGuidesResponse {
  video_id: string;
  concept_guides: ConceptGuideItem[];
  cached: boolean;
}

export interface VideoAnalysisResponse {
  video_id: string;
  title: string;
  channel: string;
  duration_seconds: number;
  transcript_source: string;
  level: UserLevel;
  video_summary_one_liner: string;
  prerequisites: PrerequisiteItem[];
  core_concepts: CoreConceptItem[];
  extensions: ExtensionItem[];
  graph_edges: GraphEdge[];
  transcript_excerpt: string;
  chapters?: ChapterItem[];
  transcript_language?: string;
  transcript_lines?: TranscriptLine[];
  transcript_zh_tw_lines?: TranscriptLine[];
  concept_guides?: ConceptGuideItem[];
}

export interface TranslateTranscriptResponse {
  video_id: string;
  transcript_language: string;
  transcript_lines: TranscriptLine[];
  transcript_zh_tw_lines: TranscriptLine[];
  cached: boolean;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface HealthStatus {
  status: string;
  ffmpeg_available: boolean;
  gemini_key_configured: boolean;
  model: string;
  frontend_build_id?: string;
  backend_stale?: boolean;
  backend_started_at?: string;
}

export interface HistorySummaryItem {
  video_id: string;
  title: string;
  channel: string;
  level: UserLevel;
  video_summary_one_liner: string;
  saved_at: string;
  mastered_count: number;
  prereq_count: number;
}

export interface SavedHistoryRecord {
  analysis: VideoAnalysisResponse;
  mastered_ids: string[];
  chat_messages: ChatMessage[];
  saved_at: string;
}
