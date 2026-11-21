# 獨立 Model Armor 最小測試

`armor-probe.sh` 與完整 Agent 的雲端開關分開。它只掃描三筆程式內固定的合成文字，不呼叫 Vertex、不部署容器、不建立 bucket，也不修改 floor settings 或 IAM。完整 Agent 的 `Armor` adapter 已在短效 execution policy 下完成五個檢查點實測；此腳本保留作為獨立三筆掃描。

```bash
./scripts/armor-probe.sh plan       # 只顯示輸入數量與上限，不連雲端
./scripts/armor-probe.sh preflight  # 唯讀核對 project、account、billing、API 與近期 token metrics
```

先以 `configure.sh` 填入自己的專用實驗 project 與 account。Model Armor API 必須已啟用；啟用時只指定 `modelarmor.googleapis.com`，不需要訂閱 Security Command Center Premium。所有 CLI 呼叫都使用明確的 project/account，template CLI 額外使用單次 process 的區域 endpoint，保留既有全域設定。

## 免費條件

官方 standalone Model Armor 每月前 200 萬 tokens 免費，超過會計費。[官方價格](https://cloud.google.com/security-command-center/pricing)

**project metrics 不等於 billing account 的剩餘額度。** 實測前要檢查實際計費範圍、同帳戶其他用量與最新官方條件，將有依據的判定保存在 `.state/allowance-review.json`，不可只為通過檢查填入數字。檔案需包含 `project`、`account`、`billing_account`（完整資源名稱）、`month`（UTC YYYY-MM）、`checked_at`（含時區，兩小時內）、整數 `remaining_free_tokens`（至少 10,000），及 `evidence`。這是操作者的檢查紀錄，不是 Google 核發的餘額證明。

```bash
./scripts/armor-probe.sh run --allowance-review .state/allowance-review.json
./scripts/armor-probe.sh cleanup  # 中斷後可重跑；只處理此 probe 的 template
```

每次最多三筆、每筆最多 1024 code points，不自動重試掃描。兩份專案共用本機同一 project 的月計數器，位於 `~/.local/state/devfest-model-armor/`，每月上限 10,000 code points；請求失敗也不退回預留量。此計數器不能約束其他機器、其他使用者或手動呼叫，不是帳單硬上限。

測試前，月初往前多一天的 project token 總量必須低於保守門檻。Cloud Monitoring 資料可能延遲，回傳沒有 series 只表示查詢沒有資料，不是永久免費保證。[用量指標](https://docs.cloud.google.com/model-armor/monitoring-dashboard)

## 結果與 cleanup

原始 API 判定寫入 `.state/armor-probe-<id>.json`。三種輸入是正常工具描述、投毒工具描述與直接要求忽略政策的合成攻擊。程式保存實際結果，不預設惡意內容一定被擋，也不把掃描成功視為 Agent 安全證明。

每次建立隨機名稱的 template，標上 owner，結束時確認遠端 owner 後刪除，再讀回確認不存在；中途出錯保留 state 供 cleanup。無法核對權限或 ownership 時不宣稱清理完成。API 啟用狀態會保留，不影響專案其他工作。

區域 template 需走相同區域 endpoint；使用 global endpoint 的 `PERMISSION_DENIED` 不一定是 IAM 權限不足，應先核對 endpoint。[官方排錯](https://docs.cloud.google.com/model-armor/troubleshooting)
