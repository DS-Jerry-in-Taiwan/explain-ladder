#!/usr/bin/env bash
# 下載 Piper TTS 語音模型（L4 影片旁白用）。
# 用法：bash assets/download_voice.sh
set -euo pipefail
OUT="assets/voices/en_US-lessac-medium.onnx"
if [ -f "$OUT" ]; then
  echo "已存在：$OUT，跳過下載"
  exit 0
fi
URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx?download=true"
echo "下載中：$URL"
curl -fL --retry 3 -o "$OUT" "$URL"
echo "完成：$OUT ($(du -h "$OUT" | cut -f1))"
