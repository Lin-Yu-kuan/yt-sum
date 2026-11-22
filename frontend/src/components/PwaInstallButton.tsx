"use client";

import { useEffect, useState } from "react";
import { Download, MonitorDown, Share, X } from "lucide-react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

export default function PwaInstallButton() {
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isStandalone, setIsStandalone] = useState(true);
  const [isMacSafari, setIsMacSafari] = useState(false);
  const [showSafariGuide, setShowSafariGuide] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);

    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      (window.navigator as { standalone?: boolean }).standalone === true;
    setIsStandalone(standalone);

    let swReg: ServiceWorkerRegistration | null = null;
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible" && swReg) {
        swReg.update().catch(() => {});
      }
    };

    if (window.location.port !== "3000" && "serviceWorker" in navigator) {
      navigator.serviceWorker
        .register("/sw.js")
        .then((reg) => {
          swReg = reg;
          reg.update().catch(() => {});
        })
        .catch(() => {});
      document.addEventListener("visibilitychange", handleVisibilityChange);
    }

    const ua = navigator.userAgent;
    const isMac = /Macintosh/i.test(ua);
    const isSafari = /Safari/i.test(ua) && !/Chrome|Chromium|Edg|OPR|Firefox/i.test(ua);
    setIsMacSafari(isMac && isSafari);

    const handleBeforeInstallPrompt = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
    };

    const handleAppInstalled = () => {
      setDeferredPrompt(null);
      setIsStandalone(true);
      setShowSafariGuide(false);
    };

    window.addEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
    window.addEventListener("appinstalled", handleAppInstalled);

    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
      window.removeEventListener("appinstalled", handleAppInstalled);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  if (!mounted || isStandalone) return null;
  if (!deferredPrompt && !isMacSafari) return null;

  const handleInstallClick = async () => {
    if (deferredPrompt) {
      await deferredPrompt.prompt();
      const choice = await deferredPrompt.userChoice;
      if (choice.outcome === "accepted") {
        setDeferredPrompt(null);
      }
      return;
    }
    if (isMacSafari) {
      setShowSafariGuide((v) => !v);
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={handleInstallClick}
        title="安裝為獨立視窗桌面 App"
        className="text-xs px-2.5 py-1.5 rounded-lg border border-blue-500/40 bg-blue-500/10 hover:bg-blue-500/20 text-[var(--accent-blue)] inline-flex items-center gap-1.5 cursor-pointer transition"
      >
        <MonitorDown className="w-3.5 h-3.5" />
        <span className="hidden sm:inline">安裝 App</span>
      </button>

      {showSafariGuide && isMacSafari && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4" onClick={() => setShowSafariGuide(false)}>
          <div
            className="w-full max-w-sm rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-5 space-y-3 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-blue-500/15 text-[var(--accent-blue)] flex items-center justify-center shrink-0">
                  <Download className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-[var(--text-main)]">
                    在 Mac 安裝 YT-Sum App
                  </h3>
                  <p className="text-[11px] text-[var(--text-muted)]">
                    適用 macOS Sonoma 以上版本 Safari
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowSafariGuide(false)}
                className="p-1 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-main)] cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-3.5 rounded-xl bg-[var(--bg-page)] border border-[var(--border-subtle)] text-xs leading-relaxed space-y-2 text-[var(--text-main)]">
              <p>
                1. 點選 Safari 畫面最上方選單列的「<strong>檔案</strong>」→「<strong>加入 Dock</strong>」。
              </p>
              <p className="flex items-center gap-1 text-[var(--text-muted)]">
                （或點擊工具列右側的 <Share className="w-3.5 h-3.5 inline text-[var(--accent-blue)]" /> 分享圖示 →「加入 Dock」）
              </p>
              <p>2. 確認名稱後按「加入」，即可從 Dock 直接以獨立視窗開啟！</p>
            </div>

            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setShowSafariGuide(false)}
                className="text-xs px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium cursor-pointer"
              >
                我知道了
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
