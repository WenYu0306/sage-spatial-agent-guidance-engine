# 发布材料包 · 程序员客栈投递用

> 用途：直接可贴的投递文案与链接清单。数字全部来自仓库台账，不即兴。

## 一句话简介（两版）

**短版（30 字内）**
> 场景无关的空间智能体导视平台：AI 问答 + 跨楼层导航 + 运营后台，已上公网。

**长版（约 120 字）**
> SAGE 是一个多租户空间智能体导视平台（LangGraph 编排 + pgvector RAG + 自研路径引擎），
> 首场景为商场 AI 导视：大屏流式问答、跨楼层路线与扫码接力、商户运营后台、数据看板。
> 核心验证是"换场景零改码"——第二个商场（米制坐标、2,243 节点路网）接入时代码零改动。
> 已部署公网 demo，评测基线 30 条、首轮通过率 90%。

## 亮点速览（面试官 30 秒版）

1. **Agent 工程可复现**：数据驱动计划步 + 工具预算（6 次/12s）+ 幻觉名单法后置校验，全链路 trace 落库可回放（亮点①：docs/highlights/01-agent-orchestration.md）
2. **换场景零改码**：空间计算是纯函数库，接入器 + 八项体检 + 评测重跑构成交付流水线；体检首跑抓到 15 个路网孤岛并修复（亮点②：docs/highlights/02-scene-portability.md）
3. **真的上了公网**：安全审计 20 项分级清零 → 6 场景故障演练 → 2C4G 服务器 SHIP 流程 → 公网 502 三连环排查 → 全项目机器审查 16 根因全处置（亮点③：docs/highlights/03-production-hardening.md）
4. **工程纪律**：296 后端测试 + 47 前端测试全绿、13.3 台账（每 bug 带复现测试路径）、ASSUMPTIONS 留名所有 demo 简化

## 链接清单

| 项 | 值 |
| :-- | :-- |
| 仓库（公开） | https://github.com/WenYu0306/sage-spatial-agent-guidance-engine |
| 公网大屏（核心体验） | https://sage.westwardecho.com/screen/ （免配置直接用） |
| 公网运营后台 | https://sage.westwardecho.com/admin/ （演示口令线下提供） |
| 公网手机落地 | 大屏问答→发到手机→扫码，落地于 /m/route/{id}（公网全链路） |
| 根 README | 仓库首页（架构图 + 硬数字 + 模块地图） |
| 难点解析 ×3 | docs/highlights/ |
| 演示视频 | ≤2 分钟（docs/video-script.md 为分镜与录制判据） |
| License | PolyForm Noncommercial 1.0.0（可商用需另授权） |

## 投递注意事项

- 技术栈关键词（对齐平台检索）：LangGraph · FastAPI · pgvector/RAG · React/TS · Docker · 微服务 · 多租户
- 面试可直接讲的三个故事：跨步骤惰性求值（被评测掩盖两周的缺陷）、体检抓孤岛（换场景的静默降级）、锁定窗口 1 秒（审查抓到的把戏级 bug）
- 展示优先级：公网大屏现场操作（/screen/ 问一句+扫码接力）> 视频 > 亮点文档 > 代码走读
- 演示视频（113s，furrow 主题）已按 docs/video-script.md 录制完成
