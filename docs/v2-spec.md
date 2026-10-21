# Explain Ladder v2 實作規格

## 範圍與相容性

基準為 v1 `18d838b`；本文件只規劃 B1–B4，不實作、不改動正在執行的 production jobs。四個 MCP tools 的既有參數名稱、順序、預設值、語意，以及回傳 JSON keys 均保持不變。只新增 optional parameters；`explain_status(job_id)`、`explain_result(job_id)` 不改 signature。既有 `levels=[]` 的處理、段落切分、scene-count validation、warnings、output paths 亦不變。

完全省略新參數時：原 English authoring `SPEC` 逐字不變、Piper 使用原模型、English page 與 built-in scenes 保留原文與字型、diagram 保留原 mmdc 指令行為。相容性的「byte-comparable」是同一版本工具與環境下不引入額外渲染差異；不承諾跨 Chromium/Manim 版本或影音 metadata 的 bitwise reproducibility。

## 1. MCP 參數與解析規則

所有新增 Python 參數均為 keyword-only；既有 positional 參數仍可照舊使用。MCP 對外仍以 named arguments 呼叫。

| Tool | 新參數 | 型別 | 宣告預設值 | 語意 |
|---|---|---|---|---|
| `explain_spec` | `lang` | `str` | `"en"` | 只接受 `en` / `zh`；`en` 回傳現有 `SPEC`，`zh` 回傳新 `SPEC_ZH`。不儲存 session language。 |
| `explain_start` | `lang` | `str` | `"en"` | job 語言；控制 page、Manim font、TTS 預設，不自動翻譯輸入。 |
| `explain_start` | `tts_engine` | `str \| None` | `None` | `None` 依語言解析：`en→piper`、`zh→edge`；明確值只接受 `piper` / `edge`。 |
| `explain_start` | `tts_voice` | `str \| None` | `None` | `edge` 為 voice short name；`piper` 為 `.onnx` 模型路徑。預設依下文解析。 |
| `explain_start` | `mermaid_theme` | `str` | `"default"` | `default` / `dark` / `forest` / `neutral` / `base`。 |
| `explain_start` | `mermaid_theme_variables` | `dict \| None` | `None` | Mermaid `themeVariables` object；`None` 或 `{}` 不建立 config。 |
| `explain_start` | `diagram_background` | `str` | `"white"` | 傳給 mmdc `-b` 的 CSS color 或 `transparent`。 |
| `explain_start` | `diagram_scale` | `int` | `2` | PNG 的 mmdc `-s`，正整數，不改 SVG scale。 |

新增 signature：

```python
explain_spec(*, lang: str = "en") -> str
explain_start(name: str, brief_md: str, diagram_mmd: str,
              narration_txt: str, manim_scenes_py: str = "",
              glossary: list = None, levels: list = None, *,
              lang: str = "en", tts_engine: str | None = None,
              tts_voice: str | None = None,
              mermaid_theme: str = "default",
              mermaid_theme_variables: dict | None = None,
              diagram_background: str = "white",
              diagram_scale: int = 2) -> str
```

### 預設值與 validation

