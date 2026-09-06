from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_goal: str
    session_id: str
    task_id: str
    plan: list[str]
    route: Literal["tools", "direct", ""]
    tool_results: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    exports: list[dict[str, Any]]
    reflection: str
    should_retry: bool
    retry_hint: str
    session_context: str
    iteration: int
    final_answer: str
    status: str
    error: str
