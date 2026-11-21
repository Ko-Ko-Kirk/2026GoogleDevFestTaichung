# 驗證紀錄（2026-10-28）

## 已完成的模型與雲端整合

- Agent Runtime 真實部署與遠端 `async_query`：2 次 Gemini 推論、五個 Armor 檢查點、1 筆 GCS receipt，帳本沒有修改。
- Gemini 3.1 Flash-Lite Developer API 真實推論，模型專案未綁 billing。
- LangGraph 五個 Model Armor 檢查點：prompt、工具描述、tool arguments、tool result、final response。
- 私有 Cloud Run MCP；同一 initialize 無 token 為 HTTP 403，指定 SA 的短效 ID token 為 HTTP 200。
- GCS receipt 與帳本獨立讀回；Cloud Logging 留下工具執行／拒絕紀錄。
- 六案雲端觀察見 `examples/live-cloud-results.json`；其中 server policy replay 明確使用 fixture。
- 本次投毒、無額外防護的案例沒有誘發 Gemini 越權；不能據此推論其他攻擊也不會成功。
- Model Armor 與 pin 各自於推論前攔下投毒描述；Bob 合法批准成功。
- 多語言設定前後的同一中文要求對照，見 `examples/multilingual-observation.json`。

## 本機測試

真實 MCP HTTP 六案與單元測試涵蓋 manifest 漂移、caller/server 授權、合法操作、atomic receipt、未知／部分 Armor 錯誤、成本檢查、禁止付費 fallback、私有 key、資源 ownership、cleanup 重入。`scripts/check.sh` 執行 ruff、shellcheck 與 pytest；原雲端驗收時兩份專案均通過 68 個測試。

`examples/offline-summary.json` 所有模型來源都是 `deterministic-policy-fixture`，不等於 Gemini 行為。`examples/live-armor-probe.json` 是早先獨立三筆掃描，與完整 Agent 整合分開記錄。

## 部署與 cleanup

台中先完成 Cloud Run、六案雲端觀察與 Agent Runtime 遠端 query，隨後清理；台北以獨立資源重新部署並通過真實 Gemini smoke，再清理。兩份環境均確認已記錄資源不存在，並再次執行 cleanup 通過。Runtime 完整測試使用台中環境，台北共用同一份實作，沒有重複宣稱兩次 Runtime 實驗。

專用模型 API key 已撤銷；兩份本機 execution policy 已回到預設關閉。未綁 billing 的模型專案、共用 API、雲端稽核紀錄保留。

最後監控觀察為 Model Armor 3,230.75 tokens、Cloud Run billable instance time 約 20.93 秒、Runtime CPU allocation 約 56.56 CPU 秒及 memory allocation 約 18.71 GiB 秒。這些是截至查詢時間的專案 DELTA 指標，可能延遲，不是已結算帳單；成本細節與查詢時間保存於公開驗證 JSON。

## 本次台中 Code Review 增修

台中工作目錄已更新固定雙專案流程與模型 key 綁定；87 個測試、ruff 與 shellcheck 通過，configure → plan 本機 CLI 已驗證。新流程尚未重新部署雲端；前述真實雲端結果屬原驗收版本。Review 尚有一項六案正向成功條件待修，見 [Code Review](code-review-2026-10-28.md)。台北版本與先前 ZIP／投影片維持原快照。
