"use client";

import { useState } from "react";
import {
  BookOpen,
  Check,
  Copy,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { generateConceptGuides } from "@/lib/api";
import {
  buildConceptGuidesNotionMarkdown,
  copyTextToClipboard,
} from "@/lib/exportMarkdown";
import { ConceptGuideItem, VideoAnalysisResponse } from "@/types/knowledge";

interface ConceptGuidePanelProps {
  data: VideoAnalysisResponse;
  apiKey?: string;
  onConceptsUpdated: (guides: ConceptGuideItem[]) => void;
  onAskInApp: (prompt: string) => void;
  onOpenExternalGemini: (topicTitle: string, prompt: string) => void;
  onNotify?: (message: string) => void;
}

export default function ConceptGuidePanel({
  data,
  apiKey,
  onConceptsUpdated,
  onAskInApp,
  onOpenExternalGemini,
  onNotify,
}: ConceptGuidePanelProps) {
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const guides = data.concept_guides ?? [];

  const handleGenerate = async (force = false) => {
    if (generating) return;
    setGenerating(true);
    setError(null);
    try {
      const res = await generateConceptGuides({
        videoId: data.video_id,
        apiKey,
        force,
      });
      onConceptsUpdated(res.concept_guides);
      if (!res.cached) {
        onNotify?.("已生成觀念解說並快取於本機紀錄！");
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "觀念解說生成失敗，請稍後再試"
      );
    } finally {
      setGenerating(false);
    }
  };

  const handleCopy = async (single?: ConceptGuideItem) => {
    const key = single ? single.id : "__all__";
    const md = buildConceptGuidesNotionMarkdown(data, single);
    const ok = await copyTextToClipboard(md);
    if (ok) {
      setCopiedId(key);
      onNotify?.(
        single
          ? `已複製「${single.title}」筆記！`
          : "已複製完整觀念解說 Notion 筆記，可直接 Ctrl+V 貼上！"
      );
      setTimeout(() => {
        setCopiedId((curr) => (curr === key ? null : curr));
      }, 2000);
    } else {
      onNotify?.("複製失敗，請確認瀏覽器剪貼簿權限");
    }
  };

  if (generating) {
    return (
      <div className="py-16 flex flex-col items-center justify-center gap-3 text-xs text-[var(--text-muted)]">
        <Loader2 className="w-6 h-6 animate-spin text-[var(--accent-blue)]" />
        <p className="font-medium text-[var(--text-main)]">
          正在綜觀整支影片脈絡，為你整理不受時間軸限制的「觀念解說」...
        </p>
        <p className="text-[11px]">完成後會自動保存於本機，下次開啟可直接秒開</p>
      </div>
    );
  }

  if (guides.length === 0) {
    return (
      <div className="p-6 rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-page)] text-center space-y-4">
        <div className="w-10 h-10 rounded-xl bg-blue-500/15 text-[var(--accent-blue)] flex items-center justify-center mx-auto">
          <BookOpen className="w-5 h-5" />
        </div>
        <div className="space-y-1.5 max-w-md mx-auto">
          <h3 className="text-sm font-semibold text-[var(--text-main)]">
            全片概念整合：觀念解說
          </h3>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            跳脫影片時間順序與章節切分的限制，綜觀整支影片想傳達的核心概念，為你整理成獨立、完整、可系統化閱讀的深度解說。
          </p>
        </div>

        {error && (
          <div className="p-3 rounded-lg border border-rose-500/40 bg-rose-500/10 text-xs text-[var(--accent-rose)] max-w-md mx-auto">
            ⚠️ {error}
          </div>
        )}

        <button
          type="button"
          onClick={() => handleGenerate(false)}
          className="inline-flex items-center gap-1.5 text-xs px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium cursor-pointer transition"
        >
          <Sparkles className="w-3.5 h-3.5" />
          一鍵生成觀念解說
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[var(--border-subtle)]">
        <div className="text-xs text-[var(--text-muted)]">
          跳脫影片時間順序，綜觀全片整理出{" "}
          <span className="font-semibold text-[var(--text-main)]">
            {guides.length}
          </span>{" "}
          個核心觀念解說
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => handleCopy()}
            title="複製完整觀念解說為 Notion Markdown"
            className={`inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-md border transition cursor-pointer ${
              copiedId === "__all__"
                ? "border-emerald-500/40 bg-emerald-500/15 text-[var(--accent-emerald)]"
                : "border-[var(--border-subtle)] bg-[var(--bg-page)] text-[var(--text-muted)] hover:text-[var(--text-main)] hover:border-blue-500/50"
            }`}
          >
            {copiedId === "__all__" ? (
              <>
                <Check className="w-3.5 h-3.5" />
                已複製
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                複製 Notion
              </>
            )}
          </button>

          <button
            type="button"
            onClick={() => handleGenerate(true)}
            title="重新綜觀整支影片生成觀念解說"
            className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-page)] text-[var(--text-muted)] hover:text-[var(--text-main)] hover:border-blue-500/50 cursor-pointer transition"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            重新生成
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-lg border border-rose-500/40 bg-rose-500/10 text-xs text-[var(--accent-rose)]">
          ⚠️ {error}
        </div>
      )}

      {/* Concept Cards */}
      <div className="space-y-4">
        {guides.map((g, idx) => {
          const isCopied = copiedId === g.id;
          const researchPrompt = `請針對這部影片的核心觀念「${g.title}」（${g.one_line_definition}），用更深入且易懂的方式延伸解說與回答我的疑問。`;
          return (
            <article
              key={g.id || idx}
              className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)]/40 p-4 space-y-3"
            >
              {/* Title */}
              <div className="flex items-start gap-2.5">
                <span className="px-2 py-0.5 rounded text-xs font-semibold bg-blue-500/15 text-[var(--accent-blue)] border border-blue-500/30 shrink-0 mt-0.5">
                  觀念 {idx + 1}
                </span>
                <h3 className="text-sm font-semibold text-[var(--text-main)] leading-snug">
                  {g.title}
                </h3>
              </div>

              {/* 1. 一句話精準定義 */}
              <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/25 text-xs leading-relaxed">
                <span className="font-semibold text-[var(--accent-blue)]">
                  一句話精準定義：
                </span>
                <span className="text-[var(--text-main)]">
                  {g.one_line_definition}
                </span>
              </div>

              {/* 2. 完整系統化解說 */}
              <div className="text-xs text-[var(--text-main)] leading-relaxed whitespace-pre-wrap bg-[var(--bg-page)] p-3.5 rounded-lg border border-[var(--border-subtle)]">
                {g.detailed_explanation}
              </div>

              {/* 3. 互動按鈕 */}
              <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => handleCopy(g)}
                  className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-md border transition cursor-pointer ${
                    isCopied
                      ? "border-emerald-500/40 bg-emerald-500/15 text-[var(--accent-emerald)]"
                      : "border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-elevated)]"
                  }`}
                >
                  {isCopied ? (
                    <>
                      <Check className="w-3 h-3" />
                      已複製
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" />
                      複製
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => onOpenExternalGemini(g.title, researchPrompt)}
                  className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-md border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-elevated)] cursor-pointer"
                >
                  <Copy className="w-3 h-3" />
                  帶去 Gemini
                </button>

                <button
                  type="button"
                  onClick={() => onAskInApp(researchPrompt)}
                  className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-md bg-blue-500/15 border border-blue-500/35 text-[var(--accent-blue)] hover:bg-blue-500/25 cursor-pointer"
                >
                  <Sparkles className="w-3 h-3" />
                  深入研究
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
