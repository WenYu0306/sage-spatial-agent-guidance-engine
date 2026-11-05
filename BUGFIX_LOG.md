# BUGFIX_LOG

> 13.3 铁律台账：日期 | 现象 | 根因 | A/B 类 | 复现测试路径 | 修复位置。
> A 类=通用缺陷（跟模块走）；B 类=场景假设缺陷（换场景必须重跑 tests/scenario/）。

| 2026-11-05 | 同会话累计 6 次工具调用后整轮锁死 | checkpointer 跨轮还原 tool_calls 不清零 | A | test_service.py::test_tool_budget_resets_per_turn | agent_orchestrator/app.py invoke 显式重置轮内状态 |
| 2026-11-05 | 检查点持久化在所有部署中从未生效（静默降级内存） | 三层叠加：from_conn_string 是 contextmanager 被当对象用；SQLAlchemy 方言串 psycopg 不认；setup() 的 CONCURRENTLY 索引需 autocommit 连接 | A | test_service.py::test_make_checkpointer_prefers_postgres_and_never_silent | agent_orchestrator/app.py make_checkpointer（长连接+方言归一+autocommit） |
| 2026-11-05 | F1 问厕被指去 B1 卫生间 | route.plan 按名 ilike 解析在并列 hot_score 同名设施间随机选层；计划步骤 args 在工具列表执行前一次性算好 | A | test_tools.py::test_route_plan_by_poi_id + test_nearest_and_route_plan_shares_target | tools.py to_poi_id 直取 + graph.py 惰性 callable 步骤 |
| 2026-11-05 | 『适合一家人吃饭』返回降级空结果 | poi.search 场景词 jsonb @> 精确匹配，自然语言场景词全搜空 | A | test_tools.py::test_poi_search_scene_tag_bidirectional_match | tools.py 场景词与标签双向子串包含 |
| 2026-11-05 | 同会话第二轮起 recommend.rank 恒空候选 | 计划步骤读节点入口冻结 state，同轮前序结果不可见 | A | test_service.py::test_rank_step_receives_same_turn_search_candidates | graph.py 步骤视图带累积 results |
| 2026-11-05 | 部分问句整轮 3001 崩溃 | trace 落库 json.dumps[:2000] 盲截断产出非法 JSON | A | test_graph.py::test_trace_clip_always_valid_json | graph.py _clip 包裹截断 |
| 2026-11-05 | 3001 异常无任何日志 | except Exception 静默吞（违反不吞异常红线） | A | test_service.py 手工复现+日志断言 | app.py logger.exception |
| 2026-11-05 | 『最近的服务台』无位置时返回任意设施且谎称同层 | 无位置上下文距离恒 1e9、same_floor 恒 True | A | test_tools.py facility 相关用例 | tools.py 无位置按热度+不声称同层 |
| 2026-11-04 | 『附近有什么咖啡店』被误判幻觉降级 | 幻觉抽取器把用户话术回声当店名 | A | test_graph.py::test_unknown_poi_names_skips_question_echo | graph.py stop_chars 过滤 |
| 2026-11-04 | 优惠关联门店被误判幻觉 | promotion.list 出参无门店名进校验白名单 | A | test_graph.py::test_known_poi_names_collects_promotion_store_names | tools.py poi_name 出参 + graph.py 采集 |
| 2026-11-05 | 领券成功恒显示『暂时领完』 | 前端读后端不存在的 claimed 字段；售罄走 200+4002 未处理 | A | 手工验收（前端无渲染测试，缺口已记） | mobile Coupons.tsx 对齐出参+error_code |
| 2026-11-05 | 8 折券显示『满 0 减 80』 | 前端 type vs coupon_type 漂移且 percent 不在枚举 | A | 手工验收（同上缺口） | mobile/screen couponDetail 按真实枚举 |
| 2026-11-05 | 搜索结果点击跳 #/poi/undefined | 前端 poi_id vs 后端 id 漂移 | A | 手工验收（同上缺口） | mobile Search.tsx 对齐 |
| 2026-11-05 | 指标午夜后漏事件 | overview/timeseries 按 UTC 分桶而非场地时区 | A | test_app.py::test_overview_counts_events_in_venue_timezone | analytics _venue_tz |
| 2026-11-05 | guest 可读草稿活动/POI | 读端点未强制 published | A | test_reads.py::test_guest_reads_published_only | content guest 强制 published |
| 2026-11-05 | venue_admin 可创建 platform_admin（提权） | user_create 无角色层级校验 | A | test_security_p2.py::test_user_create_cannot_escalate | content 角色层级拦截 |
| 2026-11-05 | merchant 建号无门店绑定 | UserCreate 无 store 字段 | A | test_security_p2.py::test_user_create_merchant_requires_store | content store 必填+绑定 |
| 2026-11-05 | 商户 A 可改/发布商户 B 的活动 | _load_act_for_write 无归属校验 | A | test_security_p2.py::test_merchant_cannot_patch | content 归属校验 |
| 2026-11-05 | 心跳可冒充同场地其他设备 | 无 device_id 身份绑定 | A | test_heartbeat.py::test_heartbeat_cannot_spoof_same_venue_device | content 身份绑定先于范围 |
| 2026-11-05 | events 可伪造租户/时间污染指标 | 无鉴权且信客户端 tenant/venue/occurred_at | A | test_app.py::test_events_server_side_clamp | analytics 服务端钳制 |
| 2026-11-05 | 登录爆破/场地枚举/扫 ID 清券无限制 | 无限流器 | A | test_rbac_api.py/test_app.py 限流用例 | platform_core/ratelimit.py + 三处接线 |
| 2026-11-05 | 账号锁定文案构成存在性 oracle | D-019 防枚举未贯彻到锁定分支 | A | test_rbac_api.py::test_locked_account_message_has_no_oracle | auth_router 文案统一 |
| 2026-11-04 | 多轮评测取错意图/判据恒真 | actual 取会话首条 intent；type_check 含 chain 恒真 | A | （评测脚本级，eval 复跑验证） | run_agent_eval.py |
| 2026-11-05 | 『电梯』搜不到直梯 | 意图 prompt 无分类字典同义词归一 | B | eval E11（评测级复现） | intent_system.txt 设施词归一 |
| 2026-11-05 | 登录链路 device_id 从未填充 | _load_identity 未查 devices（auth.py 约定未落地） | A | test_heartbeat.py::test_devices_me_returns_own_row | auth_router _load_identity |

