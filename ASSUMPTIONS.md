# ASSUMPTIONS · Demo 简化假设与转生产条件

> 建立日期：2026-11-06（13.6）。原则：**demo 里每一处"先这样"都要留名**——这里登记所有已知简化假设、为什么可接受、以及转生产时必须换成什么。
> 与 `DECISIONS.md` 的区别：DECISIONS 记"选了什么"，本文记"什么被简化了、补齐的门槛"。

## 运行时形态

| # | 假设 | 为什么 demo 可接受 | 转生产条件 |
| :-- | :-- | :-- | :-- |
| A1 | 限流是**单进程内存滑动窗**（platform_core/ratelimit.py） | demo 单实例部署，重启清零无业务影响 | 多副本前必须换 Redis 分布式限流（接口已抽象，替换实现即可） |
| A2 | `route_id` 路线缓存是**进程内 dict**（agent-orchestrator `_RouteCache`），重启即丢，过期语义 2005 | 扫码接力只在几分钟窗口内有效，丢失可重查 | 多副本或重启敏感场景换 Redis 存储，保留同一 TTL 语义 |
| A3 | LangGraph checkpointer 用 PostgresSaver 单连接；测试/单模块 demo 时为 None（无持久化多轮） | demo 与 CI 不需要跨进程恢复会话 | 生产必须挂 checkpointer（make_checkpointer 已具备），并评估连接池 |
| A4 | 异步任务用 FastAPI BackgroundTasks，**不引 Celery**（REUSE.md 决策） | demo 无重批处理任务 | 出现定时任务/重试队列/横向扩容需求时，按 REUSE.md 流程评估引入 |
| A5 | 单 PostgreSQL 库承载全部模块表；多租户隔离靠**每查询注入 tenant_id**，无行级安全 | demo 租户数少，CI 有越权用例覆盖 | 转生产建议叠加 Postgres RLS 作为第二道防线；商户维度同理 merchant_id |

## 接口与安全

| # | 假设 | 为什么 demo 可接受 | 转生产条件 |
| :-- | :-- | :-- | :-- |
| A6 | 运维/内部端点（`/api/v1/agent/sessions/{id}/trace`、`/api/v1/agent/stats`、`/knowledge/ingest`、`/knowledge/retrieve`）**无鉴权** | demo 内网使用，只读统计 | 必须挂网关鉴权或运维 token；trace 含会话数据，不可公网裸奔 |
| A7 | 幻觉后置校验是**名单法**：回答中的店名必须出现在工具结果里，否则整条降级为列表卡片 | 店名级编造是最高频幻觉；列表降级保证不出错信息 | 数字/价格/时间类编造不在覆盖内；可叠加 NLI 类校验或结构化字段输出 |
| A8 | 底图渲染**双轨**：前端用 map-render 内嵌 SVG 资产（floors.ts），`map_layers.svg_url` 走 /static/maps 供契约消费方 | demo 前端打包内嵌最可靠；上传通道（脚本剥离）已就绪 | 定版后统一走 svg_url + 版本化 CDN；两轨必须指向同一份资产 |
| A9 | SVG 上传做了脚本剥离（`<script>`/`javascript:`/事件属性），但**未做** schema 级白名单校验 | 人工上传、来源可控 | 开放第三方上传时补 schema 白名单与文件大小/尺寸上限 |

## AI 行为口径

| # | 假设 | 为什么 demo 可接受 | 转生产条件 |
| :-- | :-- | :-- | :-- |
| A10 | 评测基线 **30 条、通过率方差带 77-90%**（LLM 非确定性）；判据为内容命中 | 方差带内的波动不视为回归；稳定失败项单独立案归因（见 EVAL_baseline.md） | 改 prompt/工具/模型后重跑对比基线；上线前将判据自动化进 CI（mock 模式） |
| A11 | token 统计口径：intent_parse 与 generate 两步 `output.usage` 求和；provider 不返回 usage 时记 0，不阻断 | 用量是运营参考，不是计费依据 | 计费场景需 provider 级强保证（缺 usage 视为错误） |
| A12 | 模型调用单供应商（OpenAI 兼容协议）+ 环境变量配置；无多 Key 轮询 | 最小陌生面决策（自建 Provider 抽象） | 多供应商/Key 轮询需求出现时，按 REUSE.md 流程评估，封装在 provider 模块内 |

## 数据与场景

| # | 假设 | 为什么 demo 可接受 | 转生产条件 |
| :-- | :-- | :-- | :-- |
| A13 | D-029：空间能力**挂 M8（content-service 空间端点）+ spatial_model 纯函数库**，偏离 PRD 的独立空间服务（决策与恢复条件见 DECISIONS.md） | 减少一个服务进程；核心包 M3/M5/M6/M7/M9 已验证零改动换场景 | 多场景并发/空间计算量大时拆独立服务，纯函数库可整体平移 |
| A14 | 场景数据质量靠 **scripts/scene_check.py 体检**（导入后手动跑，不在 CI） | 换场景是低频操作；CI 无法预知下一场景的数据形态 | 若开放商户自助导入，体检必须前移为导入流程的强制步骤 |
| A15 | 故障演练 **scripts/chaos_test.sh 为发布前手动体检**（连真实服务与真实模型） | 六条降级路径依赖真实进程/容器操作，CI 密闭环境做不了 | 生产环境换 k8s job 或混沌平台执行，断言复用 |
| A16 | 演示数据（山雀里/栖云广场）为**虚构商场**；评测基线与 seed 绑定该数据形态 | 作品集 demo 需要可讲述的一致故事线 | 新场景交付 = 跑 M2 导入器 + scene_check + 重跑评测基线 |

## 维护纪律

- 新增简化时**必须**在本文登记一行；转生产完成时把状态改为"已补齐"并注明日期。
- 与 CLAUDE.md 第 7 节禁止事项冲突的简化（权限、租户过滤、密钥）**不允许**出现在本表。