- `edge` 未給 voice：`zh→zh-TW-HsiaoChenNeural`；`en→en-US-AriaNeural`。`piper` 未給 voice：原 `VOICE`（`assets/voices/en_US-lessac-medium.onnx` 的 absolute path）。不依語言猜測 Piper 中文模型；`lang="zh", tts_engine="piper"` 必須明確給 `tts_voice`，否則 start 拒絕並說明需提供中文模型或改用 edge。這是新組合，不影響 v1。
- 不因 voice 自動切換 engine。非 `None` voice 必須為非空字串；edge short name 檢查 `^[a-z]{2,3}-[A-Z]{2}-[A-Za-z0-9]+Neural$`，不在 start 連網列舉 voices，實際不存在的 voice 於 synthesis 明確失敗。Piper 路徑相對於 PROJECT 解析並正規化為 absolute path；只在要求 L4 時檢查 `.onnx` 及同名 `.onnx.json` 存在。無 L4 不載入模型、不連網。
- `lang`、engine、theme 不接受未知值，不默默修正大小寫；background 必須非空字串。CSS color 的實際語法交由 mmdc 檢查，不建造不完整的 CSS parser。scale 必須為真正的正整數，排除 bool。
- `mermaid_theme_variables` 必須為 dict 或 `None`；執行 `json.dumps(value, ensure_ascii=False, allow_nan=False)`，拒絕非 JSON 值（包含 NaN/Infinity/circular references）。遞迴要求 object keys 為字串，避免 Python 自動將數字 keys 轉字串。以 `ValueError("mermaid_theme_variables must be a JSON-serializable object: ...")` 回報；MCP 回傳 readable tool error。
- 所有新增 validation 必須在建立 job directory、寫入檔案及 `Popen` **之前**完成。即使是 L2-only 也驗證 option 型別。FastMCP schema 可先拒絕錯誤型別，但函式本身仍需 validation，供直接 Python tests 使用。
- 非空 themeVariables 原樣傳入，不暗改 theme；需要自訂顏色時 authoring spec 指示選 `mermaid_theme="base"`。不新增 rate、pitch、volume、fallback policy 等參數。

## 2. 中文 authoring 與呈現

### `SPEC_ZH`

另建繁體中文 spec，不改寫 English `SPEC`。內容保留 v1 所有 input、scene-count、glossary、levels、async protocol 規則，並明確寫出：

1. brief 使用「中文白話」，短句，一句一個概念；首行仍須 `# 標題`。不要求中文套用 ASD-STE100。
2. narration 為繁體中文純文字，以一個空白行分段；一段等於一個 scene、一個 TTS segment。Mermaid 中文 labels 使用引號；brief、labels、glossary 可全中文。
3. 呼叫 `explain_spec(lang="zh")` 不會設定 job；必須在 `explain_start` 再傳 `lang="zh"`。說明 TTS 與 diagram 新選項及上述 defaults。
4. built-in scenes 仍是 **4 個 English RAG scenes**。lang 只換 font，不會翻譯場景文案。需要全中文 visuals 或其他主題，須提供自己的 `manim_scenes_py`，並提供中文 glossary；不要誤用 English RAG fallback glossary。
5. topic scenes 可讀 `EXPLAIN_LANG`（`en` / `zh`）、`EXPLAIN_FONT`（解析後字型名稱）；以 `os.environ.get("EXPLAIN_FONT", "DejaVu Sans")` 指定 Manim `Text(font=...)`。`SCENE_DUR` 既有約定不變。自行使用 `Tex`/`MathTex` 的 CJK 支援不在本次保證範圍。

### L3 page

`build_page.build(..., lang="zh")` 輸出 `<html lang="zh-Hant">`。zh CSS font stack 為 `"Noto Sans CJK TC", "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif`；不依賴外部 webfont。English branch 保留目前 HTML、CSS 及 `json.dumps` 行為，預設 page bytes 不因 template 重構改變。

zh UI 固定使用下列文字（emoji、IDs、JS 行為不變）：

| 原 UI | zh UI |
|---|---|
| `Interactive Explainer` | `互動式講解` |
| subtitle 整句 | `Karpathy 的講解階梯 — 第 3 級：互動網頁。由 explain-ladder pipeline 建置。` |
| `Read` / `Diagram` / `Walkthrough` / `Glossary` | `閱讀` / `圖解` / `逐步導覽` / `術語表` |
| diagram caption 整句 | `使用 Mermaid 從 diagram.mmd 渲染的流程圖。`（保留檔名 code markup） |
| `← Prev` / `Next →` | `← 上一步` / `下一步 →` |
| `Step n / total` | `步驟 n / total` |
| ladder footer 整句 | `階梯：L1 白話短文 → L2 圖解 → L3 本頁 → L4 影片 (explainer.mp4)。`（保留 L3 bold 與檔名 code markup） |

