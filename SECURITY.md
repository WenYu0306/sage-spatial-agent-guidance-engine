# 安全策略

## 支持版本

仅 `main` 分支最新版本（本项目为作品集 demo，不做旧版本维护）。

## 漏洞上报

- 渠道：GitHub Security Advisory（仓库页 Security → Report a vulnerability）。
- 响应时限：72 小时内确认，7 天内给出修复或缓解方案。
- 范围：仓库代码与部署配置。**不含**本地/演示环境自担风险的弱配置（已登记于 ASSUMPTIONS.md 的简化项）。

## 已知设计边界

见 [ASSUMPTIONS.md](ASSUMPTIONS.md)（A1-A17）：单进程限流、进程内缓存、多租户靠查询注入等均为登记过的 demo 简化，转生产条件逐条在列。
