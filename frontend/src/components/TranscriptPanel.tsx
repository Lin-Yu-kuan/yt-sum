"use client";

import { useMemo, useState } from "react";
import { Check, Copy, Languages, Loader2, Play, Search } from "lucide-react";
import { translateTranscript } from "@/lib/api";
import { copyTextToClipboard } from "@/lib/exportMarkdown";
import { TranscriptLine, VideoAnalysisResponse } from "@/types/knowledge";

interface TranscriptPanelProps {
  data: VideoAnalysisResponse;
  apiKey?: string;
  onSeekVideo: (seconds: number, label: string) => void;
  onTranscriptUpdated: (patch: {
    transcript_language: string;
    transcript_lines: TranscriptLine[];
    transcript_zh_tw_lines: TranscriptLine[];
  }) => void;
  onNotify?: (message: string) => void;
}

type TranscriptLangMode = "original" | "zh-tw";

export default function TranscriptPanel({
  data,
  apiKey,
  onSeekVideo,
  onTranscriptUpdated,
  onNotify,
}: TranscriptPanelProps) {
  const [langMode, setLangMode] = useState<TranscriptLangMode>("original");
  const [translating, setTranslating] = useState(false);
  const [translateError, setTranslateError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [copied, setCopied] = useState(false);

  const originalLines = data.transcript_lines ?? [];
  const zhTwLines = data.transcript_zh_tw_lines ?? [];
  const activeLines = langMode === "zh-tw" ? zhTwLines : originalLines;

  const filteredLines = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return activeLines;
    return activeLines.filter(
      (line) =>
        line.text.toLowerCase().includes(q) ||
        line.timestamp.toLowerCase().includes(q)
    );
  }, [activeLines, query]);

  const handleSelectZhTw = async () => {
    setLangMode("zh-tw");
    if (zhTwLines.length > 0 || translating) return;

    setTranslating(true);
    setTranslateError(null);
    try {
      const res = await translateTranscript({
        videoId: data.video_id,
        apiKey,
      });
      onTranscriptUpdated({
        transcript_language: res.transcript_language,
        transcript_lines: res.transcript_lines,
        transcript_zh_tw_lines: res.transcript_zh_tw_lines,
      });
      if (!res.cached) {
        onNotify?.("已完成繁體中文逐字稿轉換並快取於本機！");
      }
    } catch (err) {
      setTranslateError(
        err instanceof Error ? err.message : "繁體中文轉換失敗，請稍後再試"
      );
    } finally {
      setTranslating(false);
    }
  };

  const handleCopyAll = async () => {
    if (activeLines.length === 0) return;
    const text = activeLines
      .map((line) => `[${line.timestamp}] ${line.text}`)
      .join("\n");
    const ok = await copyTextToClipboard(text);
    if (ok) {
      setCopied(true);
      onNotify?.(
        `已複製${langMode === "zh-tw" ? "繁體中文" : "原文"}逐字稿（${activeLines.length} 行）`
      );
      setTimeout(() => setCopied(false), 2000);
    } else {
      onNotify?.("複製失敗，請確認瀏覽器剪貼簿權限");
    }
  };

  const isLegacyOrNoSubtitle = originalLines.length === 0;

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[var(--border-subtle)]">
        <div className="inline-flex items-center gap-1 p-1 rounded-lg bg-[var(--bg-page)] border border-[var(--border-subtle)]">
          <button
            type="button"
            onClick={() => {
              setLangMode("original");
              setTranslateError(null);
            }}
            className={`text-xs px-3 py-1.5 rounded-md font-medium cursor-pointer transition ${
              langMode === "original"
                ? "bg-blue-600 text-white"
                : "text-[var(--text-muted)] hover:text-[var(--text-main)]"
            }`}
          >
            原文{data.transcript_language ? ` (${data.transcript_language})` : ""}
          </button>
          <button
            type="button"
            onClick={handleSelectZhTw}
            className={`text-xs px-3 py-1.5 rounded-md font-medium inline-flex items-center gap-1.5 cursor-pointer transition ${
              langMode === "zh-tw"
                ? "bg-purple-600 text-white"
                : "text-[var(--text-muted)] hover:text-[var(--text-main)]"
            }`}
          >
            <Languages className="w-3.5 h-3.5" />
            繁體中文
          </button>
        </div>

        <div className="flex items-center gap-2 flex-1 justify-end min-w-[200px]">
          <div className="relative flex-1 max-w-xs">
            <Search className="w-3.5 h-3.5 text-[var(--text-muted)] absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜尋逐字稿關鍵字..."
              className="w-full text-xs pl-8 pr-2.5 py-1.5 rounded-lg bg-[var(--bg-page)] border border-[var(--border-subtle)] text-[var(--text-main)] focus:outline-none focus:border-blue-500"
            />
          </div>

          <button
            type="button"
            onClick={handleCopyAll}
            disabled={activeLines.length === 0}
            className={`inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border transition cursor-pointer disabled:opacity-40 ${
              copied
                ? "border-emerald-500/40 bg-emerald-500/15 text-[var(--accent-emerald)]"
                : "border-[var(--border-subtle)] bg-[var(--bg-page)] text-[var(--text-muted)] hover:text-[var(--text-main)]"
            }`}
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5" />
                已複製
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                複製全文
              </>
            )}
          </button>
        </div>
      </div>

      {/* Content Area */}
      {translating ? (
        <div className="py-12 flex flex-col items-center justify-center gap-2.5 text-xs text-[var(--text-muted)]">
          <Loader2 className="w-5 h-5 animate-spin text-[var(--accent-purple)]" />
          <p>正在轉換為台灣繁體中文逐字稿（完成後會自動快取於本機）...</p>
        </div>
      ) : translateError ? (
        <div className="p-4 rounded-xl border border-rose-500/40 bg-rose-500/10 text-xs text-[var(--accent-rose)] space-y-2">
          <p>⚠️ {translateError}</p>
          <button
            type="button"
            onClick={handleSelectZhTw}
            className="px-3 py-1.5 rounded-md bg-rose-500/20 hover:bg-rose-500/30 cursor-pointer font-medium"
          >
            重新嘗試
          </button>
        </div>
      ) : activeLines.length === 0 ? (
        <div className="p-6 rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-page)] text-center space-y-2.5">
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            {isLegacyOrNoSubtitle
              ? "此紀錄尚未儲存逐字稿（可能為無字幕影片，或為舊版解析檔）。"
              : "尚無可顯示的逐字稿內容。"}
          </p>
          {isLegacyOrNoSubtitle && (
            <button
              type="button"
              onClick={handleSelectZhTw}
              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white cursor-pointer transition"
            >
              <Languages className="w-3.5 h-3.5" />
              嘗試從 YouTube 補抓原文與繁中逐字稿
            </button>
          )}
        </div>
      ) : filteredLines.length === 0 ? (
        <div className="py-8 text-center text-xs text-[var(--text-muted)]">
          找不到符合「{query}」的逐字稿片段
        </div>
      ) : (
        <div className="space-y-1 max-h-[540px] overflow-y-auto pr-1">
          {filteredLines.map((line, idx) => (
            <div
              key={`${line.seconds}-${idx}`}
              className="group flex items-start gap-2.5 px-2.5 py-1.5 rounded-lg hover:bg-[var(--bg-elevated)]/60 transition"
            >
              <button
                type="button"
                onClick={() => onSeekVideo(line.seconds, line.timestamp)}
                title={`跳轉至 ${line.timestamp}`}
                className="shrink-0 inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 mt-0.5 rounded bg-blue-500/15 text-[var(--accent-blue)] hover:bg-blue-500/30 cursor-pointer transition"
              >
                <Play className="w-2.5 h-2.5 fill-current" />
                {line.timestamp}
              </button>
              <p className="text-xs text-[var(--text-main)] leading-relaxed flex-1">
                {line.text}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
