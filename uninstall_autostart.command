#!/usr/bin/env bash
set -e

PLIST_PATH="$HOME/Library/LaunchAgents/com.ytsum.server.plist"

echo "=== YT-Sum macOS 移除背景常駐服務 ==="

if [ -f "$PLIST_PATH" ]; then
    UID_NUM="$(id -u)"
    launchctl bootout "gui/$UID_NUM" "$PLIST_PATH" >/dev/null 2>&1 || launchctl unload -w "$PLIST_PATH" >/dev/null 2>&1 || true
    rm -f "$PLIST_PATH"
    echo "[完成] 已停止並移除 YT-Sum 背景常駐服務。"
    echo "之後若要使用 YT-Sum，請改為雙擊 run_app.command。"
else
    echo "[提示] 尚未安裝背景常駐服務（找不到 $PLIST_PATH）。"
fi

read -r -p "按 Enter 鍵關閉..."
