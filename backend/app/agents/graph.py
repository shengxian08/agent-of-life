"""
LangGraph Agent Graph v4.0 — StateGraph Orchestration Engine
Semantic routing + parallel agents + result fusion + checkpoint persistence
"""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator, Literal, TypedDict

from loguru import logger

from ..config import settings
from ..models.schemas import AgentRequest

_graph_app = None
_checkpointer_conn = None  # SQLite connection for cleanup


class HouseholdState(TypedDict):
    session_id: str
    user_id: str
    message: str
    intents: list[str]
    shopping_result: str
    meal_plan_result: str
    appliance_result: str
    maintenance_result: str
    final_response: str
    confidence: float
    error: str


# ================================================================
# Node implementations
# ================================================================

async def _node_classify_intent(state: HouseholdState) -> dict:
    """LLM semantic intent classification"""
    msg = state["message"]
    domain_keywords = {
        "shopping": ["购物","清单","买菜","采购","比价","价格","冰箱","库存","超市"],
        "meal_plan": ["菜谱","规划","吃什么","做法","怎么做","搭配","食材","菜"],
        "appliance": ["错峰","预约","家电","扫地","洗衣","洗碗","运行"],
        "maintenance": ["维保","保养","维修","坏了","修理","师傅","账单","缴费"],
    }
    matched = []
    for domain, keywords in domain_keywords.items():
        if any(k in msg for k in keywords):
            matched.append(domain)
    if matched:
        if len(matched) > 1 or any(k in msg for k in ["并","同时","顺便","还有","另外","以及"]):
            return {"intents": matched}
        return {"intents": matched}

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.openai_base_url,
        )
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{
                "role": "system",
                "content": (
                    "Classify user message to domains (can be multiple): "
                    "shopping, meal_plan, appliance, maintenance, general. "
                    "Return JSON array only, e.g. [\"meal_plan\"] or [\"meal_plan\",\"shopping\"]."
                ),
            }, {
                "role": "user",
                "content": msg,
            }],
            temperature=0,
            max_tokens=50,
            response_format={"type": "json_object"},  # Structured output
        )
        text = (resp.choices[0].message.content or '{"intents":["general"]}').strip()
        data = json.loads(text)
        intents = data.get("intents", data if isinstance(data, list) else ["general"])
        if isinstance(intents, list) and intents:
            return {"intents": intents}
    except Exception as e:
        logger.warning(f"Graph classify failed: {e}")

    return {"intents": ["general"]}


async def _run_domain_agent(domain: str, state: HouseholdState) -> dict:
    """Execute a single domain agent"""
    from .crew import get_household_crew
    crew = get_household_crew()
    request = AgentRequest(
        session_id=state["session_id"],
        user_id=state["user_id"],
        message=state["message"],
        intent=domain,
    )
    try:
        if domain == "general":
            resp = await crew.orchestrator.run(request)
        else:
            agents = {
                "shopping": crew.shopping,
                "meal_plan": crew.meal,
                "appliance": crew.appliance,
                "maintenance": crew.maintenance,
            }
            agent = agents.get(domain)
            if not agent:
                return {f"{domain}_result": f"Unknown domain: {domain}"}
            resp = await agent.run(request)
        return {f"{domain}_result": resp.response, "confidence": resp.confidence}
    except Exception as e:
        logger.error(f"Domain agent {domain} failed: {e}")
        return {f"{domain}_result": f"[{domain} error]", "error": str(e)}


async def _node_shopping_agent(state: HouseholdState) -> dict:
    return await _run_domain_agent("shopping", state)

async def _node_meal_agent(state: HouseholdState) -> dict:
    return await _run_domain_agent("meal_plan", state)

async def _node_appliance_agent(state: HouseholdState) -> dict:
    return await _run_domain_agent("appliance", state)

async def _node_maintenance_agent(state: HouseholdState) -> dict:
    return await _run_domain_agent("maintenance", state)

async def _node_general_agent(state: HouseholdState) -> dict:
    return await _run_domain_agent("general", state)


async def _node_merge_results(state: HouseholdState) -> dict:
    """Merge multiple agent results via LLM"""
    results = {}
    for key in ["shopping_result","meal_plan_result","appliance_result","maintenance_result"]:
        val = state.get(key, "")
        if val:
            results[key.replace("_result","")] = val

    if not results:
        return {
            "final_response": state.get("error", "Unable to process request"),
            "confidence": 0.5,
        }

    if len(results) == 1:
        return {
            "final_response": list(results.values())[0],
            "confidence": state.get("confidence", 0.9),
        }

    parts = "\n\n---\n\n".join(
        f"[{d}] {t}" for d, t in results.items()
    )

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.openai_base_url,
        )
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{
                "role": "system",
                "content": (
                    "Merge multiple agent replies into one natural conversational Chinese response. "
                    "Use emoji as section separators. No markdown."
                ),
            }, {
                "role": "user",
                "content": f"User: {state['message']}\n\nAgent replies:\n{parts[:3000]}",
            }],
            temperature=0.4,
            max_tokens=1500,
        )
        return {"final_response": resp.choices[0].message.content or parts, "confidence": 0.9}
    except Exception as e:
        logger.warning(f"Merge LLM failed: {e}")
        return {"final_response": parts, "confidence": 0.8}


