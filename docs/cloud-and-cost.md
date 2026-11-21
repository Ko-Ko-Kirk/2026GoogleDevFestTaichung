# Google Cloud 部署與免費額度

本實驗使用兩個專案：未綁 billing 的模型專案呼叫 Gemini Developer API；已綁 billing 的實驗專案承載 Model Armor、Cloud Run、Agent Runtime 與證據儲存。帳號與 project 都由操作者明確指定，程式不修改全域 gcloud 預設值。

免費模式固定使用 Gemini Developer API 和專用 API key。台中唯讀彩排可另外執行 `scripts/model-project.sh smoke-vertex`，以已設定的實驗專案呼叫 Vertex AI 全球端點，按 token 用量計費；MCP 和收據留在本機。雲端部署與一般 Agent 路徑仍依原本的免費額度政策執行。 [Gemini Developer API 定價](https://aistudio.google.com/docs/pricing) · [Vertex AI 定價](https://cloud.google.com/model-garden/pricing)

## 開始前

1. 用 `scripts/configure.sh --project YOUR_INFRA_PROJECT --model-project YOUR_FREE_MODEL_PROJECT --account YOU@example.com` 固定兩個 project 與帳號；`scripts/project-pair.sh plan` 列出命令。
2. `scripts/model-project.sh setup --create-project --organization YOUR_ORG` 建立指定的未綁 billing 模型專案；已有專案時省略 create/organization。key 只寫 `.state/gemini-api-key`，權限 0600，另記錄 project/account 與 SHA-256 指紋。
3. `scripts/project-pair.sh check` 只讀核對雙方 billing。另查核 infrastructure billing account 的所有 linked projects、當月用量、區域與免費額度；單一 project metrics 不能證明帳戶剩餘額度。
4. 填妥 `examples/allowance-review.example.json` 的私有副本，執行 `scripts/project-pair.sh review --allowance-review .state/allowance-review.json`。它驗證 key 建立紀錄與 billing，產生綁定 project/key 的 policy；期限從原查核時間起算，預設 60 分鐘、最多三小時。
5. `scripts/live-check.sh` 依序部署、跑 smoke、六案觀察、部署並查詢 Runtime，最後清理。失敗也會嘗試 cleanup。結束後用 `scripts/model-project.sh cleanup --apply` 另外撤銷模型 key。

完整操作例子見 [雙專案免費模型教學](free-project-pair.md)。

執行 policy 是本次操作者的成本查核紀錄，不是防竄改授權機制，也不是 Google 的硬性費用上限。缺少或過期時，雲端執行會停止；cleanup 不受過期限制。每次 preflight 會再確認模型專案未綁 billing。

## 用量限制（2026-10-28 核對）

| 項目 | Demo 設定 | 免費條件／停止條件 |
|---|---|---|
| Gemini Developer API | Gemini 4 Hydrogen、LOW thinking、每次最多 2 次推論、每次推論最多 2,048 output tokens | 未綁 billing 專案；API 錯誤即停止 |
| Model Armor | 專用 template；24 KB/scan；只開 prompt injection / jailbreak | 每月前 200 萬 tokens；先查帳戶其他使用者用量 |
| Cloud Run | us-central1、每 revision min 0 / max 1、1 CPU、256 MiB、gen1 request-based | 每月 180,000 vCPU-seconds、360,000 GiB-seconds、200 萬 requests |
| Agent Runtime | min 0 / max 1、1 CPU / 1 GiB、concurrency 1 | 平台共享免費運算／記憶體／儲存額度；不啟用額外記憶、sandbox 等服務 |
| Artifact Registry | 同區域專用 repository；MCP image 在本機建置 | 每帳單帳戶每月 0.5 GiB 儲存；不要同時保留兩場環境 |
| Cloud Storage | us-central1 regional；關閉 soft delete、versioning | 指定美國區域每月 5 GB 儲存及操作額度；US multi-region 不適用 |
| Secret Manager | 專用 secret、僅一個版本；cleanup 刪除 | 每帳戶 6 active versions、10,000 accesses/月 |
| Cloud Logging | 結構化 stdout；最多查 200 筆 | 不自動開啟所有 Data Access logs；仍需考慮共享用量 |

來源：[GCP Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features)、[Cloud Run](https://cloud.google.com/run/pricing)、[Agent Platform](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing)、[Model Armor](https://cloud.google.com/security-command-center/pricing)、[Artifact Registry](https://cloud.google.com/artifact-registry/pricing)、[Secret Manager](https://cloud.google.com/secret-manager/pricing)。

限量執行與立即清理用來控制本實驗新增用量；帳單延遲、其他工作負載與共享額度仍需另外查核，不能把 budget alert 或 min instances 0 當成零費用保證。

## 身分與授權

MCP server 與 Agent Runtime 使用不同 service account。Server 只能讀自己的 bucket，寫入權限限於 `runs/` prefix。Agent 僅有 Model Armor sanitize、Service Usage、該 Cloud Run service 的 invoker、該 Gemini secret 的 accessor，以及啟動診斷所需的 Logs Writer；沒有 Vertex prediction 或 bucket 寫入權限。

本機 smoke 使用明確的 operator credential 呼叫 Model Armor，再 impersonate 專用 agent SA 取得 Cloud Run ID token。Runtime 改用 attached service account；key 經同專案 Secret Manager 的版本引用注入，沒有序列化到 agent object、程式碼或 source ZIP。Runtime 不覆寫官方保留的環境變數。[部署與 secret reference](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/deploy-an-agent)

Alice／Bob 是伺服器設定的合成 persona，不是正式產品的終端使用者登入。Cloud Run IAM 管服務連入；server policy 管角色、租戶與物件權限。

## Model Armor 覆蓋範圍

LangGraph 明確檢查 user prompt、工具描述、tool arguments、tool result 與 final response。Google-managed MCP 原生整合不自動檢查 `tools/list`，所以仍需要 discovery 完整性檢查。MATCH_FOUND 由本應用程式決定阻擋；未完成、未知或 API 錯誤均不能視為安全通過。[MCP integration](https://docs.cloud.google.com/model-armor/model-armor-mcp-google-cloud-integration)

## 清理

`./scripts/cleanup.sh --apply` 只刪除 state 中、遠端 ownership 相符的本次資源，含 Runtime、Cloud Run、template、repository/image、bucket/objects、secret、專用 SA／role／bindings。`./scripts/model-project.sh cleanup --apply` 另外撤銷模型 key，保留未綁 billing 的專案供下次使用。

不刪 project、不解除 billing、不停用共用 APIs、不修改其他人的資源。Cloud Logging、Google-managed service identities 與 IAM 暫刪除 metadata 可能仍保留。不得以資源已刪除宣稱帳單與稽核紀錄消失。

## 多語言設定的實測修正

初次整合未指定多語言偵測，正常中文唯讀要求被判成 HIGH，Agent 在推論前停止。依官方文件在每次 sanitize request 加入 `multi_language_detection_metadata.enable_multi_language_detection=true` 後，同一要求通過五個檢查點並完成查詢。原結果保留，沒有新增 exclusion rule，也沒有調低拒絕門檻。這是一組設定前後的觀察，不能推論所有中文輸入都不再誤判。[多語言 sanitize](https://docs.cloud.google.com/model-armor/sanitize-prompts-responses)

Runtime 封裝使用本機 build 的 wheel，同時列入 `requirements` 與 `extra_packages`，固定 Python 3.12。以 SDK 支援的 `async_query` 方法接上 LangGraph，避免在 Runtime 已存在的 event loop 內再呼叫 `asyncio.run()`。已存在的同 owner Runtime 用 `scripts/cloud.sh update-runtime` 更新；不會偷偷再建一個。遠端驗證設定單次 HTTP attempt，失敗保留證據，不自動重播 query。

部署 smoke 會先以指定 service account 做 MCP initialize，對剛部署時的 HTTP 403／503 最多等待約兩分鐘；這段不呼叫模型或業務工具。若仍未就緒就停止。工具與模型請求不會因此自動重播。清理後若 IAM describe 回傳模糊的 403，只有同專案 service account 清單成功且找不到該 email 才確認不存在；沒有列舉權限仍視為驗證失敗。
