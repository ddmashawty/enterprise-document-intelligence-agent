from __future__ import annotations

from functools import lru_cache
from typing import Any
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from doc_agent.agent.nodes import act_node, finalize_node, plan_node, route_node, should_continue
from doc_agent.agent.state import AgentState


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("plan", plan_node)
    g.add_node("act", act_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", route_node, {"act": "act", "finalize": "finalize"})
    g.add_conditional_edges("act", should_continue, {"act": "act", "finalize": "finalize"})
    g.add_edge("finalize", END)
    return g.compile()


@lru_cache
def get_graph():
    return build_graph()


def run_agent(message: str, session_id: str | None = None) -> dict[str, Any]:
    sid = session_id or str(uuid4())
    graph = get_graph()
    initial: AgentState = {
        "messages": [HumanMessage(content=message)],
        "user_goal": message,
        "session_id": sid,
        "plan": [],
        "route": "",
        "tool_results": [],
        "citations": [],
        "iteration": 0,
        "final_answer": "",
        "status": "started",
        "error": "",
    }
    final = graph.invoke(initial)
    return {
        "session_id": sid,
        "answer": final.get("final_answer") or "",
        "plan": final.get("plan") or [],
        "citations": final.get("citations") or [],
        "trace": final.get("tool_results") or [],
        "status": final.get("status") or "",
        "iterations": final.get("iteration") or 0,
    }
