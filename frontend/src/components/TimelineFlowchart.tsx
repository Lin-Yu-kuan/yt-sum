"use client";

import { useMemo, useState } from "react";
import {
  ArrowDown,
  Bookmark,
  CheckCircle2,
  Clock,
  Play,
  Sparkles,
} from "lucide-react";
import {
  ChapterItem,
  CoreConceptItem,
  VideoAnalysisResponse,
} from "@/types/knowledge";

interface TimelineFlowchartProps {
  data: VideoAnalysisResponse;
  onSeekVideo: (seconds: number, label: string) => void;
  onAskInApp: (prompt: string) => void;
}

type FlowFilter = "combined" | "chapters" | "concepts";

interface ChapterGroup {
  chapter: ChapterItem | null;
  concepts: CoreConceptItem[];
}

export default function TimelineFlowchart({
  data,
  onSeekVideo,
  onAskInApp,
}: TimelineFlowchartProps) {
  const chapters = useMemo(
    () => [...(data.chapters ?? [])].sort((a, b) => a.start_seconds - b.start_seconds),
    [data.chapters]
  );
  const concepts = useMemo(
    () => [...data.core_concepts].sort((a, b) => a.seconds - b.seconds),
    [data.core_concepts]
  );

  const hasChapters = chapters.length > 0;
  const [filter, setFilter] = useState<FlowFilter>("combined");

  const groupedByChapter = useMemo<ChapterGroup[]>(() => {
    if (!hasChapters) return [];

    const groups: ChapterGroup[] = chapters.map((ch) => ({
      chapter: ch,
      concepts: [],
    }));
    const introConcepts: CoreConceptItem[] = [];

    for (const c of concepts) {
      let targetIndex = -1;
      for (let i = 0; i < chapters.length; i++) {
        if (c.seconds >= chapters[i].start_seconds) {
          targetIndex = i;
        } else {
          break;
        }
      }
      if (targetIndex >= 0) {
        groups[targetIndex].concepts.push(c);
      } else {
        introConcepts.push(c);
      }
    }

    if (introConcepts.length > 0) {
      groups.unshift({ chapter: null, concepts: introConcepts });
    }
    return groups;
  }, [chapters, concepts, hasChapters]);

  const showChaptersMode = hasChapters && filter !== "concepts";

  return (
    <div className="space-y-4">
      {/* Top Info & View Mode Switch */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-[var(--text-muted)]">
          {hasChapters
            ? `已整合 ${chapters.length} 個 YouTube 作者章節與 ${concepts.length} 個核心觀念，點擊任一節點即可跳轉影片：`
            : `依影片時間軸呈現 ${concepts.length} 個核心觀念脈絡，點擊任一節點即可跳轉影片：`}
        </p>

        {hasChapters && (
          <div className="inline-flex items-center gap-1 p-1 rounded-lg bg-[var(--bg-page)] border border-[var(--border-subtle)]">
            <button
              type="button"
              onClick={() => setFilter("combined")}
              className={`text-[11px] px-2.5 py-1 rounded-md font-medium cursor-pointer transition ${
                filter === "combined"
                  ? "bg-blue-600 text-white"
                  : "text-[var(--text-muted)] hover:text-[var(--text-main)]"
              }`}
            >
              整合流程
            </button>
            <button
              type="button"
              onClick={() => setFilter("chapters")}
              className={`text-[11px] px-2.5 py-1 rounded-md font-medium cursor-pointer transition ${
                filter === "chapters"
                  ? "bg-blue-600 text-white"
                  : "text-[var(--text-muted)] hover:text-[var(--text-main)]"
              }`}
            >
              僅 YT 章節
            </button>
            <button
              type="button"
              onClick={() => setFilter("concepts")}
              className={`text-[11px] px-2.5 py-1 rounded-md font-medium cursor-pointer transition ${
                filter === "concepts"
                  ? "bg-blue-600 text-white"
                  : "text-[var(--text-muted)] hover:text-[var(--text-main)]"
              }`}
            >
              僅核心觀念
            </button>
          </div>
        )}
      </div>

      {/* Flowchart Body */}
      <div className="p-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-page)] flex flex-col items-center">
        {/* Start Node */}
        <button
          type="button"
          onClick={() => onSeekVideo(0, "00:00")}
          className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full border border-blue-500/40 bg-blue-500/10 text-xs font-semibold text-[var(--accent-blue)] hover:bg-blue-500/20 cursor-pointer transition"
        >
          <Clock className="w-3.5 h-3.5" />
          影片起點 · 00:00
        </button>

        {showChaptersMode ? (
          groupedByChapter.map((group, gIdx) => (
            <div key={group.chapter ? `ch-${gIdx}` : "intro"} className="w-full max-w-2xl flex flex-col items-center">
              {/* Connector Arrow */}
              <div className="flex flex-col items-center py-1 text-[var(--text-muted)]">
                <div className="w-0.5 h-4 bg-blue-500/40" />
                <ArrowDown className="w-3.5 h-3.5 text-blue-500/70 -mt-1" />
              </div>

              {/* Chapter Stage Card */}
              <div className="w-full rounded-xl border border-amber-500/35 bg-[var(--bg-card)] p-3.5 space-y-2.5 shadow-sm">
                {group.chapter ? (
                  <button
                    type="button"
                    onClick={() =>
                      onSeekVideo(group.chapter!.start_seconds, group.chapter!.timestamp)
                    }
                    className="w-full flex items-center justify-between gap-2 text-left group cursor-pointer"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-500/15 text-[var(--accent-amber)] border border-amber-500/30 shrink-0 inline-flex items-center gap-1">
                        <Bookmark className="w-3 h-3" />
                        章節 {chapters.indexOf(group.chapter) + 1}
                      </span>
                      <span className="text-sm font-semibold text-[var(--text-main)] group-hover:text-[var(--accent-blue)] transition truncate">
                        {group.chapter.title}
                      </span>
                    </div>
                    <span className="shrink-0 inline-flex items-center gap-1 text-xs font-mono px-2 py-0.5 rounded bg-amber-500/15 text-[var(--accent-amber)] group-hover:bg-amber-500/25 transition">
                      <Play className="w-3 h-3 fill-current" />
                      {group.chapter.timestamp}
                    </span>
                  </button>
                ) : (
                  <div className="text-xs font-semibold text-[var(--text-muted)]">
                    序幕／章節前重點
                  </div>
                )}

                {filter === "combined" && group.concepts.length > 0 && (
                  <div className="pl-3 border-l-2 border-blue-500/30 space-y-2 pt-1">
                    {group.concepts.map((c, cIdx) => (
                      <div key={c.id} className="space-y-1.5">
                        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-page)] p-3 hover:border-blue-500/50 transition">
                          <div className="flex items-start justify-between gap-2">
                            <button
                              type="button"
                              onClick={() => onSeekVideo(c.seconds, c.timestamp)}
                              className="text-left flex-1 cursor-pointer group"
                            >
                              <div className="text-xs font-semibold text-[var(--text-main)] group-hover:text-[var(--accent-blue)] transition">
                                ◆ {c.title}
                              </div>
                              <p className="text-xs text-[var(--text-muted)] mt-1 leading-relaxed">
                                {c.summary}
                              </p>
                            </button>
                            <div className="flex flex-col items-end gap-1.5 shrink-0">
                              <button
                                type="button"
                                onClick={() => onSeekVideo(c.seconds, c.timestamp)}
                                className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded bg-blue-500/15 text-[var(--accent-blue)] hover:bg-blue-500/25 cursor-pointer transition"
                              >
                                <Play className="w-2.5 h-2.5 fill-current" />
                                {c.timestamp}
                              </button>
                              <button
                                type="button"
                                onClick={() =>
                                  onAskInApp(
                                    `請針對影片「${c.title} (${c.timestamp})」這段的觀念做更詳細的拆解與舉例：${c.summary}`
                                  )
                                }
                                title="請 AI 深入解說此節點"
                                className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--accent-blue)] hover:border-blue-500/40 cursor-pointer transition"
                              >
                                <Sparkles className="w-2.5 h-2.5" />
                                追問
                              </button>
                            </div>
                          </div>
                        </div>
                        {cIdx < group.concepts.length - 1 && (
                          <div className="flex justify-center">
                            <ArrowDown className="w-3 h-3 text-blue-500/50" />
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))
        ) : (
          concepts.map((c, idx) => (
            <div key={c.id} className="w-full max-w-2xl flex flex-col items-center">
              <div className="flex flex-col items-center py-1">
                <div className="w-0.5 h-4 bg-blue-500/40" />
                <ArrowDown className="w-3.5 h-3.5 text-blue-500/70 -mt-1" />
              </div>

              <div className="w-full rounded-xl border border-blue-500/35 bg-[var(--bg-card)] p-3.5 hover:border-blue-400 transition">
                <div className="flex items-start justify-between gap-3">
                  <button
                    type="button"
                    onClick={() => onSeekVideo(c.seconds, c.timestamp)}
                    className="text-left flex-1 cursor-pointer group"
                  >
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-500/15 text-[var(--accent-blue)] shrink-0">
                        步驟 {idx + 1}
                      </span>
                      <h4 className="text-sm font-semibold text-[var(--text-main)] group-hover:text-[var(--accent-blue)] transition">
                        {c.title}
                      </h4>
                    </div>
                    <p className="text-xs text-[var(--text-muted)] mt-1.5 leading-relaxed">
                      {c.summary}
                    </p>
                  </button>

                  <div className="flex flex-col items-end gap-1.5 shrink-0">
                    <button
                      type="button"
                      onClick={() => onSeekVideo(c.seconds, c.timestamp)}
                      className="inline-flex items-center gap-1 text-xs font-mono px-2 py-0.5 rounded bg-blue-500/15 text-[var(--accent-blue)] hover:bg-blue-500/25 cursor-pointer transition"
                    >
                      <Play className="w-3 h-3 fill-current" />
                      {c.timestamp}
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        onAskInApp(
                          `請針對影片「${c.title} (${c.timestamp})」這段的觀念做更詳細的拆解與舉例：${c.summary}`
                        )
                      }
                      className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--accent-blue)] hover:border-blue-500/40 cursor-pointer transition"
                    >
                      <Sparkles className="w-2.5 h-2.5" />
                      深入問
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))
        )}

        {/* End Summary Node */}
        <div className="flex flex-col items-center py-1">
          <div className="w-0.5 h-4 bg-emerald-500/40" />
          <ArrowDown className="w-3.5 h-3.5 text-emerald-500/70 -mt-1" />
        </div>
        <div className="w-full max-w-2xl rounded-xl border border-emerald-500/35 bg-emerald-500/10 p-3.5 flex items-start gap-2.5">
          <CheckCircle2 className="w-4 h-4 text-[var(--accent-emerald)] shrink-0 mt-0.5" />
          <div className="text-xs leading-relaxed">
            <span className="font-semibold text-[var(--accent-emerald)]">核心總結：</span>
            <span className="text-[var(--text-main)]">{data.video_summary_one_liner}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