zh 且沒有 `glossary.json` 時，使用與現有五條 RAG glossary 對應的繁體中文 term/definition 常數：文件片段、嵌入向量、向量資料庫、檢索、根據資料回答；定義忠實翻譯現有內容，不混入 English 頁面。topic glossary 優先權與現有行為不變。內容 escaping 不減弱；UI 字串進 JS 時使用 JSON encoding。

### Manim font / 環境變數

`lang=en→DejaVu Sans`；`lang=zh→Noto Sans CJK TC`（本機已安裝）。built-in `FONT` 改讀 `EXPLAIN_FONT`，未設定時再依 `EXPLAIN_LANG` 選 font，兩者皆未設定則回到 DejaVu Sans。不翻譯 built-in text、不改動畫時間軸。

`build_video.build` 在 **load_scene_classes 執行 topic module 前**暫設上述兩個 env vars，離開 import 後以 `try/finally` 還原原本環境（原本不存在則移除）；傳給每次 Manim subprocess 的 env 也明確覆寫這兩個值與 `SCENE_DUR`。不可只設定 render subprocess 而讓 module import 看不到語言。v1 topic scenes 不讀新 env vars 仍照舊；不強制修改它們，也不 monkey-patch Manim global font。

## 3. TTS 與時間語意

選 **CLI subprocess integration**，不用在 sync runner 內管理 `asyncio.run` 或共享 event loop。使用 `[sys.executable, "-m", "edge_tts", ...]`，確保使用 runner 的 project venv，不依賴 shell PATH。已檢視本機安裝的 7.3.1 CLI：支援 `--file`、`--voice`、`--write-media`；非零 return code 視為失敗。

每段依原順序序列執行：

1. 將 paragraph 以 UTF-8 寫入 `_video_work/seg{i}.txt`。
2. `sys.executable -m edge_tts --file seg{i}.txt --voice <resolved voice> --write-media seg{i}.mp3`，`subprocess.run(capture_output=True, text=True, timeout=180)`；不使用 shell、不將整段文案塞進 argv。
3. 確認成功且 MP3 非空，再執行 `ffmpeg -y -i seg{i}.mp3 -vn -ac 1 -ar 24000 -c:a pcm_s16le seg{i}.wav`，capture output、`check=True`、timeout 60 秒。
4. 確認 WAV 可用且 `wav_seconds(wav)>0`；`tts_wavs` 仍只回傳依序排列的 WAV paths。MP3/TXT 留在 workdir 供除錯，不新增 result output keys。

Piper branch 保留原 load/synthesize_wav、sample rate 與 WAV 生成方式；只有模型 path 可選。edge branch 不 import/load Piper。後續 **完全不變**：`dur = wav_seconds(wav) + 0.8`；`SCENE_DUR=f"{dur:.2f}"`；Manim 720p30；ffmpeg `apad`、`-t f"{dur:.2f}"`、AAC 160k；concat stream copy。絕不以 MP3 metadata duration 或字數估時。

網路錯誤、voice 不存在、timeout、空音訊、轉檔錯誤皆 raise `RuntimeError`，包含 engine、voice、1-based paragraph index、失敗階段及 stderr 尾端（最多 1500 chars）。不自動換 engine、不無聲改 voice、不新增 application retries。runner 既有 exception handler 將 job 設 failed，保留 L2/L3 outputs；`explain_result.error` 及 `run.log` 可讀原因，`explain_status` 仍由既有 `log_tail` 提供線索。Piper 是 caller 可明確指定後重新提交的離線替代，不是透明 fallback。開始 L4 時記錄 resolved engine/voice，方便驗收。

## 4. 單一 diagram preset 與 rendering

