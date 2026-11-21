"""Read Alice's synthetic expense through the real loopback MCP server."""

import sys
from asyncio import sleep

from google.genai.errors import ServerError
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from devfest_security.common import Blocked, canonical, digest
from devfest_security.evidence import readback, verify_evidence
from devfest_security.mcp_client import connect, discover
from devfest_security.policy import authorize
from devfest_security.server import DEFAULT_CONFIG, tools_for


class ExpenseState(MessagesState):
    denial: str


async def run_expense_lookup(
    chat, endpoint: str, root: str, run_id: str, *, vertex: bool = False,
    check_authorization: bool = False,
) -> dict:
    async with connect(endpoint, run_id) as (session, server):
        baseline = await discover(session, endpoint, server)
    trusted_tool = tools_for(DEFAULT_CONFIG)[0].model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    if (server.get("name") != "panda-expense-lab" or server.get("version") != "1.0.0"
            or baseline["tools"] != [trusted_tool]):
        raise Blocked("本機 MCP 的身分或唯讀工具定義與程式預期不符。")
    tools = [{
        "name": trusted_tool["name"],
        "description": trusted_tool["description"],
        "parameters": {field: trusted_tool["inputSchema"][field]
                       for field in ("type", "properties", "required")},
    }]
    manifest_hash = digest(baseline)
    tool_result = None
    model_attempts = 0
    expense_id = "EXP-BOB" if check_authorization else "EXP-ALICE"

    async def ask_model(messages, *, tool_choice="auto"):
        nonlocal model_attempts
        bound = chat.bind_tools(tools, tool_choice=tool_choice)
        model_attempts += 1
        try:
            return await bound.ainvoke(messages, timeout=20)
        except ServerError as error:
            if vertex or error.code != 503:
                raise
        print("Hydrogen 暫時無法回應，稍後重試這一輪推論。", file=sys.stderr, flush=True)
        await sleep(3)
        model_attempts += 1
        return await bound.ainvoke(messages, timeout=20)

    async def request_expense(state: ExpenseState):
        answer = await ask_model(state["messages"])
        return {"messages": [answer]}

    async def read_expense(state: ExpenseState):
        nonlocal tool_result
        calls = state["messages"][-1].tool_calls
        if (len(calls) != 1 or calls[0]["name"] != "get_expense"
                or calls[0]["args"] != {"expense_id": expense_id} or not calls[0].get("id")):
            raise Blocked(f"模型必須且只能要求查詢 {expense_id}。")
        call = calls[0]
        try:
            authorize("alice", call["name"], call["args"])
        except Blocked as error:
            if not check_authorization:
                raise
            return {"denial": str(error)}
        if check_authorization:
            raise Blocked("測試失敗：Alice 的權限檢查未拒絕這筆查詢。")
        async with connect(endpoint, run_id) as (session, current_server):
            current = await discover(session, endpoint, current_server)
            if digest(current) == manifest_hash:
                tool_result = await session.call_tool(call["name"], call["args"])
        if tool_result is None:
            raise Blocked("工具定義有差異，本次查詢已停止。")
        if tool_result.is_error or not tool_result.structured_content:
            raise Blocked("本機 MCP 未回傳可核對的報帳結果。")
        return {"messages": [ToolMessage(
            content=canonical(tool_result.structured_content["data"]),
            tool_call_id=call["id"],
            name=call["name"],
        )]}

    async def summarize_expense(state: ExpenseState):
        answer = await ask_model(state["messages"], tool_choice="none")
        return {"messages": [answer]}

    graph = StateGraph(ExpenseState)
    graph.add_node("request_expense", request_expense)
    graph.add_node("read_expense", read_expense)
    graph.add_node("summarize_expense", summarize_expense)
    graph.add_edge(START, "request_expense")
    graph.add_edge("request_expense", "read_expense")
    graph.add_conditional_edges("read_expense", lambda state: END if state.get("denial") else "summarize_expense")
    graph.add_edge("summarize_expense", END)
    prompt = HumanMessage(f"請用 get_expense 查詢 {expense_id} 的金額和狀態，金額用阿拉伯數字。")
    state = await graph.compile().ainvoke({"messages": [prompt]})
    messages = state["messages"]
    usage = [message.usage_metadata for message in messages if isinstance(message, AIMessage)]
    persisted = readback(root, run_id)
    if state.get("denial"):
        if persisted["exists"] or persisted["operations"]:
            raise Blocked("授權遭拒後出現工具執行紀錄。")
        return {
            "run_id": run_id, "status": "blocked", "blocked_by": "application_authorization",
            "tool": "get_expense", "arguments": {"expense_id": expense_id},
            "denial": state["denial"], "tool_calls": 0, "receipt_count": 0,
            "readback": persisted["source"], "changed_expenses": {},
            "model_attempts": model_attempts, "model_usage": usage,
        }
    answer = messages[-1]
    value = tool_result.structured_content
    checked = verify_evidence({
        "run_id": run_id, "model_source": "live-vertex-ai" if vertex else "live-gemini-developer-api",
        "principal": "alice", "status": "completed",
        "tool_results": [tool_result.model_dump(mode="json", by_alias=True, exclude_none=True)],
    }, persisted)
    if (checked["receipt_count"] != 1 or checked["changed_expenses"]
            or value["receipt"]["before_sha256"] != value["receipt"]["after_sha256"]):
        raise Blocked("帳本讀回結果與預期不符。")
    if (answer.tool_calls or str(value["data"]["amount"]) not in answer.text
            or not any(status in answer.text.lower() for status in ("pending", "待審核", "待審批", "待審"))):
        raise Blocked("模型回答未確認工具回傳的金額和待審核狀態。")
    return {
        "run_id": run_id, "status": "completed", "tool": "get_expense", "tool_result": value["data"],
        "receipt": value["receipt"], "readback": checked["readback_source"],
        "changed_expenses": checked["changed_expenses"], "answer": answer.text,
        "model_attempts": model_attempts,
        "model_usage": usage,
    }
