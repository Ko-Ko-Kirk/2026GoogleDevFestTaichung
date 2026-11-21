# 台中場逐頁講者備註（r10）

## 1. 從 MCP Tool Poisoning 到 Google Cloud Agent Security 實戰（00:00–00:10）

先報講題和名字。自介與書封之後，從 Alice 的報帳問題開始。

- <https://gdg.community.dev/events/details/google-gdg-taichung-presents-devfest-taichung-2026/>

## 2. 關於 Ko Ko（00:10–00:40）

大家好，我是柯克，經營「大魔術熊貓工程師」。我用機器學習做過植物基因研究，也常在技術社群分享生成式 AI 的開發經驗。

## 3. 我合著的六本書（00:40–01:00）

從第一本《駕馭 ChatGPT-4》到最新的《從 Prompt 到 Product》，這六本都是和其他作者一起寫的。上一本談 MCP，這次就拿報帳工具來看，模型提出查詢之後，誰有權決定要不要執行。

- <https://www.tenlong.com.tw/products/9786263335189>
- <https://www.tenlong.com.tw/products/9786263338203>
- <https://www.tenlong.com.tw/products/9786263339729>
- <https://www.tenlong.com.tw/products/9786264141871>
- <https://www.tenlong.com.tw/products/9786264142922>
- <https://www.tenlong.com.tw/products/9786264146371>

## 4. Alice 登入後，可以查哪一張單？（01:00–02:30）

把左右兩個單號念出來，請大家記住登入者是 Alice。程式用固定的測試身分代表她。待會兒兩次提問只有單號不同，工具與 Alice 的權限完全相同。

- [src/devfest_security/expense_smoke.py](../src/devfest_security/expense_smoke.py)
- [src/devfest_security/policy.py](../src/devfest_security/policy.py)

## 5. 第一幕　Alice 查自己的報帳（02:30–05:00）

執行 ./scripts/model-project.sh smoke-vertex，讓台下看一輪完整往返。兩次彩排送出的提示都明確要求使用 get_expense，程式也只提供這個唯讀工具。模型先提出工具與參數，本機應用程式核對 Alice 的權限，MCP 查單，再把結果交回 Hydrogen。若連線不順，說明是回放後，執行 python3 scripts/talk-replay.py alice。

- [examples/hydrogen-stage.json](../examples/hydrogen-stage.json)
- [src/devfest_security/expense_smoke.py](../src/devfest_security/expense_smoke.py)

## 6. 金額 120，怎麼知道真的查過？（05:00–06:30）

指給觀眾看這次執行的 run_id。MCP 留下一張收據，能對回 Alice、get_expense 和單號。比對的是報帳資料查詢前後的雜湊，收據本身仍然會新增。模型把 120 說對了，還要有執行紀錄才算完成驗證。

- [examples/hydrogen-stage.json](../examples/hydrogen-stage.json)
- [src/devfest_security/expense_smoke.py](../src/devfest_security/expense_smoke.py)

## 7. 第二幕　Alice 改查 Bob 的報帳（06:30–08:00）

停一下，讓台下先猜誰會拒絕。執行 ./scripts/model-project.sh smoke-vertex --check-authorization。指著輸出的 blocked_by 和 arguments，接著翻頁。若連線不順，改用 python3 scripts/talk-replay.py bob，先告知這是同一模型的先前實測。

- [examples/hydrogen-stage.json](../examples/hydrogen-stage.json)
- [src/devfest_security/expense_smoke.py](../src/devfest_security/expense_smoke.py)

## 8. Bob 的單子，擋在哪一步？（08:00–10:00）

第一行是模型確實提出的呼叫。第二行是 LangGraph 在送出 tools/call 前呼叫應用程式的 authorize，判斷目前的使用者 Alice 有沒有權利讀這張單。第三行是本機讀回的結果。Agent 仍做過工具發現，因此「0 次」特指工具執行。這一幕沒有呼叫 Model Armor。

- [examples/hydrogen-stage.json](../examples/hydrogen-stage.json)
- [src/devfest_security/expense_smoke.py](../src/devfest_security/expense_smoke.py)

## 9. 同一個模型、同一個工具，換一張報帳單（10:00–11:30）

請觀眾橫著看「模型提出」和「MCP 工具執行」。模型在兩次請求都照提示提出查詢，差別出現在程式比對單據歸屬的那一步。接下來讓 Alice 回頭查自己的單，改看她讀不到的工具說明。

