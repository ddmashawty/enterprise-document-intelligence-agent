from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from doc_agent.agent import kaoyan_flow
from doc_agent.agent.guardrails import (
    citations_to_excel_rows,
    citations_to_markdown,
    detect_kaoyan_intent,
    filter_redundant_tool_calls,
    infer_export_filename,
    is_list_documents_spin,
    recent_tools,
    resolve_compare_doc_names,
    tool_call_count,
    wants_compare,
    wants_excel,
    wants_export)
from doc_agent.agent.prompts import FINAL_SYSTEM, PLAN_SYSTEM, REFLECT_SYSTEM
from doc_agent.agent.state import AgentState
from doc_agent.config import get_settings
from doc_agent.runtime_options import effective_max_tool_calls
from doc_agent.llm.factory import get_chat_model
from doc_agent.tools import kaoyan as kaoyan_tools
from doc_agent.tools.registry import get_tool_list, parse_export_payload, tools_by_name


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


def _run_tool(
    tool_map: dict[str, Any],
    name: str,
    args: dict[str, Any],
    results: list[dict[str, Any]],
    messages: list[Any],
    citations: list[dict[str, Any]],
    exports: list[dict[str, Any]],
    *,
    tool_call_id: str | None = None) -> None:
    tool = tool_map.get(name)
    try:
        output = tool.invoke(args) if tool else f"未知工具: {name}"
    except Exception as exc:  # noqa: BLE001
        output = f"工具执行失败: {exc}"
    results.append({"tool": name, "args": args, "output": output})
    # Only attach ToolMessage when paired with an LLM tool_call id.
    if tool_call_id:
        messages.append(ToolMessage(content=str(output), tool_call_id=tool_call_id))
    if name == "rag_search":
        try:
            parsed = json.loads(str(output))
            if isinstance(parsed, list):
                citations.extend(parsed)
        except json.JSONDecodeError:
            pass
    if name == "compare_docs":
        try:
            payload = json.loads(str(output))
            docs = payload.get("documents") if isinstance(payload, dict) else None
            if isinstance(docs, dict):
                for snippets in docs.values():
                    if isinstance(snippets, list):
                        citations.extend(snippets)
        except json.JSONDecodeError:
            pass
    citations.extend(kaoyan_tools.citations_from_output(name, output))
    export_meta = parse_export_payload(name, output)
    if export_meta:
        exports.append(export_meta)


def _force_export(
    state: AgentState,
    tool_map: dict[str, Any],
    results: list[dict[str, Any]],
    messages: list[Any],
    citations: list[dict[str, Any]],
    exports: list[dict[str, Any]]) -> None:
    if exports or not citations:
        return
    goal = state["user_goal"]
    filename = infer_export_filename(goal)
    title = filename.replace("_", " ")
    if wants_excel(goal):
        rows = citations_to_excel_rows(citations)
        # Prefer structured secrecy/retention rows when present in text
        _run_tool(
            tool_map,
            "export_excel",
            {
                "title": title,
                "rows_json": json.dumps(rows, ensure_ascii=False),
                "filename": filename,
            },
            results,
            messages,
            citations,
            exports)
    else:
        content = citations_to_markdown(goal, citations, title=title)
        _run_tool(
            tool_map,
            "export_markdown",
            {"title": title, "content": content, "filename": filename},
            results,
            messages,
            citations,
            exports)


def _force_compare(
    state: AgentState,
    tool_map: dict[str, Any],
    results: list[dict[str, Any]],
    messages: list[Any],
    citations: list[dict[str, Any]],
    exports: list[dict[str, Any]]) -> None:
    if tool_call_count(results, "compare_docs") > 0:
        return
    names = resolve_compare_doc_names(state["user_goal"])
    if len(names) < 2:
        return
    aspects = ""
    goal = state["user_goal"]
    if "保存" in goal or "期限" in goal:
        aspects = "保存期限,参数,条款"
    elif "参数" in goal:
        aspects = "参数,TopK,切片"
    _run_tool(
        tool_map,
        "compare_docs",
        {
            "query": goal,
            "doc_names": ",".join(names),
            "aspects": aspects,
            "top_k": 4,
        },
        results,
        messages,
        citations,
        exports)


