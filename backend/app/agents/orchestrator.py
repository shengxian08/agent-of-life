"""
主协调 Agent v5.0 — 6 Agent 语义路由 + 复合意图拆分 + 多 Agent 串并行调度
新增：安防监护Agent、家庭事务Agent
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger

from .base_agent import BaseAgent
from .shopping_agent import ShoppingAgent
from .meal_planner_agent import MealPlannerAgent
from .appliance_agent import ApplianceAgent
from .maintenance_agent import MaintenanceAgent
from .security_agent import SecurityAgent
from .household_agent import HouseholdAgent
from ..models.schemas import AgentRequest, AgentResponse
from ..config import settings

ORCHESTRATOR_PROMPT = """你是"家务事务全权代办"的总管家 v5.0。你可以调度6个专业管家：
- 🛒 购物管家：冰箱管理、清单生成、比价
- 🍳 膳食规划师：菜谱规划、食材搭配、做法指导
- ⚡ 家电调度员：错峰预约、状态查看、全屋设备协同控制
- 🔧 维保小卫士：检查保养、联系维修、账单管理
- 🛡️ 安防监护Agent：门禁管理、监控巡检、异常预警、老人儿童看护
- 📋 家庭事务Agent：日程管理、快递追踪、物业对接、访客预约

如果用户同时提出多个需求（如"规划菜谱并生成购物清单，顺便检查安防"），请协调多个管家依次完成。"""


class Orchestrator(BaseAgent):
    """语义路由器 + 6 Agent 编排"""

    # 领域定义（供 LLM 语义分类）— 6 domains
    DOMAIN_MAP = {
        "shopping": {
            "agent": "shopping",
            "keywords": ["购物", "清单", "买菜", "采购", "比价", "价格", "冰箱", "库存", "超市", "下单", "购买"],
            "description": "购物管家：冰箱库存、智能清单、商超比价",
        },
        "meal_plan": {
            "agent": "meal_plan",
            "keywords": ["菜谱", "规划", "一周", "吃什么", "做法", "怎么做", "能做什么", "搭配", "食材", "菜", "营养"],
            "description": "膳食规划师：一周菜谱规划、食材搭配、做法指导",
        },
        "appliance": {
            "agent": "appliance",
            "keywords": ["错峰", "预约", "家电", "扫地", "洗衣", "洗碗", "空调", "运行", "今晚", "省电", "设备"],
            "description": "家电调度员：错峰预约、状态查看、全屋设备协同控制",
        },
        "maintenance": {
            "agent": "maintenance",
            "keywords": ["维保", "保养", "维修", "坏了", "修理", "师傅", "账单", "缴费", "电费", "水费", "燃气"],
            "description": "维保小卫士：检查保养、联系维修、账单管理",
        },
        "security": {
            "agent": "security",
            "keywords": ["安防", "监控", "门禁", "摄像头", "门窗", "布防", "报警", "老人", "看护", "安全", "门口"],
            "description": "安防监护Agent：门禁管理、监控巡检、异常预警、老人儿童看护",
        },
        "household": {
            "agent": "household",
            "keywords": ["日程", "快递", "物业", "访客", "待办", "社区", "包裹", "预约", "客人", "通知"],
            "description": "家庭事务Agent：日程管理、快递追踪、物业对接、访客预约",
        },
    }

    def __init__(self):
        super().__init__(
            name="orchestrator",
            description="总管家v5.0：6 Agent语义意图路由、多Agent协调",
            system_prompt=ORCHESTRATOR_PROMPT,
        )
        self.shopping = ShoppingAgent()
        self.meal = MealPlannerAgent()
        self.appliance = ApplianceAgent()
        self.maintenance = MaintenanceAgent()
        self.security = SecurityAgent()
        self.household = HouseholdAgent()

    # ================================================================
    # 混合意图分类：关键词快速路径 + LLM 语义路由
    # ================================================================

    def _classify_keywords(self, msg: str) -> str | None:
        """快速关键词分类 — 低延迟快速路径"""
        m = msg.lower()
        for domain, info in self.DOMAIN_MAP.items():
            if any(k in m for k in info["keywords"]):
                return domain
        return None

    async def _classify_llm(self, msg: str) -> list[str]:
        """LLM 语义分类 — 支持多意图识别"""
        domain_list = "\n".join(
            f"- {d}: {info['description']}"
            for d, info in self.DOMAIN_MAP.items()
        )
        try:
            resp = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[{
                    "role": "system",
                    "content": (
                        f"你是意图分类器。将用户消息分类到以下领域（可多个）：\n"
                        f"{domain_list}\n"
                        f"另外还有 'general' 表示通用聊天。\n"
                        f"返回 JSON 对象，格式 {{\"intents\": [\"meal_plan\"]}}。"
                    ),
                }, {
                    "role": "user",
                    "content": msg,
                }],
                temperature=0,
                max_tokens=100,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or '{"intents":["general"]}'
            data = json.loads(text.strip())
            result = data.get("intents", ["general"])
            if isinstance(result, list):
                valid = [r for r in result if r in self.DOMAIN_MAP or r == "general"]
                return valid if valid else ["general"]
        except Exception as e:
            logger.warning(f"LLM classification failed: {e}")
        return ["general"]

    async def _classify(self, msg: str) -> list[str]:
        """混合分类器：先关键词，不确定再 LLM"""
        kw_result = self._classify_keywords(msg)
        if kw_result:
            # 简单启发式：检查是否可能是多意图
            if any(k in msg for k in ["并", "同时", "顺便", "还有", "另外", "以及"]):
                # 可能多意图，走 LLM
                return await self._classify_llm(msg)
            return [kw_result]
        return await self._classify_llm(msg)

    # ================================================================
    # 多 Agent 调度
    # ================================================================

    async def run(self, request: AgentRequest) -> AgentResponse:
        """主入口 — 语义路由到单个/多个 Agent"""
        intents = await self._classify(request.message)
        logger.info(f"Routing '{request.message[:50]}...' → {intents}")

        agents = {
            "shopping": self.shopping,
            "meal_plan": self.meal,
            "appliance": self.appliance,
            "maintenance": self.maintenance,
            "security": self.security,
            "household": self.household,
        }

        # 单意图
        if len(intents) == 1:
            intent = intents[0]
            if intent in agents:
                response = await agents[intent].run(request)
                response.intent = intent
                return response
            # general
            response = await super().run(request)
            response.intent = "general"
            return response

        # 多意图：并行执行各 Agent 然后融合结果
        agent_tasks = []
        for intent in intents:
            if intent in agents:
                # 为每个 Agent 构建独立的 request
                sub_req = AgentRequest(
                    session_id=request.session_id,
                    user_id=request.user_id,
                    message=request.message,
                    intent=intent,
                    context=request.context,
                )
                agent_tasks.append((intent, agents[intent].run(sub_req)))

        if not agent_tasks:
            response = await super().run(request)
            response.intent = "general"
            return response

        # 并行执行所有 Agent
        results = await asyncio.gather(
            *[task for _, task in agent_tasks],
            return_exceptions=True,
        )

        # 融合结果
        merged = await self._merge_results(
            request.message, intents, results, agent_tasks
        )

        return AgentResponse(
            session_id=request.session_id,
            response=merged,
            intent="+".join(intents),
            confidence=0.9,
        )

    async def _merge_results(
        self,
        original_query: str,
        intents: list[str],
        results: list[Any],
        agent_tasks: list[tuple[str, Any]],
    ) -> str:
        """用 LLM 融合多个 Agent 的结果为一个自然回复"""
        parts = []
        for (intent, _), result in zip(agent_tasks, results):
            if isinstance(result, Exception):
                parts.append(f"[{intent}] 处理失败: {str(result)}")
            elif hasattr(result, "response"):
                parts.append(f"【{self.DOMAIN_MAP.get(intent, {}).get('description', intent)}】\n{result.response}")
            else:
                parts.append(f"[{intent}] {str(result)[:500]}")

        if len(parts) == 1:
            return parts[0]

        # LLM 融合
        combined = "\n\n---\n\n".join(parts)
        try:
            resp = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[{
                    "role": "system",
                    "content": (
                        "你是总管家。将以下多个管家的回复融合成一个自然的回答。"
                        "保持口语化，用 emoji 分隔不同主题，禁止 Markdown。"
                        "不要丢失任何重要信息。"
                    ),
                }, {
                    "role": "user",
                    "content": f"用户问题：{original_query}\n\n各管家回复：\n{combined[:3000]}",
                }],
                temperature=0.4,
                max_tokens=1500,
            )
            return resp.choices[0].message.content or combined
        except Exception:
            return combined

    # ================================================================
    # 流式
    # ================================================================

    async def run_stream(self, request: AgentRequest):
        """流式对话 — 单 Agent 流式，多 Agent 合并"""
        intents = await self._classify(request.message)
        agents = {
            "shopping": self.shopping,
            "meal_plan": self.meal,
            "appliance": self.appliance,
            "maintenance": self.maintenance,
            "security": self.security,
            "household": self.household,
        }

        if len(intents) == 1 and intents[0] in agents:
            agent = agents[intents[0]]
            async for chunk in agent.run_stream(request):
                yield chunk
            return

        # 多意图/通用：走基类流式
        async for chunk in super().run_stream(request):
            yield chunk