| 2026-11-05 | 跨天营业时段（22:00-02:00）凌晨判停业 | 营业解析不支持 end<=start 的跨午夜跨度；首版合并查又在 21:00 产生假阳性 | B | tests/scenario/test_dirty_data.py::test_02_overnight_hours_open_at_1am | content _open_now 两半拆分算法 |
| 2026-11-05 | open_now=true 时空营业时间店铺消失 | 过滤把"未知"当"关闭"剔除 | B | test_dirty_data.py::test_03_empty_hours_not_dropped | content open_now 未知保留 |
| 2026-11-05 | 无 level=1 楼层的场地（医院 3/-2/2）路线规划 500 | M3 scale 查询硬编码 f.level=1 假设 | B | test_dirty_data.py::test_05/06/07/10（场景类全挂） | route-engine/db.py 任取场地 scale |
| 2026-11-05 | 脏场地路线规划 500（无 map_layers） | load_route_graph 异常未按 PRD 降级 | A | test_dirty_data.py（2004 断言） | route-engine/app.py except→2004 |
| 2026-11-05 | M5 起点解析失败被吞成"缺少起点" | nearest-node HTTPError 无细节即吞 | A | tools.py 起点解析失败消息含 exc | tools.py 消息带原因 |
| 2026-11-05 | 领券幂等重放被工具判为未领取 | 重放回执无 id 键，工具按 id 判定 | A | test_tools.py::test_coupon_claim_idempotent | tools.py 按 error_code 判定 |
| 2026-11-06 | 新场地路网 15 个连通分量（跨层不可达） | 导入器把扶梯/电梯插成独立节点，walk 网无边接入 | B | scripts/scene_check.py 路网连通项（修后 2243 节点全连通） | import_mall_scene 3.5 垂直节点吸附最近 2 个 walk 节点 |
| 2026-11-06 | 导入器二次执行即失败 | 幂等清理对 coupon_claims 用了不存在的 venue_id 列 | A | import_mall_scene 连续重跑两次验证 | 清理改经 coupons 子查询先行 |
