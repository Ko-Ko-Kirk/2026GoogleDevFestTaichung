# 本機開發

```bash
./scripts/setup.sh
./scripts/check.sh
./scripts/demo.sh
```

Python 3.12、uv、macOS／Linux；Windows 使用 WSL。所有相依版本由 `uv.lock` 固定。

修改安全控制時，測試必須同時涵蓋合法操作、拒絕路徑與持久化結果。新增真實模型案例要記錄 provider、model、manifest hash、實際 tool call、授權結果與 readback；不要把固定 fixture 標成 LLM 結果。

目前為零支出版本。CI 與預設 Demo 不連雲端、不取得憑證，也不建立資源。不要為通過測試而改成發送真實付費請求。測試內替換 execution guard 只允許模擬網路邊界。

程式採 MIT 授權；第三方依賴維持原授權。投影片母片、講者照片與品牌素材不屬於此程式碼授權範圍。

目前使用私人 GitHub 儲存庫協作。對外公開的時間由講者決定。
