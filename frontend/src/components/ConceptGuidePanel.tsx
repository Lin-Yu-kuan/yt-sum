"use client";

import { useState } from "react";
import {
  BookOpen,
  Check,
  Compass,
  Copy,
  Lightbulb,
  Link2,
  Loader2,
  RefreshCw,
  Sparkles,
  Target,
} from "lucide-react";
import MarkdownContent from "@/components/MarkdownContent";
import { generateConceptGuides } from "@/lib/api";
import {
  buildConceptGuidesNotionMarkdown,
  copyTextToClipboard,
} from "@/lib/exportMarkdown";
import {
  ConceptGuideItem,
  ConceptOverview,
  VideoAnalysisResponse,
} from "@/types/knowledge";

interface ConceptGuidePanelProps {
  data: VideoAnalysisResponse;
  apiKey?: string;
  onConceptsUpdated: (payload: {
    concept_overview?: ConceptOverview | null;
    concept_guides: ConceptGuideItem[];
  }) => void;
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

  const overview = data.concept_overview ?? null;
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
      onConceptsUpdated({
        concept_overview: res.concept_overview ?? null,
        concept_guides: res.concept_guides,
      });
      if (!res.cached) {
        onNotify?.("已生成完整導師講義並快取於本機紀錄！");
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
        <p className="font-medium text-sm text-[var(--text-main)]">
          正在綜觀全片逐字稿，為你建構「端到端完整主軸講義」與關鍵環節拆解...
        </p>
        <p className="text-xs">完成後會自動保存於本機，下次開啟可直接秒開</p>
      </div>
    );
  }

  if (!overview && guides.length === 0) {
    return (
      <div className="p-6 rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-page)] text-center space-y-4">
        <div className="w-10 h-10 rounded-xl bg-blue-500/15 text-[var(--accent-blue)] flex items-center justify-center mx-auto">
          <BookOpen className="w-5 h-5" />
        </div>
        <div className="space-y-1.5 max-w-md mx-auto">
          <h3 className="text-sm font-semibold text-[var(--text-main)]">
            端到端核心主軸與實戰閉環講義
          </h3>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            站在觀眾想真正學會的角度，先建立生活化心智模型，再串起從起點到「真正可用」的完整主軸流程與避坑指南，並針對關鍵決策點深度拆解。
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
          一鍵生成導師講義
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[var(--border-subtle)]">
        <div className="text-xs text-[var(--text-muted)]">
          {overview ? (
            <>
              全片核心主軸閉環講義 ＋{" "}
              <span className="font-semibold text-[var(--text-main)]">
                {guides.length}
              </span>{" "}
              個關鍵環節深化拆解
            </>
          ) : (
            <>
              已整理{" "}
              <span className="font-semibold text-[var(--text-main)]">
                {guides.length}
              </span>{" "}
              個核心觀念解說（舊版格式）
            </>
          )}
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
            title="重新綜觀整支影片生成完整導師講義"
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

      {/* 舊版快取升級提醒 */}
      {!overview && guides.length > 0 && (
        <div className="p-3 rounded-lg border border-amber-500/35 bg-amber-500/10 text-xs text-[var(--accent-amber)] flex flex-wrap items-center justify-between gap-2">
          <span>
            💡 這是舊版條目式觀念解說。點擊「重新生成」即可升級為「端到端完整主軸流程 ＋ 心智模型 ＋ 避坑指南」導師講義。
          </span>
          <button
            type="button"
            onClick={() => handleGenerate(true)}
            className="px-2.5 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 font-medium cursor-pointer transition shrink-0"
          >
            立即升級新版
          </button>
        </div>
      )}

      {/* 第一層：全片核心主軸講義 */}
      {overview && (
        <section className="rounded-xl border border-blue-500/35 bg-[var(--bg-elevated)]/35 p-4 sm:p-5 space-y-4">
          {/* 1. 本片核心目標 */}
          <div className="space-y-1.5">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-blue-500/15 text-[var(--accent-blue)] border border-blue-500/30">
              <Target className="w-3.5 h-3.5" />
              全片核心主軸講義
            </div>
            {overview.core_question && (
              <h3 className="text-base font-semibold text-[var(--text-main)] leading-snug pt-0.5">
                {overview.core_question}
              </h3>
            )}
          </div>

          {/* 2. 整體心智模型（生活化比喻） */}
          {overview.mental_model && (
            <div className="p-3.5 rounded-lg bg-blue-500/10 border border-blue-500/25 space-y-1">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--accent-blue)]">
                <Compass className="w-3.5 h-3.5" />
                整體心智模型（先建立畫面感）
              </div>
              <p className="text-sm text-[var(--text-main)] leading-relaxed">
                {overview.mental_model}
              </p>
            </div>
          )}

          {/* 3. 端到端完整主軸與實作/原理閉環 */}
          {overview.end_to_end_guide && (
            <div className="bg-[var(--bg-page)] p-4 rounded-lg border border-[var(--border-subtle)]">
              <MarkdownContent content={overview.end_to_end_guide} />
            </div>
          )}

          {/* 4. 導師小提醒 / 避坑指南 */}
          {overview.pitfalls_and_tips && overview.pitfalls_and_tips.length > 0 && (
            <div className="p-3.5 rounded-lg bg-amber-500/10 border border-amber-500/30 space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--accent-amber)]">
                <Lightbulb className="w-3.5 h-3.5" />
                導師小提醒（避坑指南與決策建議）
              </div>
              <ul className="space-y-1.5 list-disc pl-5 text-sm text-[var(--text-main)]">
                {overview.pitfalls_and_tips.map((tip, idx) => (
                  <li key={idx} className="leading-relaxed">
                    <MarkdownContent content={tip} className="text-sm" />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {overview.core_question && (
            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={() =>
                  onAskInApp(
                    `針對這支影片的核心目標「${overview.core_question}」，我有一個操作或觀念上的延伸問題想請教：`
                  )
                }
                className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-md bg-blue-500/15 border border-blue-500/35 text-[var(--accent-blue)] hover:bg-blue-500/25 cursor-pointer transition"
              >
                <Sparkles className="w-3.5 h-3.5" />
                針對主軸繼續追問導師
              </button>
            </div>
          )}
        </section>
      )}

      {/* 第二層：關鍵環節深化拆解 */}
      {guides.length > 0 && (
        <section className="space-y-3">
          {overview && (
            <div className="flex items-center gap-2 pt-1">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                關鍵環節深化拆解（{guides.length}）
              </h4>
              <div className="h-px flex-1 bg-[var(--border-subtle)]" />
            </div>
          )}

          <div className="space-y-4">
            {guides.map((g, idx) => {
              const isCopied = copiedId === g.id;
              const researchPrompt = `請針對這部影片的關鍵觀念「${g.title}」（${g.one_line_definition}），結合整體主軸用更深入且易懂的方式延伸解說。`;
              return (
                <article
                  key={g.id || idx}
                  className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)]/35 p-4 space-y-3"
                >
                  {/* Title */}
                  <div className="flex items-start gap-2.5">
                    <span className="px-2 py-0.5 rounded text-xs font-semibold bg-blue-500/15 text-[var(--accent-blue)] border border-blue-500/30 shrink-0 mt-0.5">
                      {overview ? `深化 ${idx + 1}` : `觀念 ${idx + 1}`}
                    </span>
                    <h3 className="text-sm font-semibold text-[var(--text-main)] leading-snug">
                      {g.title}
                    </h3>
                  </div>

                  {/* 在整體中的定位 (So What?) */}
                  {g.role_in_big_picture && (
                    <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-purple-500/10 border border-purple-500/25 text-xs leading-relaxed">
                      <Link2 className="w-3.5 h-3.5 text-[var(--accent-purple)] shrink-0 mt-0.5" />
                      <div>
                        <span className="font-semibold text-[var(--accent-purple)]">
                          在整體中的定位：
                        </span>
                        <span className="text-[var(--text-main)]">
                          {g.role_in_big_picture}
                        </span>
                      </div>
                    </div>
                  )}

                  {/* 一句話精準定義 */}
                  <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/25 text-xs sm:text-sm leading-relaxed">
                    <span className="font-semibold text-[var(--accent-blue)]">
                      一句話精準定義：
                    </span>
                    <span className="text-[var(--text-main)]">
                      {g.one_line_definition}
                    </span>
                  </div>

                  {/* Markdown 系統化解說 */}
                  <div className="bg-[var(--bg-page)] p-4 rounded-lg border border-[var(--border-subtle)]">
                    <MarkdownContent content={g.detailed_explanation} />
                  </div>

                  {/* 互動按鈕 */}
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
                      onClick={() =>
                        onOpenExternalGemini(g.title, researchPrompt)
                      }
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
        </section>
      )}
    </div>
  );
}
