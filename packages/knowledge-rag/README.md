# M6 knowledge-rag — 自建 RAG 管道

## 做什么

切片（300–500 token、重叠 50、段落边界优先）→ 向量化（自建 LLMProvider，OpenAI 兼容）→ pgvector 入库（knowledge_chunks）→ 检索（租户强制过滤 + 向量 Top20 → 重排 Top5 → 阈值过滤 → 带出处）→ Provider 不可用时降级关键词检索。不引入 LlamaIndex。

## 对外接口

- `knowledge_rag.provider`：`make_provider()`（有 `LLM_API_KEY` 用真实 OpenAI 兼容 Provider，无 key 落 `MockProvider` 确定性向量）、`DailyLimitError`/`ProviderUnavailableError`
- `knowledge_rag.chunking`：`estimate_tokens` / `split_into_chunks`（纯函数）
- `knowledge_rag.ingest`：`ingest_venue(venue_name, tenant_code)` — 切片+批量向量化+幂等 upsert，返回 `{documents, chunks}`
- `knowledge_rag.retrieval`：`retrieve(tenant_id, venue_id, query, threshold=None)` → `list[RetrievedChunk{document_id, title, content, score, rerank_score, source}]`

## 如何单独运行

```bash
make compose-up && make migrate && make seed
uv run --package knowledge-rag python -c "from knowledge_rag.ingest import ingest_venue; print(ingest_venue('山雀里·栖云广场','shanqueli-demo'))"
uv run python scripts/run_agent_eval.py --stage retrieval            # 20 问 Top3 命中率
uv run --package knowledge-rag pytest packages/knowledge-rag/tests
```

## 示例

```
{'documents': 100, 'chunks': 100}          # ingest 实测
Top3 命中率：10/20 = 50%（provider=mock(待真实模型), threshold=0.05）
```

**当前命中数字为 MockProvider（sha256 确定性向量，无语义）下的管线验证值**；在 `.env` 填 `LLM_API_KEY`（OpenAI 兼容网关即可）后重跑 ingest 与评测即得真实数字，评测脚本自动标注 provider 类型。embedding 维度 1024（`EMBED_DIM`，Provider 经 dimensions 参数对齐 text-embedding-3-small 等 Matryoshka 模型）。

## 如何摘出复用到其他项目

三层全部可拆：① `chunking.py` 纯函数零依赖（token 估算规则一行讲清：CJK 1 字≈1 token、其余 4 字符≈1 token）；② `provider.py` 只依赖 openai SDK，环境变量配置 + 每日限额（进程内计数）+ mock 降级；③ `retrieval.py` 的检索 SQL 是一段可独立复用的模板——`WHERE tenant_id AND venue_id ORDER BY embedding <=> :q`，换表名即用。换场景重写只有 seed 数据与阈值。
