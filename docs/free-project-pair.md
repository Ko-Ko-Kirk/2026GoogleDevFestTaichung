# 用固定雙專案保留 Gemini 免費層

本 Demo 把模型與雲端資源放在兩個明確指定的 project。Gemini Developer API 使用未綁 billing 的模型專案；Model Armor、Cloud Run、GCS 與 Agent Runtime 使用已綁 billing 的實驗專案，並查核各服務的免費額度。程式明確設定 `vertexai=False`。[Gemini billing](https://ai.google.dev/gemini-api/docs/billing)

| 用途 | 專案設定 | 認證 |
|---|---|---|
| Gemini 推論 | `--model-project`，必須未綁 billing | 該專案建立的 API-restricted key |
| Cloud Run／Armor／Runtime／GCS | `--project`，需啟用 billing | 明確 operator 或專用 service account |

這兩個 project 會固定重用。Cloud 資源的免費額度仍依服務規則、區域與 billing account 計算；拆專案不會增加共享額度。遇到 Gemini 429 就停止，不自動建立另一個 project 或切換付費服務。[Google Cloud Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features)

## 1. 設定目標，不修改 gcloud 全域預設

```bash
./scripts/configure.sh --project YOUR_INFRA_PROJECT \
  --model-project YOUR_FREE_MODEL_PROJECT --account YOU@example.com
./scripts/project-pair.sh plan
```

`configure.sh` 與 `plan` 只處理本機檔案。兩個 project 不得相同；有尚未清理的環境時不能改目標。`plan` 會列出這組 project 的後續命令。

## 2. 建立模型專案與 key

首次建立指定專案：

```bash
./scripts/model-project.sh setup --create-project --organization YOUR_ORG_ID
```

沒有 organization 時省略該參數；專案已存在時只執行 `./scripts/model-project.sh setup`。它從本機設定取出明確的 model project 與 account，從不綁 billing。key 只允許 `generativelanguage.googleapis.com`，寫入權限 0600 的 `.state/gemini-api-key`；建立紀錄另存 project、account 與 key 的 SHA-256 指紋。

```bash
./scripts/project-pair.sh check
```

`check` 只讀取這兩個 project 的身分與 billing，所有 CLI 都帶 project/account。模型專案綁上 billing，或雲端專案沒有 active billing，立即停止。

## 3. 查核共享額度後產生短效 execution policy

```bash
cp examples/allowance-review.example.json .state/allowance-review.json
# 填入實際 project、account、billing account、UTC 查核時間與 evidence。
# evidence 應記錄共享帳戶的既有用量、剩餘免費額度、區域與查核來源。
./scripts/project-pair.sh review \
  --allowance-review .state/allowance-review.json --minutes 60
```

範本刻意過期且沒有證據，不能直接啟用。`review` 會再次只讀核對 billing、驗證本機 key 的建立紀錄，才產生 `.state/execution-policy.json`。policy 綁定兩個 project 與 key 指紋，不含 API key；期限從原查核時間計算，最多三小時。這是操作者的額度查核紀錄，並非 Google 帳單硬上限。

本機既有 `GEMINI_API_KEY` 若來自其他 key，會在推論前被拒絕。Runtime 也以相同指紋檢查 Secret Manager 引用；更換 key 時先清理原部署，避免沿用舊 secret version。舊版建立紀錄沒有指紋時，請撤銷並重新建立 key。

## 4. 執行與清理

```bash
./scripts/live-check.sh
./scripts/model-project.sh cleanup --apply
```

`live-check.sh` 結束或失敗時會嘗試清理雲端資源。模型 key 另外撤銷，未綁 billing 的模型專案保留供下次使用。每次雲端 preflight 都再查模型 billing；免費層只送合成資料，資料使用條款與模型供應在演講前重新核對。
