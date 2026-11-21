import {
  ChatMessage,
  HealthStatus,
  HistorySummaryItem,
  SavedHistoryRecord,
  TranslateTranscriptResponse,
  UserLevel,
  VideoAnalysisResponse,
} from "@/types/knowledge";

function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_BASE) return process.env.NEXT_PUBLIC_API_BASE;
  if (typeof window !== "undefined" && window.location.port === "3000") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "";
}

async function parseError(res: Response): Promise<string> {
  if (res.status === 405) {
    return "後端服務版本過舊（HTTP 405），請重新啟動本機伺服器後再試";
  }
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
  } catch {
    // ignore JSON parse failure
  }
  return `請求失敗 (HTTP ${res.status})`;
}

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await fetch(`${getApiBase()}/api/health`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function saveApiKeyToLocal(apiKey: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/api/config/key`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function analyzeVideo(params: {
  url: string;
  level: UserLevel;
  apiKey?: string;
}): Promise<VideoAnalysisResponse> {
  const res = await fetch(`${getApiBase()}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: params.url,
      level: params.level,
      api_key: params.apiKey?.trim() || null,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function sendChatFollowUp(params: {
  videoTitle: string;
  videoContext: string;
  history: ChatMessage[];
  question: string;
  apiKey?: string;
}): Promise<string> {
  const res = await fetch(`${getApiBase()}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      video_title: params.videoTitle,
      video_context: params.videoContext,
      history: params.history,
      question: params.question,
      api_key: params.apiKey?.trim() || null,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return data.answer as string;
}

export async function downloadMediaFile(
  url: string,
  format: "mp4" | "mp3"
): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(`${getApiBase()}/api/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, format }),
  });
  if (!res.ok) throw new Error(await parseError(res));

  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";\n]+)"?/i);
  const filename = match ? decodeURIComponent(match[1]) : `video.${format}`;
  const blob = await res.blob();
  return { blob, filename };
}

export class DownloadCancelledByUser extends Error {
  constructor() {
    super("已終止下載");
  }
}

export async function pauseMediaDownload(taskId: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/api/download/pause/${taskId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function resumeMediaDownload(taskId: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/api/download/resume/${taskId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function cancelMediaDownload(taskId: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/api/download/cancel/${taskId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await parseError(res));
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw new DownloadCancelledByUser();
  }
}

function abortableSleep(ms: number, signal?: AbortSignal): Promise<void> {
  throwIfAborted(signal);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DownloadCancelledByUser());
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export async function downloadMediaWithProgress(
  url: string,
  format: "mp4" | "mp3",
  onProgress: (percent: number, stage: string, isPaused: boolean) => void,
  onTaskCreated?: (taskId: string) => void,
  signal?: AbortSignal
): Promise<{ blob: Blob; filename: string }> {
  try {
    throwIfAborted(signal);
    const startRes = await fetch(`${getApiBase()}/api/download/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, format }),
      signal,
    });
    if (!startRes.ok) throw new Error(await parseError(startRes));
    const { task_id } = (await startRes.json()) as { task_id: string };
    throwIfAborted(signal);
    onTaskCreated?.(task_id);

    while (true) {
      await abortableSleep(450, signal);
      const stRes = await fetch(`${getApiBase()}/api/download/status/${task_id}`, {
        signal,
      });
      if (!stRes.ok) throw new Error(await parseError(stRes));
      const st = (await stRes.json()) as {
        status: "running" | "paused" | "done" | "cancelled" | "error";
        percent: number;
        stage: string;
        filename?: string;
        error?: string;
      };

      throwIfAborted(signal);
      onProgress(st.percent, st.stage, st.status === "paused");
      if (st.status === "cancelled") {
        throw new DownloadCancelledByUser();
      }
      if (st.status === "error") {
        throw new Error(st.error || "下載失敗");
      }
      if (st.status === "done") {
        const fileRes = await fetch(`${getApiBase()}/api/download/file/${task_id}`, {
          signal,
        });
        if (!fileRes.ok) throw new Error(await parseError(fileRes));
        const blob = await fileRes.blob();
        throwIfAborted(signal);
        return { blob, filename: st.filename || `video.${format}` };
      }
    }
  } catch (err) {
    if (
      signal?.aborted ||
      (err instanceof DOMException && err.name === "AbortError")
    ) {
      throw new DownloadCancelledByUser();
    }
    throw err;
  }
}

export async function downloadTranscriptFile(params: {
  url: string;
  format: "txt" | "srt";
  translateToZhTw: boolean;
  apiKey?: string;
}): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch(`${getApiBase()}/api/transcript/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: params.url,
      format: params.format,
      translate_to_zh_tw: params.translateToZhTw,
      api_key: params.apiKey?.trim() || null,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));

  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";\n]+)"?/i);
  const filename = match ? decodeURIComponent(match[1]) : `transcript.${params.format}`;
  const blob = await res.blob();
  return { blob, filename };
}

export async function fetchHistoryList(): Promise<HistorySummaryItem[]> {
  const res = await fetch(`${getApiBase()}/api/history`);
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return (data.items || []) as HistorySummaryItem[];
}

export async function loadHistoryItem(videoId: string): Promise<SavedHistoryRecord> {
  const res = await fetch(`${getApiBase()}/api/history/${videoId}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function updateHistoryState(
  videoId: string,
  masteredIds: string[],
  chatMessages: ChatMessage[]
): Promise<void> {
  await fetch(`${getApiBase()}/api/history/${videoId}/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mastered_ids: masteredIds,
      chat_messages: chatMessages,
    }),
  });
}

export async function deleteHistoryItem(videoId: string): Promise<void> {
  const res = await fetch(`${getApiBase()}/api/history/${videoId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function translateTranscript(params: {
  videoId: string;
  apiKey?: string;
}): Promise<TranslateTranscriptResponse> {
  const res = await fetch(`${getApiBase()}/api/transcript/translate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      video_id: params.videoId,
      api_key: params.apiKey?.trim() || null,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function transcribeTranscript(params: {
  videoId: string;
  apiKey?: string;
}): Promise<TranslateTranscriptResponse> {
  const res = await fetch(`${getApiBase()}/api/transcript/transcribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      video_id: params.videoId,
      api_key: params.apiKey?.trim() || null,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
