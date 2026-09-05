from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from doc_agent.agent.prompts import FINAL_SYSTEM, PLAN_SYSTEM
from doc_agent.agent.state import AgentState
from doc_agent.config import get_settings
from doc_agent.llm.factory import get_chat_model
from doc_agent.tools.registry import get_tool_list, tools_by_name


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}


def plan_node(state: AgentState) -> dict[str, Any]:
    llm = get_chat_model()
    resp = llm.invoke(
        [
            SystemMessage(content=PLAN_SYSTEM),
            HumanMessage(content=state["user_goal"]),
        ]
    )
    data = _extract_json(str(resp.content))
    route = data.get("route") or "tools"
    if route not in {"tools", "direct"}:
        route = "tools"
    # Phase-1 safety: only allow direct for very short greetings.
    goal = (state.get("user_goal") or "").strip()
    greetings = {"你好", "您好", "hello", "hi", "谢谢", "thanks", "thank you"}
    if route == "direct" and goal.lower() not in greetings and len(goal) > 8:
        route = "tools"
    plan = data.get("plan") or ["检索相关文档", "基于证据作答"]
    if isinstance(plan, str):
        plan = [plan]
    return {
        "plan": [str(p) for p in plan][:4],
        "route": route,
        "status": "planned",
        "messages": [AIMessage(content=f"规划完成: route={route}; plan={plan}")],
    }


def route_node(state: AgentState) -> str:
    if state.get("route") == "direct":
        return "finalize"
    if state.get("iteration", 0) >= get_settings().max_tool_calls:
        return "finalize"
    return "act"


def act_node(state: AgentState) -> dict[str, Any]:
    llm = get_chat_model().bind_tools(get_tool_list())
    tool_map = tools_by_name()
    results = list(state.get("tool_results") or [])
    citations = list(state.get("citations") or [])
    messages: list[Any] = []

    # Always ground with a direct retrieval pass on the user goal (phase-1 reliability).
    if state.get("iteration", 0) == 0:
        try:
            baseline = tool_map["rag_search"].invoke(
                {"query": state["user_goal"], "top_k": get_settings().top_k}
            )
            results.append(
                {
                    "tool": "rag_search",
                    "args": {"query": state["user_goal"]},
                    "output": baseline,
                }
            )
            parsed = json.loads(str(baseline))
            if isinstance(parsed, list):
                citations.extend(parsed)
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "tool": "rag_search",
                    "args": {"query": state["user_goal"]},
                    "output": f"工具执行失败: {exc}",
                }
            )

    prompt = (
        f"用户目标: {state['user_goal']}\n"
        f"执行计划: {state.get('plan')}\n"
        f"已有检索片段数: {len(citations)}\n"
        f"已有工具结果条数: {len(results)}\n"
        "若证据已足够可不再调工具；若不足可再调用 rag_search / parse_document / list_documents。"
    )
    ai: AIMessage = llm.invoke(
        [
            SystemMessage(content="你是工具调用执行器，只通过工具获取私有文档证据。"),
            HumanMessage(content=prompt),
        ]
    )
    messages.append(ai)

    if not ai.tool_calls:
        return {
            "messages": messages,
            "tool_results": results,
            "citations": citations,
            "iteration": state.get("iteration", 0) + 1,
            "status": "acted",
        }

    for call in ai.tool_calls:
        name = call["name"]
        args = call.get("args") or {}
        tool = tool_map.get(name)
        try:
            output = tool.invoke(args) if tool else f"未知工具: {name}"
        except Exception as exc:  # noqa: BLE001
            output = f"工具执行失败: {exc}"
        results.append({"tool": name, "args": args, "output": output})
        messages.append(ToolMessage(content=str(output), tool_call_id=call["id"]))
        if name == "rag_search":
            try:
                parsed = json.loads(str(output))
                if isinstance(parsed, list):
                    citations.extend(parsed)
            except json.JSONDecodeError:
                pass

    return {
        "messages": messages,
        "tool_results": results,
        "citations": citations,
        "iteration": state.get("iteration", 0) + 1,
        "status": "acted",
    }


def should_continue(state: AgentState) -> str:
    settings = get_settings()
    if state.get("iteration", 0) >= settings.max_tool_calls:
        return "finalize"
    # if last AI wanted tools but we already executed, allow one more planning loop only when no citations
    if not state.get("citations") and state.get("iteration", 0) < 2:
        return "act"
    return "finalize"


def finalize_node(state: AgentState) -> dict[str, Any]:
    llm = get_chat_model()
    evidence = {
        "plan": state.get("plan"),
        "citations": (state.get("citations") or [])[:8],
        "tool_results_tail": (state.get("tool_results") or [])[-3:],
    }
    resp = llm.invoke(
        [
            SystemMessage(content=FINAL_SYSTEM),
            HumanMessage(
                content=(
                    f"用户目标:\n{state['user_goal']}\n\n"
                    f"证据JSON:\n{json.dumps(evidence, ensure_ascii=False)[:12000]}"
                )
            ),
        ]
    )
    answer = str(resp.content).strip()
    return {
        "final_answer": answer,
        "status": "done",
        "messages": [AIMessage(content=answer)],
    }
