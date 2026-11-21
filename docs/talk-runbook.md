# 台中場 40 分鐘講者手冊

配合台中簡報 r10。第 1–27 頁講 35 分鐘，最後留 5 分鐘問答；第 28–29 頁備查。[逐頁講者備註](speaker-notes.md)

封面後先用 50 秒帶過第 2 頁自介與第 3 頁的六本合著，再問台下：「Alice 可以查自己的報帳。如果她請同一個 Agent 查 Bob 的，誰會擋下來？」先讓大家猜。第一幕讓他們看到查詢成功時留下什麼，第二幕再揭曉。

## 台上要開的三個畫面

從台中專案目錄執行指令。先把終端機字放大。前兩幕現場呼叫 Vertex AI 會依用量計費。三幕都有本機回放，只需 Python 3，可以全程離線。

| 時間 | 頁次 | 操作與轉場 |
|---|---|---|
| 00:00–01:00 | 1–3 | 講題、講者自介、六本合著。 |
| 01:00–02:30 | 4 | 介紹 EXP-ALICE 和 EXP-BOB。兩次的使用者都是 Alice。 |
| 02:30–06:30 | 5–6 | 第一幕查 Alice 的單。先看金額 120 和待審核，再讀回收據。 |
| 06:30–11:30 | 7–9 | 第二幕查 Bob 的單。先請大家猜，再翻第 8 頁揭曉。第 9 頁並排兩個結果。 |
| 11:30–16:30 | 10–12 | 回到 Alice 自己的單。明說「現在來看工具說明送檢的回放」，先看工具描述的掃描結果，再看對照組。 |
| 16:30–22:00 | 13–17 | 對著架構講解 tools/list 如何送掃描、正常查詢經過的五個檢查點，以及掃描出錯時如何停止。 |
| 22:00–29:00 | 18–22 | 接著講 Manifest、Agent 與伺服器各自檢查的權限、IAM 和收據，最後用 run_id 串起紀錄。 |
| 29:00–33:30 | 23–26 | 用存檔講雲端部署、清理、Runtime、推論費用和回歸測試。 |
| 33:30–40:00 | 27 | 先收尾，35:00 開放問答。 |

### 第一幕　Alice 查自己的單

```bash
./scripts/model-project.sh smoke-vertex
```

這次程式只提供唯讀工具，提示明確指定用 get_expense 查一個單號。Hydrogen 彩排時先提出查詢 EXP-ALICE，第二輪才根據工具回傳整理答覆。看金額 120、狀態 pending、一張本機收據，以及報帳資料查詢前後的雜湊相同。

### 第二幕　Alice 查 Bob 的單

```bash
./scripts/model-project.sh smoke-vertex --check-authorization
```

只換查詢的單號，畫面左邊是使用者 Alice，右邊是 Bob 的單。台上先指向模型提出的 get_expense(EXP-BOB)，再指向 blocked_by 欄的 application_authorization。LangGraph 在送出 tools/call 前拒絕。工具執行 0 次，收據 0 張，Bob 的金額也沒有回傳。

### 第三幕　Alice 查自己的單，工具說明卻變了

```bash
python3 scripts/talk-replay.py armor
```

這是 [Model Armor 實測存檔](../examples/live-cloud-results.json)。在同一次執行中，user_prompt 通過，tool_descriptions 命中。程式停在第一次模型推論前。投影出實際推論 0 次、收據 0 張，以及 Cloud Storage 讀回結果。這案原本設定 Flash-Lite。對照組另外跑過改了工具說明而未開額外防護的條件，當次模型仍只做查詢。

### 網路不穩或全程離線

說明「接下來看先前實測的回放」，再執行該幕的指令。可以在尚未設定雲端憑證的電腦上使用。回放只讀專案內附的 JSON，全程沒有雲端 API 流量。

```bash
python3 scripts/talk-replay.py alice
python3 scripts/talk-replay.py bob
python3 scripts/talk-replay.py armor
```

前兩幕的[彩排摘要](../examples/hydrogen-stage.json)保留各自的 run_id，成功案的執行數與收據張數來自同次伺服器紀錄及持久化帳本。新的現場結果寫在本機 .state/hydrogen-expense-*/summary.json。如果模型回覆或網路狀況和當天不同，照實說明，再切到同一幕的回放。

## 成本與收尾

兩次 Vertex AI 彩排分別估算 US$0.001647 和 US$0.000801，合計 US$0.002448。這是當次 token 用量的推估，實付以帳單為準。[Vertex AI 定價](https://cloud.google.com/model-garden/pricing)

現場兩次 Hydrogen 查詢使用本機唯讀 MCP，執行時無須部署 Cloud Run 或 Agent Runtime。若另外重跑歷史雲端部署，結束後用 `./scripts/cleanup.sh --apply` 清理，再以 `./scripts/verify-cleanup.sh` 查殘留。另行為 Developer API 建立的模型金鑰可用 `./scripts/model-project.sh cleanup --apply` 撤銷。

第 27 頁收尾可以這樣說：「工具說明被動過，要在交給模型前查。Alice 能查誰的帳，要在工具執行前查。最後到底有沒有查到，就看執行紀錄。」
