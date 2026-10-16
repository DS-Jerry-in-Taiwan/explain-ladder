# Explain Ladder Pipeline

把 Karpathy 的「四級講解 ladder」做成可執行的 pipeline：同一個主題，自動產出四種越來越好懂的格式。

| Level | 格式 | 產出 |
|---|---|---|
| L1 | ASD-STE100 風格短文 | `brief.md`（輸入） |
| L2 | 圖表 | `diagram.svg` / `diagram.png`（mmdc 渲染） |
| L3 | 互動網頁 | `index.html`（單檔，tabs＋步驟導覽＋術語表） |
| L4 | manim 動畫講解影片 | `explainer.mp4`（manim 720p30 場景＋Piper TTS 旁白＋ffmpeg mux/concat；Write/Create/FadeIn/Indicate/打字機字幕） |

靈感：Andrej Karpathy 2026-10-02 X 貼文 — 瓶頸不在 AI 生成的速度，而在人理解的速度。

## 專案結構

```
explain-ladder/
├── README.md
├── pipeline/
│   ├── run.py            # 總指揮：topic dir → 全部產出
│   ├── render_diagram.py # L2：mmdc 渲染 mermaid
│   ├── build_page.py     # L3：組裝互動式單檔 HTML
│   └── build_video.py    # L4：Piper TTS＋ffmpeg 影片
├── demo/
│   └── rag/              # 範例主題：How RAG Works
│       ├── brief.md      # L1 輸入（ASD-STE100 風格）
│       ├── diagram.mmd   # L2 輸入（mermaid 原始碼）
│       └── narration.txt # L4 輸入（旁白稿，空行分段）
├── assets/
│   ├── puppeteer.json    # mmdc 用（root 環境需 --no-sandbox）
│   └── voices/           # Piper 語音模型（本機 TTS）
└── out/                  # 產出目錄
```

## 依賴

- 專案 venv（`.venv`）：manim、piper、pillow、markdown —— `run.py` 會自動切進 venv 執行
- Piper 語音模型：`bash assets/download_voice.sh`（63MB，從 HuggingFace 下載；`.onnx.json` 已在 repo 內）
- `mmdc`（@mermaid-js/mermaid-cli）＋ chrome-headless-shell
- `ffmpeg`
- root 環境跑 mmdc 需 `--puppeteerConfigFile assets/puppeteer.json`

## 用法

```bash
# 跑範例
python3 pipeline/run.py demo/rag --out out/rag

# 換主題：複製 demo/rag 改三個輸入檔即可
cp -r demo/rag demo/my-topic
# 編輯 brief.md / diagram.mmd / narration.txt
python3 pipeline/run.py demo/my-topic --out out/my-topic
```

## L1 怎麼來？

正式版應該由 LLM 生成，prompt 模板（Karpathy 建議）：

```
Explain {topic} in ASD-STE100, about 80% of the way.
Short sentences. One idea per sentence. Plain words.
```

本專案 demo 模式用手寫的 `brief.md`，所以不需要 API key 也能跑完整條鏈。
`diagram.mmd` 與 `narration.txt` 同理：正式版由 LLM 產，demo 版手寫。
manim 場景目前是手寫的（`pipeline/manim_scenes.py`，4 個 Scene 對 4 段旁白）；
新主題把自己的 `manim_scenes.py` 放進 topic 目錄並定義 `SCENE_CLASSES` 即可，
正式版可由 LLM 生成場景程式碼。