def plan_node(state: AgentState) -> dict[str, Any]:
    intent = detect_kaoyan_intent(state.get("user_goal") or "")
    intent["available"] = bool(intent["is_kaoyan"]) and kaoyan_tools.kaoyan_available()
    if intent["available"]:
        plan = kaoyan_flow.plan_steps(intent)
        return {
            "plan": plan,
            "route": "tools",
            "intent": intent,
            "status": "planned",
            "messages": [AIMessage(content=f"规划完成(考研): kinds={intent['kinds']}; plan={plan}")],
        }
    llm = get_chat_model()
    history = state.get("session_context") or ""
    human = state["user_goal"]
    if history:
        human = f"近期会话摘要:\n{history}\n\n当前用户目标:\n{state['user_goal']}"
    resp = llm.invoke(
        [
            SystemMessage(content=PLAN_SYSTEM),
            HumanMessage(content=human),
        ]
    )
    data = _extract_json(str(resp.content))
    route = data.get("route") or "tools"
    if route not in {"tools", "direct"}:
        route = "tools"
    goal = (state.get("user_goal") or "").strip()
    greetings = {"你好", "您好", "hello", "hi", "谢谢", "thanks", "thank you"}
    if route == "direct" and goal.lower() not in greetings and len(goal) > 8:
        route = "tools"
    plan = data.get("plan") or ["检索相关文档", "基于证据作答"]
    if isinstance(plan, str):
        plan = [plan]
    # Ensure export/compare appear in plan when goal asks for them
    plan_l = [str(p) for p in plan][:4]
    if wants_export(goal) and not any("export" in p.lower() or "导出" in p for p in plan_l):
        plan_l = (plan_l + ["export_markdown 或 export_excel 落盘"])[:4]
    if wants_compare(goal) and not any("compare" in p.lower() or "对比" in p for p in plan_l):
        plan_l = (["compare_docs 多文档检索"] + plan_l)[:4]
    return {
        "plan": plan_l,
        "route": route,
        "intent": intent,
        "status": "planned",
        "messages": [AIMessage(content=f"规划完成: route={route}; plan={plan_l}")],
    }


def route_node(state: AgentState) -> str:
    if state.get("route") == "direct":
        return "finalize"
    if state.get("iteration", 0) >= effective_max_tool_calls():
        return "finalize"
    return "act"


def _kaoyan_act(state: AgentState) -> dict[str, Any]:
    tool_map = tools_by_name()
    results = list(state.get("tool_results") or [])
    citations = list(state.get("citations") or [])
    exports = list(state.get("exports") or [])
    messages: list[Any] = []
    iteration = state.get("iteration", 0)

    def run(name: str, args: dict[str, Any]) -> None:
        _run_tool(tool_map, name, args, results, messages, citations, exports)

    if iteration == 0:
        kaoyan_flow.bootstrap(dict(state), run)
        if state["intent"].get("export"):
            kaoyan_flow.export(dict(state), results, run)
    else:
        kaoyan_flow.continue_act(dict(state), results, exports, run)
    return {
        "messages": messages + [AIMessage(content=f"考研工具: {recent_tools(results, 8)}")],
        "tool_results": results,
        "citations": citations,
        "exports": exports,
        "iteration": iteration + 1,
        "should_retry": False,
        "status": "acted",
    }


