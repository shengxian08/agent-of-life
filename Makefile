.PHONY: build up down restart eval seed clean logs deploy deploy-down

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose down; docker compose up -d

# ====== 生产部署 ======
deploy:
	cp -n .env.production .env 2>/dev/null || true
	@echo "请先编辑 .env 填入 API Key，然后运行: make deploy-up"

deploy-up:
	docker compose -f docker-compose.prod.yml up -d --build
	@echo "部署完成，访问 http://你的服务器IP"

deploy-down:
	docker compose -f docker-compose.prod.yml down

eval:
	cd backend && python -m app.eval.ragas_eval
	@echo ""
	@echo "========================================"
	@echo "  📊 RAG Evaluation Summary"
	@echo "========================================"
	@cd backend && python -c "import json; r=json.load(open('../data/eval_report.json','r',encoding='utf-8')); s=r['scores']; print(f\"  Faithfulness:       {s.get('faithfulness','-'):.4f}\"); print(f\"  Answer Relevancy:   {s.get('answer_relevancy','-'):.4f}\"); print(f\"  Context Precision:  {s.get('context_precision','-'):.4f}\"); print(f\"  Context Recall:     {s.get('context_recall','-'):.4f}\"); print(f\"  Retrieval Hit Rate: {s.get('retrieval_hit_rate','-'):.4f}\"); print(f\"  Non-Fallback Rate:  {s.get('non_fallback_rate','-'):.4f}\"); print('========================================')" || echo "  (run 'make seed' first to populate knowledge base)"

seed:
	cd backend && python -m app.eval.seed_knowledge

seed-and-eval: seed eval

clean:
	cd backend && python -c "from app.memory.vector_store import get_vector_store; import asyncio; asyncio.run(get_vector_store().add(texts=[], ids=[]))"
	rm -rf backend/data/logs/*.log

logs:
	docker compose logs -f
