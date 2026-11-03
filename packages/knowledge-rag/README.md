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

**三档实测数字（20 问 Top3 命中率，脚本自动标注模式）**：
① MockProvider（sha256 伪向量）= 50%，仅证明管线贯通；② 关键词降级模式 = 50%（Provider 404/不可用时自动触发），命中语义精准但覆盖窄（ILIKE 仅取前 3 个二元组）；③ **真实向量（阿里百炼 text-embedding-v3，1024 维，阈值 0.35）= 85%（17/20）**——语义命中如"便宜的午餐"→轻食沙拉、"咖啡店"→三家咖啡店全中。3 个未命中均可解释：E16 领券数据在 activities 表（M5 工具侧）、E19 天气本应走兜底（M5）、E04 为排序未进 Top3（M7 权重可调）。chat=DeepSeek、embed=百炼的双供应商由 Provider 双端点配置支撑（EMBEDDING_* 缺省回落 LLM_*）。

## 如何摘出复用到其他项目

三层全部可拆：① `chunking.py` 纯函数零依赖（token 估算规则一行讲清：CJK 1 字≈1 token、其余 4 字符≈1 token）；② `provider.py` 只依赖 openai SDK，环境变量配置 + 每日限额（进程内计数）+ mock 降级；③ `retrieval.py` 的检索 SQL 是一段可独立复用的模板——`WHERE tenant_id AND venue_id ORDER BY embedding <=> :q`，换表名即用。换场景重写只有 seed 数据与阈值。