固定共用預設 preset：`theme=default`、`themeVariables=None`、`background=white`、PNG `scale=2`。**只有一條 diagram render path**：runner 僅呼叫一次 `render()`，該函式以同一組 options 各輸出 SVG / PNG；L2 回傳兩者，L3 原樣嵌入該 SVG，L4 呼叫收到同一 PNG path，不得各自重畫或套不同 preset。

目前 `build_video.build(..., diagram_png)` 其實未使用 diagram PNG，built-in scenes 也不顯示它。本次不增加圖卡 scene、不改 v1 visuals：維持傳入 PNG 的既有介面，將「L4 使用 PNG」界定為共用素材輸入，**不宣稱目前影片已顯示 diagram**。若未來 scenes 使用此素材，也必須沿用此 PNG；把 PNG 真正加進影片屬另一個產品決策。

- 保留 `render(mmd_path, out_dir, scale=2)` 的第三個 positional 參數；新增 `*, theme="default", theme_variables=None, background="white"`。
- `common` 繼續使用原 `--puppeteerConfigFile`、`-i`、`-b`；background 改用參數。非預設 theme 才加 `-t <theme>`，預設不額外加 `-t default`，保持原指令。
- 非空 variables 以 UTF-8 寫到 out dir 的 `mermaid-config.json`：`{"themeVariables": <dict>}`，兩次 mmdc 都帶 `-c <absolute path>`；空值不寫、不傳 `-c`。不用 global/shared config。即使同一 out dir 重跑也不讀舊 config。
- SVG 不加 `-s`，PNG 維持 `-s str(scale)`。page 的現有容器白色 CSS 屬頁面 chrome，不另行修改 SVG colors；`transparent` 則透出容器背景。
- 為使新增不合法 color/config 的失敗可被 runner 捕捉，render 目前的兩處 `sys.exit` 改成 `RuntimeError`，保留 SVG/PNG failure 訊息與 stderr。成功路徑不變；不順帶修改其他 runner 行為。

## 5. job.json 與 plumbing map

在原 job object **頂層**新增下列 keys；engine/voice 寫入解析後的 effective values，無須增加 schema version 或 request copy：

```json
{
  "lang": "zh",
  "tts_engine": "edge",
  "tts_voice": "zh-TW-HsiaoChenNeural",
  "mermaid_theme": "default",
  "mermaid_theme_variables": null,
  "diagram_background": "white",
  "diagram_scale": 2
}
```

舊 job 沒有這些 keys 必須仍可讀取、poll、取結果；runner 以 `.get` 套上述 defaults，缺 engine/voice 依 job language 解析。解析邏輯集中於 `build_video.resolve_tts_options(*, lang="en", tts_engine=None, tts_voice=None)`，回傳 `(engine, voice)`；server validation 及 `tts_wavs` 共用。helper 必須只用 stdlib、不 import Piper/Manim/edge，因 server 在 `mcp/.venv` 執行。server 可將 pipeline dir 加入 `sys.path` 後 import helper，沿用 runner 方式；模型檔案存在性在 server 的 L4 validation 處檢查。