def act_node(state: AgentState) -> dict[str, Any]:
    if kaoyan_flow.is_kaoyan(state):
        return _kaoyan_act(state)
    llm = get_chat_model().bind_tools(get_tool_list())
    tool_map = tools_by_name()
    results = list(state.get("tool_results") or [])
    citations = list(state.get("citations") or [])
    exports = list(state.get("exports") or [])
    messages: list[Any] = []
    iteration = state.get("iteration", 0)
    goal = state["user_goal"]
    hint = state.get("retry_hint") or ""

    # Deterministic bootstrap: search once, then compare/export when needed.
    if iteration == 0:
        _run_tool(
            tool_map,
            "rag_search",
            {"query": goal, "top_k": get_settings().top_k},
            results,
            messages,
            citations,
            exports)
        if wants_compare(goal):
            _force_compare(state, tool_map, results, messages, citations, exports)

    # Export-only path on retry / late iterations (do not ask LLM to list docs again).
    force_export_now = (
        wants_export(goal)
        and not exports
        and bool(citations)
        and (
            iteration >= 1
            or "export_" in hint
            or "导出" in hint
            or is_list_documents_spin(results)
        )
    )
    if force_export_now:
        _force_export(state, tool_map, results, messages, citations, exports)
        return {
            "messages": messages + [AIMessage(content="已强制执行导出工具。")],
            "tool_results": results,
            "citations": citations,
            "exports": exports,
            "iteration": iteration + 1,
            "should_retry": False,
            "status": "acted",
        }

    # If compare still missing evidence from 2+ docs, force once more.
    if wants_compare(goal) and tool_call_count(results, "compare_docs") == 0 and iteration >= 1:
        _force_compare(state, tool_map, results, messages, citations, exports)

    prompt = (
        f"用户目标: {goal}\n"
        f"执行计划: {state.get('plan')}\n"
        f"已有检索片段数: {len(citations)}\n"
        f"已有导出数: {len(exports)}\n"
        f"已调用 list_documents 次数: {tool_call_count(results, 'list_documents')}\n"
        f"近期工具: {recent_tools(results)}\n"
        f"反思提示: {hint or '无'}\n"
        "硬性规则：\n"
        "1) list_documents 全任务最多调用 1 次；已调用过则禁止再调。\n"
        "2) 对比任务优先/仅用 compare_docs（传入确切 doc_name）。\n"
        "3) 需要导出且已有证据时，必须调用 export_markdown 或 export_excel，禁止继续列举文档。\n"
        "4) 证据已够且无需导出时，不要调用任何工具。\n"
    )
    ai: AIMessage = llm.invoke(
        [
            SystemMessage(
                content=(
                    "你是工具调用执行器。禁止无效重复调用。"
                    "有证据需导出时优先 export_*；对比用 compare_docs。"
                )
            ),
            HumanMessage(content=prompt),
        ]
    )
    messages.append(ai)

    raw_calls = list(ai.tool_calls or [])
    calls = filter_redundant_tool_calls(raw_calls, results)

    if not calls:
        # Last chance: still need export
        if wants_export(goal) and not exports and citations:
            _force_export(state, tool_map, results, messages, citations, exports)
        return {
            "messages": messages,
            "tool_results": results,
            "citations": citations,
            "exports": exports,
            "iteration": iteration + 1,
            "should_retry": False,
            "status": "acted",
        }

    for call in calls:
        name = call["name"]
        args = call.get("args") or {}
        # Soft-block list_documents spam even if filter missed
        if name == "list_documents" and tool_call_count(results, "list_documents") >= 1:
            continue
        _run_tool(
            tool_map,
            name,
            args,
            results,
            messages,
            citations,
            exports,
            tool_call_id=call.get("id"))

    # After LLM tools, guarantee export if requested and still missing.
    if wants_export(goal) and not exports and citations:
        _force_export(state, tool_map, results, messages, citations, exports)

    return {
        "messages": messages,
        "tool_results": results,
        "citations": citations,
        "exports": exports,
        "iteration": iteration + 1,
        "should_retry": False,
        "status": "acted",
    }


