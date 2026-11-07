## 概述

<!-- 一句话说明本 PR 做了什么 -->

## 自查清单（CLAUDE.md 工作流）

- [ ] 已先出方案并获负责人确认
- [ ] 新增/修改测试并本地跑绿（贴命令与输出）
- [ ] `ruff` + `lint-imports` 通过
- [ ] 前端改动已跑 `test` + `tsc` + `eslint`
- [ ] 涉及接口已同步 `packages/api-contract/openapi/`
- [ ] 表结构仅新增 Alembic 迁移，未改已有迁移
- [ ] 所有查询已注入 `tenant_id`（必要时 `merchant_id`）
- [ ] 无密钥/Token 入库；日志无手机号原文