| 檔案 / function | 變更 |
|---|---|
| `mcp/server.py` / `explain_spec`, `explain_start` | 上述 signature、`SPEC_ZH`、pre-launch validation、effective options 寫入 job；English `SPEC` 不動。 |
| `mcp/runner.py` / `main` | `render(..., scale=job.get("diagram_scale", 2), theme=..., theme_variables=..., background=...)`；`build_page(topic, out, lang=...)`；`build_video(topic, out, png, lang=..., tts_engine=..., tts_voice=...)`。保留 step/state/output keys。 |
| `pipeline/build_video.py` / `build` | `build(topic_dir, out_dir, diagram_png=None, *, lang="en", tts_engine=None, tts_voice=None)`；設定 scene import 與 render env、傳 TTS options。 |
| `pipeline/build_video.py` / `tts_wavs` | `tts_wavs(paras, workdir, *, lang="en", tts_engine=None, tts_voice=None)`；透過 resolver 分流，edge MP3→WAV，回傳型別不變。 |
| `pipeline/build_video.py` / `render_scene` | 保留所有既有 positional args，追加 `*, lang="en"`；由 language 算 font 並覆寫 child env。`wav_seconds` 不改。 |
| `pipeline/render_diagram.py` / `render` | 上述 signature、job-local JSON config、共用 flags、可被捕捉的 failure。 |
| `pipeline/build_page.py` / `build` | `build(topic_dir, out_dir, *, lang="en")`；保留 English template、新增 zh template/strings/glossary。 |
| `pipeline/manim_scenes.py` / module constants | `FONT` 從 env/language 解析；SCENE_CLASSES、所有 English text 與動畫不變。 |
| `requirements.txt` | 在 project dependencies 新增 `edge-tts==7.3.1`；不是裝到 MCP venv。系統仍需 ffmpeg、mmdc、CJK font。 |
| `pipeline/run.py` / `main` | 本次不新增 CLI flags、不改檔案；既有呼叫因 keyword defaults 自然維持 v1。v2 options 經 MCP 或 Python keyword API 使用。 |
| `mcp/test_client_v2.py`（後續實作新增） | 獨立新 tests；不改現有 `mcp/test_client.py` 或 RAG fixtures。 |

不新增可選 font 參數、不暴露環境變數給 MCP caller、不更動 public output names。

## 6. B4 驗收案例

新增 client 沿用 `mcp/test_client.py` 的 stdio session / poll 模式，但所有 checks 必須用 assertions，failed job、MCP tool error 或 timeout 必須以非零 exit 結束。既有 client 只印結果，不能只憑它的 exit code 判定 regression 成功。

### A. 中文 L4 end-to-end（需網路）

提供中文 RAG brief、中文 Mermaid labels、中文 glossary，`lang="zh"`、levels 全部，**省略 engine/voice** 以測 default；省略 topic scenes，使用恰好四段中文 narration：

```text
這是檢索增強生成。它讓語言模型根據你的文件回答問題，而不只依靠記憶。

先把文件切成小片段。把每個片段轉成嵌入向量，再存進向量資料庫。

使用者提出問題時，也把問題轉成向量。搜尋資料庫，找出最相關的文件片段。

最後，把問題和找到的片段交給語言模型。模型根據這些資料產生答案，讓回答有所依據。
```

assert job `done`；result `video_mp4.path` basename 是 `explainer.mp4`、檔案 size > 0；`ffprobe -v error -show_entries format=duration -of json <path>` 的 duration > 0；page 包含 `lang="zh-Hant"`、中文 UI、中文 brief/narration 與 CJK stack。讀本機 job.json 確認 resolved edge / `zh-TW-HsiaoChenNeural`；四個 WAV 皆有正 duration，log 顯示指定 voice。手動聽取至少一段確認中文旁白（不加入 speech recognition 依賴）。

選 built-in 四 scenes 是為了直接測預設 scene resolution、四段規則與中文 TTS，不讓 topic code 掩蓋問題。**不 assert built-in visuals 已翻成中文**，它們仍為 English RAG；另以小型直接 Python test 驗證 built-in `FONT` 在 zh env 為 Noto Sans CJK TC。再用一個一段 narration 的 topic scene smoke case，在 module import 及 `construct` 讀取 env，assert `EXPLAIN_LANG=="zh"`、`EXPLAIN_FONT=="Noto Sans CJK TC"` 並以該 font 顯示 `中文測試`；檢查 render 成功且 log 無 missing-glyph warning，人工抽幀確認非方框。此補充 case 可沿用 edge，網路測試失敗不得假裝 pass。

### B. Diagram options 確實生效（不需 TTS）