- [examples/hydrogen-stage.json](../examples/hydrogen-stage.json)

## 10. 第三幕　Alice 查自己的單，工具說明卻變了（11:30–13:00）

現在切到雲端實測回放。仍是 Alice 想查自己的 EXP-ALICE。這次看的是伺服器透過 tools/list 送回的工具說明。對照雲端的正常版和變更版，網址、版本和工具名稱相同。這是另一組實驗環境，前兩幕使用的 Hydrogen 沒有參與。

- [examples/live-cloud-results.json](../examples/live-cloud-results.json)

## 11. Model Armor 在工具說明裡偵測到風險（13:00–15:00）

執行 python3 scripts/talk-replay.py armor。指出 user_prompt 為 allowed，接著 tool_descriptions 為 blocked。應用程式看到掃描結果就停止。這案原先設定 Flash-Lite，實際模型推論是零。回放直接讀取當日紀錄，沒有重新送出掃描。

- [examples/live-cloud-results.json](../examples/live-cloud-results.json)
- <https://docs.cloud.google.com/model-armor/sanitize-prompts-responses>

## 12. 六個雲端案例，哪些有執行工具？（15:00–16:30）

先看前兩列。正常案與改過工具說明但沒有額外防護的那案，Flash-Lite 都只查了 Alice 的單。第三列開啟描述掃描後，在第一次模型推論前就停了。第四列是另一個獨立的 Manifest 比對案例。第五列的批准請求由測試程式送出。最後一列才是主管 Bob 合法批准。

- [examples/live-cloud-results.json](../examples/live-cloud-results.json)

## 13. 雲端的模型、掃描與工具怎麼接？（16:30–17:30）

回放中的請求經過這些服務。LangGraph 送內容給 Model Armor、向 Gemini 請求推論，再用服務帳戶呼叫私有 Cloud Run。MCP 將收據和帳本寫進 Cloud Storage。回看第二幕，應用程式在發送工具呼叫前就能拒絕。

- [examples/live-cloud-results.json](../examples/live-cloud-results.json)

## 14. Google 代管的 MCP 會掃工具清單嗎？（17:30–18:30）

就報帳範例用到的 MCP 方法來看，原生整合在支援的服務及設定下可掃 tools/call 請求和回覆，tools/list 工具清單不在原生掃描範圍。第三幕是我們在應用程式裡主動送掃描。其他受支援內容見文件。

- <https://docs.cloud.google.com/model-armor/model-armor-mcp-google-cloud-integration?hl=en>

## 15. 先掃工具定義，再交給模型（18:30–19:30）

這裡是簡化的防護程式。discover 拿到工具定義，程式把名稱、描述及 schema 送去掃描。第三幕在 scan 這行已經停止，後面的 bind_tools 沒有執行。

- <https://docs.cloud.google.com/model-armor/overview>
- <https://docs.cloud.google.com/model-armor/model-armor-mcp-google-cloud-integration?hl=en>

## 16. Model Armor 掃描的五個位置（19:30–21:00）

沿著淺藍色區塊走一遍。這是啟用掃描且模型要求呼叫工具的完整路徑。第三幕停在第二格「掃工具定義」。正常查詢會繼續，應用程式驗證參數與授權後才掃工具參數。若模型直接回答，就掃最終回覆。

## 17. 掃描出錯時，程式怎麼處理？（21:00–22:00）

程式同時檢查整體結果和個別 filter。HTTP 回應正常時，也要看 filter 有沒有把掃描做完。

## 18. Manifest Pinning 怎麼比對工具清單？（22:00–23:30）

先由人確認基準。實驗把 endpoint、serverInfo 和工具定義一起整理成固定格式，再算 SHA-256。新版清單對不上就停，請人看差異。Agent 在呼叫工具前會再檢查一次。兩次檢查之間仍可能有時間差。

## 19. 誰負責擋下越權查詢？（23:30–25:00）

回頭看 Bob 的單據，那次 Hydrogen 查詢被 Agent 的應用程式授權擋下，請求沒有送到 MCP。雲端案例還另外測過伺服器自行拒絕越權的固定批准請求。兩次拒絕發生在不同位置。

- [examples/hydrogen-stage.json](../examples/hydrogen-stage.json)
- [examples/live-cloud-results.json](../examples/live-cloud-results.json)
- [src/devfest_security/policy.py](../src/devfest_security/policy.py)

## 20. 單號格式正確，Alice 就能讀嗎？（25:00–26:00）

