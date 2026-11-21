# 台中專案 Code Review（2026-10-28）

範圍：LangGraph 執行路徑、manifest／授權／receipt、雙專案與模型 key、部署／cleanup、測試與驗證入口。以本機程式、SDK 介面及隔離的假資料重現；本輪沒有對 GCP 執行命令、建立資源或推論。

## P1：環境中的模型 key 可以蓋過免費專案 key（本次已修）

原本 `Cloud.load_model_key()` 只在沒有 `GEMINI_API_KEY` 時讀本機 key，`build_gemini()` 則只相信 policy 的 `model_project_unbilled`。因此查核 A 專案未綁 billing，卻可能把 shell 既有的 B 專案 key 送進模型 SDK。以兩把合成 key 重現，constructor 收到的確實是環境中的那把。

修正：建立 key 時記錄其 project/account 與 SHA-256 指紋；新 `project-pair.sh review` 在核對 billing 與建立紀錄後把指紋綁入 policy。雲端入口、本機模型 constructor 與 Runtime 注入的 key 都必須匹配；繼承的其他 key 會在推論前停止。既有 Secret Manager version 若屬於舊 key，拒絕直接沿用。

指紋防止本機設定意外混用，不是 Google 簽署的 key 來源證明，也不能取代 billing 查核。操作者本來就能修改本機 policy；本專案沒有把它宣稱為防惡意操作者的 IAM 邊界。

## P2：六案流程缺少正常／合法操作的必要成功條件（仍待修）

位置：`src/devfest_security/cloud.py` 的 `live_demo()`，目前只對 `status=error` 及 pin/server policy 兩案檢查不變條件。

重現：將模型入口替換為對六案都回傳 `blocked`、無 receipt、帳本不變。`live_demo()` 仍成功產生 report 並返回，沒有丟出失敗。正常唯讀被誤擋，或 Bob 合法批准沒有成功，都不能讓 `scripts/live-check.sh` 以失敗結束。

影響：模型或 Armor 更新後，功能退化可能被當作驗收完成。之前正常中文誤判的情況正是必須保留正向測試的原因。

建議：要求 01-normal 為 completed、有 get_expense receipt 且帳本不變；06-authorized-manager 為 completed、有 approve_expense receipt 且只有指定物件變成 approved。模型攻擊案仍記錄觀察結果，不把攻擊一定成功或 Armor 一定命中寫成固定答案。另加入兩個正向案例失敗時的退出碼測試。

## 本輪新增與驗證

- 新增固定雙專案的 plan/check/review 命令與教學，不修改 gcloud 全域預設。
- `scripts/model-project.sh setup` 可以使用明確設定的 model project/account；不自動換 project 或綁 billing。
- 87 個 pytest 測試、ruff、shellcheck 通過；新增的 19 個測試涵蓋 key 混用、建立紀錄、project 配對、billing 狀態、額度查核期限及命令列目標。
- `configure → plan` 在暫存目錄以真正的本機 CLI 跑通。
- 先前的真實雲端證據仍代表原驗收版本；這次新增的 key 綁定與 project-pair 命令尚未重新跑雲端驗收。
- 此輪只修改台中工作目錄；台北版本及先前交付的 ZIP／投影片仍為原快照。
