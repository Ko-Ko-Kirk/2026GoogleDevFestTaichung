"""Render recorded offline or live evidence as a standalone, network-free report."""

import argparse
import html
import json
from pathlib import Path


def render(directory: Path) -> Path:
    summaries = json.loads((directory / "summary.json").read_text())
    rows = []
    for row in summaries:
        name = row["scenario"]
        # Filenames come from the fixed rehearsal matrix, not tool/model text.
        if name not in {"01-read", "02-unsafe-policy-replay", "03-manifest-block",
                        "04-caller-policy-block", "05-server-policy-block", "06-manager-approved",
                        "01-normal", "02-poisoned-unprotected", "03-poisoned-armor",
                        "04-poisoned-pinned", "05-server-policy-replay", "06-authorized-manager"}:
            raise ValueError("Unknown rehearsal scenario")
        evidence = json.loads((directory / f"{name}.json").read_text())
        fields = [name, evidence["status"], evidence["model_source"] + f" ({evidence.get('model_calls', 0)} calls)", str(row["receipt_count"]),
                  ", ".join(f"{key}: {value['status']}" for key, value in row["changed_expenses"].items()) or "無", evidence.get("reason", "—")]
        cells = "".join(f"<td>{html.escape(value)}</td>" for value in fields)
        rows.append(f'<tr>{cells}<td><a href="{name}.json">Agent</a> · '
                    f'<a href="{name}.readback.json">Readback</a></td></tr>')
    document = '''<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>DevFest｜MCP 安全執行證據</title><style>
body{font:18px/1.7 'Microsoft JhengHei',sans-serif;background:#f6f8fb;color:#172437;margin:4vw}
h1{font-size:36px}strong{color:#1252a0}table{border-collapse:collapse;background:white;width:100%}
td,th{padding:14px;text-align:left;border-bottom:1px solid #ccd4df;vertical-align:top}
th{background:#172437;color:white}a{color:#1252a0}td:nth-child(4){min-width:90px}
</style><h1>MCP 安全：先看持久化結果</h1>
<p><strong>每列列出模型來源與實際呼叫次數；以 Agent JSON 與獨立帳本讀回驗證。</strong><br>
deterministic-policy-fixture 是指定工具輸入；live-gemini-developer-api 是 Gemini 路徑。0 calls 表示在推論前停止。掃描結果見各案 events，不以模型回覆代替執行證據。</p>
<table><thead><tr><th>情境</th><th>Agent 狀態</th><th>模型路徑／呼叫次數</th><th>Receipt</th><th>帳本變更</th>
<th>原因</th><th>原始證據</th></tr></thead><tbody>''' + "".join(rows) + '''</tbody></table>
<p>來源：本次 summary.json、Agent JSON 與獨立 readback。Receipt hash 檢查一致性，沒有數位簽章。</p>
</html>'''
    path = directory / "report.html"
    path.write_text(document)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    print(render(parser.parse_args().directory).resolve())


if __name__ == "__main__":
    main()
