import { HistorySummaryItem, SavedHistoryRecord } from "@/types/knowledge";

const HISTORY_LIST_KEY = "yt_sum_offline_history_list_v1";
const HISTORY_ITEM_PREFIX = "yt_sum_offline_history_item_v1_";

export function saveCachedHistoryList(items: HistorySummaryItem[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(HISTORY_LIST_KEY, JSON.stringify(items));
  } catch {
    // ignore storage quota or privacy mode errors
  }
}

export function loadCachedHistoryList(): HistorySummaryItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(HISTORY_LIST_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as HistorySummaryItem[]) : [];
  } catch {
    return [];
  }
}

export function saveCachedHistoryItem(
  videoId: string,
  record: SavedHistoryRecord
): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(
      `${HISTORY_ITEM_PREFIX}${videoId}`,
      JSON.stringify(record)
    );
  } catch {
    // ignore storage quota or privacy mode errors
  }
}

export function loadCachedHistoryItem(
  videoId: string
): SavedHistoryRecord | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(`${HISTORY_ITEM_PREFIX}${videoId}`);
    if (!raw) return null;
    return JSON.parse(raw) as SavedHistoryRecord;
  } catch {
    return null;
  }
}

export function removeCachedHistoryItem(videoId: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(`${HISTORY_ITEM_PREFIX}${videoId}`);
    const list = loadCachedHistoryList();
    if (list.length > 0) {
      saveCachedHistoryList(list.filter((item) => item.video_id !== videoId));
    }
  } catch {
    // ignore storage errors
  }
}
