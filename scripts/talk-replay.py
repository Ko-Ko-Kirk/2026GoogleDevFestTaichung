"""在終端機展示指定場景的實測存檔。只讀取隨專案附上的合成資料。"""

import argparse
import json
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def show_hydrogen(scene):
    recording = json.loads((EXAMPLES / "hydrogen-stage.json").read_text(encoding="utf-8"))
    run = recording["runs"][scene]
    print(f'彩排回放　{run["api"]} / {run["model"]}')
    print(f'使用者　{run["principal"]}')
    print(f'模型提出　{run["tool"]}({run["arguments"]["expense_id"]})')
    if "denial" in run:
        print(f'應用程式拒絕　{run["decision"]}')
        print(f'拒絕原因　{run["denial"]}')
    else:
        print(f'應用程式允許　{run["decision"]}')
        result = run["tool_result"]
        print(f'工具回傳　金額 {result["amount"]}，狀態 {result["status"]}')
    print(f'模型推論 {run["model_calls"]} 次　MCP 執行 {run["executed_tool_calls"]} 次'
          f'　收據 {run["receipt_count"]} 張')
    print(f'帳本變更 {len(run["changed_expenses"])} 筆　{run["readback"]}')
    print(f'run_id　{run["run_id"]}')


def show_armor():
    recording = json.loads((EXAMPLES / "live-cloud-results.json").read_text(encoding="utf-8"))
    run = next(case for case in recording["scenarios"] if case["scenario"] == "03-poisoned-armor")
    print("雲端實測回放　Model Armor")
    for event in run["events"]:
        if event["event"] == "armor_scan":
            print(f'掃描　{event["surface"]}　{event["decision"]}')
    print(f'預設模型　{run["model"]}　實際推論 {run["actual_model_calls"]} 次')
    print(f'收據 {run["receipt_count"]} 張　帳本變更 {len(run["changed_expenses"])} 筆'
          f'　{run["readback_source"]}')
    print(f'run_id　{run["run_id"]}')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene", choices=["alice", "bob", "armor"])
    scene = parser.parse_args().scene
    if scene == "armor":
        show_armor()
    else:
        show_hydrogen(scene)