def reflect_node(state: AgentState) -> dict[str, Any]:
    iteration = state.get("iteration", 0)
    goal = (state.get("user_goal") or "").strip()
    greetings = {"你好", "您好", "hello", "hi", "谢谢", "thanks", "thank you"}
    if goal.lower() in greetings:
        return {
            "reflection": "寒暄无需更多工具。",
            "should_retry": False,
            "retry_hint": "",
            "status": "reflected",
        }

    if iteration >= effective_max_tool_calls():
        return {
            "reflection": "已达工具调用上限，停止重试。",
            "should_retry": False,
            "retry_hint": "",
            "status": "reflected",
        }

    if kaoyan_flow.is_kaoyan(state):
        return kaoyan_flow.reflect(dict(state))

    citations = state.get("citations") or []
    exports = state.get("exports") or []
    results = state.get("tool_results") or []
    need_export = wants_export(goal) and not exports
    need_compare = wants_compare(goal) and tool_call_count(results, "compare_docs") == 0

    if not citations and state.get("route") != "direct":
        return {
            "reflection": "尚无检索证据，建议换关键词 rag_search（不要反复 list_documents）。",
            "should_retry": True,
            "retry_hint": "调用 rag_search；禁止再次 list_documents。",
            "status": "reflected",
        }

    if need_export and citations:
        return {
            "reflection": "用户要求导出但尚未生成文件，下一轮只允许 export_*。",
            "should_retry": True,
            "retry_hint": "只调用 export_markdown 或 export_excel；禁止 list_documents。",
            "status": "reflected",
        }

    if need_compare:
        return {
            "reflection": "对比任务尚未调用 compare_docs。",
            "should_retry": True,
            "retry_hint": "调用 compare_docs，传入两个确切 doc_name；禁止反复 list_documents。",
            "status": "reflected",
        }

    if is_list_documents_spin(results):
        return {
            "reflection": "检测到 list_documents 空转，停止重试。",
            "should_retry": False,
            "retry_hint": "",
            "status": "reflected",
        }

    # Evidence present and no mandatory export/compare left → finish (skip extra LLM reflect cost/noise)
    if citations and not need_export and not need_compare:
        return {
            "reflection": "已有检索证据且无强制导出/对比缺口，结束工具循环。",
            "should_retry": False,
            "retry_hint": "",
            "status": "reflected",
        }

    llm = get_chat_model()
    payload = {
        "goal": goal,
        "plan": state.get("plan"),
        "citation_count": len(citations),
        "export_count": len(exports),
        "iteration": iteration,
        "tool_names": recent_tools(results, 8),
        "citation_preview": [
            {
                "doc": c.get("doc_name"),
                "page": c.get("page"),
                "text": (c.get("text") or "")[:120],
            }
            for c in citations[:4]
        ],
    }
    resp = llm.invoke(
        [
            SystemMessage(content=REFLECT_SYSTEM),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)[:8000]),
        ]
    )
    data = _extract_json(str(resp.content))
    should_retry = bool(data.get("should_retry"))
    hint = str(data.get("retry_hint") or "")
    if "list_documents" in hint and tool_call_count(results, "list_documents") >= 1:
        hint = hint.replace("list_documents", "rag_search")
    if should_retry and citations and iteration >= 2 and not need_export:
        if data.get("sufficient"):
            should_retry = False
    return {
        "reflection": str(data.get("issues") or hint or resp.content)[:500],
        "should_retry": should_retry,
        "retry_hint": hint,
        "status": "reflected",
        "messages": [AIMessage(content=f"反思: {data}")],
    }


def after_reflect(state: AgentState) -> str:
    if state.get("should_retry") and state.get("iteration", 0) < effective_max_tool_calls():
        return "act"
    return "finalize"


def finalize_node(state: AgentState) -> dict[str, Any]:
    llm = get_chat_model()
    if kaoyan_flow.is_kaoyan(state):
        answer, validation = kaoyan_flow.finalize(dict(state), llm)
        exports = state.get("exports") or []
        paths = ", ".join(str(e.get("path")) for e in exports if e.get("path"))
        if paths and "data/exports" not in answer:
            answer = answer.rstrip() + f"\n\n**导出文件：** {paths}"
        return {
            "final_answer": answer,
            "facts": {**(state.get("facts") or {}), "validation": validation},
            "status": "done",
            "messages": [AIMessage(content=answer)],
        }
    evidence = {
        "plan": state.get("plan"),
        "citations": (state.get("citations") or [])[:8],
        "exports": state.get("exports") or [],
        "reflection": state.get("reflection") or "",
        "tool_results_tail": (state.get("tool_results") or [])[-4:],
        "session_context": state.get("session_context") or "",
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
    exports = state.get("exports") or []
    if exports and "data/exports" not in answer:
        paths = ", ".join(str(e.get("path")) for e in exports if e.get("path"))
        if paths:
            answer = answer.rstrip() + f"\n\n**导出文件：** {paths}"
    return {
        "final_answer": answer,
        "status": "done",
        "messages": [AIMessage(content=answer)],
    }