同一簡單 source `flowchart LR\n A["起點"] --> B["終點"]`，不可有 inline style 或 Mermaid init directive。提交兩個 L2+L3 jobs：預設 preset；以及 `mermaid_theme="base"`, `mermaid_theme_variables={"primaryColor":"#ff00aa","primaryBorderColor":"#112233"}`, `diagram_background="#faf0e6"`, `diagram_scale=3`。

兩者都 done；對自訂 SVG 解析 node rect 的 fill（含 stylesheet），正規化 hex / rgb 後 assert 是 `#ff00aa`，且 baseline 沒有該 node fill。檢查 config JSON 與要求一致、SVG background 為指定色（可在 style 屬性），page 嵌入完整同一 SVG。不是僅 assert SVG bytes 不同，因自動 IDs 可能造成假陽性。用 Pillow 讀 PNG：在同尺寸 diagram、相同 theme/background 的 scale=2 與 scale=3 兩次 renders，assert width/height 約 1.5 倍（容許 rounding 2 pixels）。theme/color 與 scale 比較使用分開的 baseline，避免 theme 造成 layout 差異。

### C. Validation / failure / compatibility

- MCP start 傳 variables 為 list/string 應 readable error，無 job directory 新增。直接 Python function test 傳 set value、circular dict、NaN、非字串 keys，同樣在 `Popen` 前拒絕。另測未知 lang/engine/theme、空 voice、scale=0/負值/bool。
- stub edge subprocess 為非零、timeout、空 MP3，及 ffmpeg 轉檔失敗：assert failed 與 readable engine/voice/paragraph/stage，不呼叫 Piper、不產生 video output key，已完成 page/diagram 仍可取。測試不可真的破壞環境網路。
- 比較 `explain_spec({})`、`explain_spec(lang="en")` 與 v1 literal 逐字一致；zh spec 包含「中文白話」、scene count 與 env 契約。檢查 tool schema 所有新參數皆非 required，舊參數不改。
- 跑原封不動的 `mcp/.venv/bin/python mcp/test_client.py quick` 與 `... full`，fixture 繼續讀 `demo/rag/*`；確認印出 final done，quick 的 SVG/PNG/page 存在，full 的 video 存在且 ffprobe duration > 0。另從 job.json 確認預設 en/piper/原 VOICE。
- default render 的 argv 與 v1 一致、沒有 `-t` / `-c`、PNG `-s 2`；固定 inputs 下 English page bytes 與基準完全相同。以 stub Piper 比較原 WAV synthesis 設定與 downstream `+0.8`、兩位小數、apad / concat flags，避免只測影片存在卻改了時間語意。
- 提供缺新增 keys 的舊 job fixture，status/result 可讀，runner defaults 為 v1；topic scene 不讀新 env 的原 English case 仍成功。

## 7. 風險與決策邊界

- edge 依賴外部網路與服務可用性；180 秒是每段上限而非整個 job 上限。授權、服務政策與旁白送往外部服務由部署者確認；不得把原文或憑證額外寫入 error。離線部署明確選 Piper 及合適模型。
- HTML font stack 只能指定 font，不能保證觀看者電腦已安裝。renderer 主機需 CJK font；Mermaid 依 Chromium 的系統 fallback 顯示中文，本次不為 zh 額外改 diagram font/theme，避免 preset 分歧。
- Mermaid source 自帶 styles / init directive 可能蓋過 theme variables；不承諾強制覆寫 caller source。驗收 fixtures 必須排除此類 override。
- topic scene 是既有可執行 Python，font env 是合作約定，不保證不採用它的舊 scene 會顯示中文。沒有自動翻譯或 CJK 排版/換行保證。
- v1 runner/server 已有 job.json 非 atomic 寫入與 PID race，本次不處理；不要為 v2 順帶重構 production job lifecycle。
- 唯一需產品另行決定的後續事項是是否讓 built-in scenes 全中文、以及是否實際把 diagram PNG 加入影片；本次均明確排除，避免破壞 v1 scene 數與 visuals。