def _route_by_intents(state: HouseholdState) -> Literal[
    "shopping", "meal_plan", "appliance", "maintenance", "general", "multi"
]:
    """Conditional edge router"""
    intents = state.get("intents", ["general"])
    if not intents:
        return "general"
    if len(intents) == 1:
        intent = intents[0]
        if intent in ("shopping", "meal_plan", "appliance", "maintenance", "general"):
            return intent
    return "multi"


# ================================================================
# Graph construction
# ================================================================

def build_household_graph(enable_checkpointer: bool = True):
    """Build the LangGraph StateGraph for household agent orchestration

    Graph topology:
        classify --> [shopping|meal_plan|appliance|maintenance|general] --> merge --> END
    """
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        logger.error("langgraph not installed, graph unavailable")
        return None

    workflow = StateGraph(HouseholdState)

    # Add all nodes
    workflow.add_node("classify", _node_classify_intent)
    workflow.add_node("shopping", _node_shopping_agent)
    workflow.add_node("meal_plan", _node_meal_agent)
    workflow.add_node("appliance", _node_appliance_agent)
    workflow.add_node("maintenance", _node_maintenance_agent)
    workflow.add_node("general", _node_general_agent)
    workflow.add_node("merge", _node_merge_results)

    # Entry point
    workflow.set_entry_point("classify")

    # Conditional routing
    route_map = {
        "shopping": "shopping",
        "meal_plan": "meal_plan",
        "appliance": "appliance",
        "maintenance": "maintenance",
        "general": "general",
        "multi": "merge",
    }
    workflow.add_conditional_edges("classify", _route_by_intents, route_map)

    # All agents converge to merge
    for node in ["shopping", "meal_plan", "appliance", "maintenance", "general"]:
        workflow.add_edge(node, "merge")

    # Merge to END
    workflow.add_edge("merge", END)

    # Optional SQLite checkpointer
    checkpointer = None
    if enable_checkpointer:
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            import sqlite3
            global _checkpointer_conn
            db_path = settings.checkpoint_db_path
            settings.checkpoint_dir  # Ensure dir exists
            _checkpointer_conn = sqlite3.connect(db_path, check_same_thread=False)
            checkpointer = SqliteSaver(_checkpointer_conn)
            logger.info(f"LangGraph checkpointer enabled: {db_path}")
        except ImportError:
            logger.debug("langgraph-checkpoint-sqlite not installed")
        except Exception as e:
            logger.warning(f"Checkpointer init failed: {e}")

    return workflow.compile(checkpointer=checkpointer)


def get_graph_app():
    """Get or create the LangGraph app singleton"""
    global _graph_app
    if _graph_app is None:
        _graph_app = build_household_graph()
    return _graph_app


# ================================================================
# Public API
# ================================================================

async def run_graph(
    session_id: str,
    user_id: str,
    message: str,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Run a conversation through the LangGraph

    Args:
        session_id: Session identifier
        user_id: User identifier
        message: User input message
        thread_id: LangGraph thread ID for checkpoint recovery

    Returns:
        {"response": str, "intents": list[str], "confidence": float}
    """
    app = get_graph_app()
    if app is None:
        return {
            "response": "Agent graph unavailable - langgraph not installed",
            "intents": ["general"],
            "confidence": 0.0,
        }

    initial_state: HouseholdState = {
        "session_id": session_id,
        "user_id": user_id,
        "message": message,
        "intents": [],
        "shopping_result": "",
        "meal_plan_result": "",
        "appliance_result": "",
        "maintenance_result": "",
        "final_response": "",
        "confidence": 0.0,
        "error": "",
    }

    config = {}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    try:
        final_state = await app.ainvoke(initial_state, config)
        return {
            "response": final_state.get("final_response", ""),
            "intents": final_state.get("intents", []),
            "confidence": final_state.get("confidence", 0.0),
        }
    except Exception as e:
        logger.error(f"Graph execution failed: {e}")
        return {
            "response": f"System error: {str(e)}",
            "intents": ["general"],
            "confidence": 0.0,
        }


async def run_graph_stream(
    session_id: str,
    user_id: str,
    message: str,
    thread_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream conversation through the LangGraph"""
    app = get_graph_app()
    if app is None:
        yield "Agent graph unavailable."
        return

    initial_state: HouseholdState = {
        "session_id": session_id,
        "user_id": user_id,
        "message": message,
        "intents": [],
        "shopping_result": "",
        "meal_plan_result": "",
        "appliance_result": "",
        "maintenance_result": "",
        "final_response": "",
        "confidence": 0.0,
        "error": "",
    }

    config = {}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    try:
        async for event in app.astream(initial_state, config):
            for node_name, node_output in event.items():
                if node_name == "merge" and "final_response" in node_output:
                    yield node_output["final_response"]
    except Exception as e:
        logger.error(f"Graph stream failed: {e}")
        yield f"\n[Stream error: {str(e)}]"


def close_graph():
    """Cleanup LangGraph resources (SQLite checkpointer connection)"""
    global _graph_app, _checkpointer_conn
    _graph_app = None
    if _checkpointer_conn:
        try:
            _checkpointer_conn.close()
            logger.info("LangGraph checkpointer connection closed")
        except Exception as e:
            logger.warning(f"Failed to close checkpointer connection: {e}")
        _checkpointer_conn = None
