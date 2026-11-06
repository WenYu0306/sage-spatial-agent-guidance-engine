# 难点解析 ③ · 从 demo 到公网：生产化加固实录

> 作品集项目最常见的短板是"能跑，但不敢上线"。SAGE 反着来：
> 架构按生产标准设计，然后真的上了公网（sage.westwardecho.com）。
> 这篇记录三级加固：安全审计 → 故障演练 → 公网部署与独立审查。

## 第一级：安全审计 20 项高危分级修复

自建多租户系统最大的风险是"每个查询都记得注入 tenant_id"这类纪律靠自觉。对策：

- **审计先行**：对全部服务做一轮高危清单审计（鉴权/越权/枚举/幂等/限流/日志泄漏 20 项），分级 P0/P1/P2 逐批清零；
- **P0 六项**：提权拦截（建号角色层级）、商户归属校验（_load_act_for_write）、心跳身份绑定、领券 IP 限流、events 服务端钳制（tenant/venue/occurred_at 一律服务端裁定）、登录限流；
- **纪律进 CI**：import-linter 三契约（内核禁依赖业务模块 / 模块间禁互相 import / 纯函数库禁依赖兄弟）+ tools.py 禁 psycopg 的 grep 门；
- 每一项修复都有越权用例测试（`test_security_p2.py` 等），不是"改了就算"。

幂等是另一个硬红线：领券以 `coupon_id + anonymous_id` 唯一键原子扣减，重放即补偿回滚，防止双重回冲。

## 第二级：故障演练 chaos_test.sh（6 场景 16 断言）

降级路径写了不等于通了。发布前跑六场景演练（连真实进程与真实模型）：
断库、断 Redis、断兄弟服务、断模型、脏场地、注入尝试——16 条断言逐条核对降级语义
（2004 脏场地、2003 不可达、8s 知识超时降级检索、3001 记日志不静默……）。

演练的价值在被抓的三个新 bug：nginx location 写在 server 块外直接 emerg 拒启、
LLM_MODEL 幽灵变量让容器落到错误模型、maps 挂载路径错一位。**体检仪本身也会坏**——
后来一次独立审查发现演练脚本自己的 `assert_not_contains` 用 `grep -qv` 对多行输入恒真，
SVG 注入断言从未可能失败（修复 + 就地双分支验证，见 BUGFIX_LOG 2026-11-06）。

## 第三级：公网部署（M13 SHIP 流程）

服务器只有 2C4G，没有镜像仓库。SHIP 流程：

1. 本机 `DOCKER_DEFAULT_PLATFORM=linux/amd64` 构建（Apple Silicon → 服务器 amd64）；
2. `docker save | gzip | ssh docker load` 直传镜像；
3. 服务器 `SKIP_BUILD=1` 七步脚本：拉码 → 迁移 → 起服务（`--wait` 健康门）→ 健康检查 → 灌数据；
4. 回滚点在重建前落盘 `.previous_release`。

公网 502 三连环排查（每一环都进了台账）：
**caddy 容器内 127.0.0.1 自指**（改 host.docker.internal）→ **我们 nginx 绑回环**（改绑 docker0 网关 172.17.0.1）→ **compose 回落 stale latest 镜像**（SAGE_TAG 固化进服务器 deploy/.env）。
此外 admin 白屏 = vite 无 base 导致 /assets 绝对路径 404（VITE_BASE=/admin/ 注入）。

## 第四级：全项目独立审查（2026-11-06）

上线后跑了一轮多维度机器审查（14 个审查员 × 5 分区 + 每条 HIGH 独立对抗验证）：
112 条原始发现 → 16 个确认根因全部处置。值得看的三个：

- **登录锁定窗口恒 1 秒**：`interval '%s seconds'` 字面量里的占位符被 psycopg 转成 `$1` 文本，
  Postgres 把 `interval '$1 seconds'` 解析成 1 秒——实测传 3600/86400 都得 1.0s，锁定形同虚设。修复 `make_interval(secs => %s)`；
- **换场景接入器的同类假设**：guest 活动过滤与 seed 数据共用状态机外的 `published` 状态，
  demo 看似正常、实为非法状态——代码与数据互相将错就错，修一半会暴露另一半；
- **运维端点公网化**：上线后 A6 假设（"内网使用"）失真，nginx 收敛 trace/stats/rank 公网路径。

全部 13 行进 `BUGFIX_LOG.md`，每条带复现测试路径。

## 诚实边界（ASSUMPTIONS.md A1-A16）

demo 简化假设全部留名：单进程内存限流（A1）、进程内路线缓存（A2）、checkpointer 形态（A3）、
单库多租户靠每查询注入（A5）……每条都写明"为什么 demo 可接受"与"转生产必须换成什么"。
**这份清单本身就是工程判断力的一部分**：知道简化了什么，比假装没简化更接近生产。