上半段是 expense_smoke.py 的呼叫處，下半段摘自 policy.py 的 authorize，為了投影調整了斷行。程式先前已查過工具、參數和租戶。EXP-BOB 是有效的單號，get_expense 也是允許的工具。固定登入者 Alice 是員工，單據卻屬於 Bob，在下方條件被拒絕。

- [src/devfest_security/expense_smoke.py](../src/devfest_security/expense_smoke.py)
- [src/devfest_security/policy.py](../src/devfest_security/policy.py)

## 21. 先驗服務身分，再查報帳權限（26:00–27:30）

上面是 Cloud Run 對服務呼叫者的檢查，要有符合 audience 的 ID token 和 Invoker 權限。下面是 MCP Server 以應用程式身分查 Alice 有沒有權批准。雲端紀錄裡可以對照這兩次初始化回應：403 與 200。Alice 與 Bob 在這個實驗是固定測試角色。

## 22. 把同一筆請求的紀錄找齊（27:30–29:00）

先用 run_id 串起這次執行。Cloud Logging 收的是 Cloud Run 上的 MCP 紀錄；在 Agent 就擋下的請求沒有到 Server。若有收據，再核對 receipt_id 和雜湊，直接從儲存讀回帳本。帳本和 receipt 寫在同一個物件更新裡。

## 23. 私有 MCP 從部署到清理（29:00–30:00）

雲端實測涵蓋建立資源、遠端查詢，以及從 GCS 讀回結果。結束後執行專案的 cleanup.sh，再以 verify-cleanup.sh 查殘留。今天講這段用存檔，無須現場部署。

- [examples/live-cloud-results.json](../examples/live-cloud-results.json)

## 24. Agent Runtime 遠端查詢的結果（30:00–31:00）

Runtime 本身有 event loop，async_query 直接 await LangGraph。架構裡的模型 key 來自 Secret Manager，連到 Cloud Run 則用 Runtime 身分。這個結果來自 Flash-Lite 的遠端查詢與 GCS 讀回。

## 25. 兩次 Hydrogen 彩排花了多少？（31:00–32:00）

按當次 Vertex AI 全球端點標準費率估算。Alice 成功查詢兩次推論，308 個輸入、158 個輸出 token。越權拒絕一次推論，139 個輸入、79 個輸出 token。合計 US$0.002448，輸出包含推理 token。這是推論估算，實付看帳單。Model Armor 雲端回放是另一次實驗。

- [examples/hydrogen-stage.json](../examples/hydrogen-stage.json)
- <https://cloud.google.com/model-garden/pricing>

## 26. 改完防護，正常的工作還能做嗎？（32:00–33:30）

以三個回歸案例收尾。工具清單變動時能在模型前停止，Alice 沒有批准權時會被拒絕，換成有權限的主管 Bob，正常的批准仍可完成。每個案例都讀回帳本核對結果。這裡談的是批准流程，前兩幕的 Hydrogen 只開放讀取。

## 27. Google Cloud 管哪一段？ 報帳系統管哪一段？（33:30–35:00，35:00–40:00 問答）

收尾可以直接說：「工具說明被動過，要在交給模型前查。Alice 能查誰的帳，要在工具執行前查。最後到底有沒有查到，就看執行紀錄。」停在這張開放問答，第 35 分鐘開始 Q&A。

- <https://docs.cloud.google.com/model-armor/overview>
- <https://docs.cloud.google.com/run/docs/authenticating/service-to-service>
- <https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime>
- <https://docs.cloud.google.com/run/docs/logging>
- <https://docs.cloud.google.com/storage/docs/consistency>

## 28. 同一句中文，開多語言偵測前後（附錄）

有一次中文查詢未開多語言偵測就被擋。用同樣的問題和門檻再跑，只改多語言設定，查詢通過了。這組結果只能說明這一句的變化。

- <https://docs.cloud.google.com/model-armor/sanitize-prompts-responses>

## 29. 文件與延伸閱讀（附錄）

來源在下面，讀完文件也可以回到 Git 專案的 docs 和 tests 對照。

- <https://docs.cloud.google.com/model-armor/overview>
- <https://docs.cloud.google.com/model-armor/model-armor-mcp-google-cloud-integration?hl=en>
- <https://cloud.google.com/security/products/model-armor>
- <https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing>
- <https://github.com/Ko-Ko-Kirk/2026-ai-security-microsoft-foundry>
- <https://gdg.community.dev/events/details/google-gdg-taichung-presents-devfest-taichung-2026/>
