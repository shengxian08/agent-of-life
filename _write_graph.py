with open(r"backend/app/agents/graph.py", "w", encoding="utf-8") as f:
    f.write(""""""LangGraph Agent Graph v4.0"""""")
    f.write("""
from __future__ import annotations
import json

_graph_app = None

class HouseholdState(dict):
    pass

def get_graph_app():
    return None

async def run_graph(session_id, user_id, message, thread_id=None):
    return {"response": "test", "intents": ["general"]}
""")