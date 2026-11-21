# 安全研究範圍

本實驗只使用固定的合成報帳與隔離的本機服務。不要以真實資料、公司環境或未取得授權的 MCP server 執行攻擊案例。

`LAB_ALLOW_SYNTHETIC_UNSAFE=true` 僅用於本機 replay。正式服務不能由模型、tool arguments 或任意 caller 關閉授權。

測試資料與 fixture 不是模型攻擊成功率，也不是 Model Armor 的雲端結果。公開問題時請移除 credentials、token、帳戶 ID、私有 URL 與原始企業日誌。若日後公開 repository，再由維護者設定私人漏洞回報管道。

本專案不是 production security gateway。端點 pin 無法證明 server 程式完整性；receipt hash 沒有數位簽章；合成 persona 也不等於正式 end-user identity。
