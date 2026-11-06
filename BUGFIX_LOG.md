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
| 2026-11-06 | nginx 运行时 emerg 拒启 | /static/maps/ location 写在 server 块外（M2 批次写入后从未真跑过 nginx，镜像构建不校验配置） | A | deploy.sh 演练 compose up 失败复现 | admin.conf 挪入 server 块 |
| 2026-11-06 | 容器内 LLM 调用全 400（全量降级 3001） | .env.demo 模板用幽灵变量 LLM_MODEL——代码读 LLM_CHAT_MODEL，默认值不在 API 支持列表 | A | 容器内 openai SDK 复现 400 | 模板换真名+真值并补 EMBED_DIM |
| 2026-11-06 | 静态底图全 404 | compose 挂载 ../maps 相对 deploy/ 解析为仓库根/maps（不存在→空目录），应为 ./maps | A | nginx 容器内 ls 挂载目录为空 | compose.demo.yml 挂载路径修正 |
| 2026-11-06 | deploy.sh 一启动即崩（SHA\xef unbound） | macOS bash 3.2 把 $VAR 紧跟的全角括号首字节吞进变量名；[[ ]] 引号段+glob 混合模式尾部 * 被转义 | B | bash deploy.sh / 匹配单测分别复现 | $VAR 紧贴 CJK 处加花括号；匹配改 grep -qF |
| 2026-11-06 | D-029 后 seed 断言连锁假红（扶梯 18 条/venues=2/floors=6） | seed 计数与路网测试按"单场地库"全表查询，第二验收场地并存即漂移 | B | 本地全量测试暴露（CI 全新库不触发） | count_rows 场地域表按演示场地口径；graph fixture 钉场地 |
| 2026-11-06 | 未知/脏场地打崩 route-engine worker，2004 降级不可达 | db 层 SystemExit(BaseException) 穿透 except Exception | A | test_service.py::test_plan_unknown_venue_is_business_error_2004 | route_engine/db.py 改抛 RouteError(2004) |
| 2026-11-06 | traffic_by_hour 两粒度恒 500 | 分桶 SQL 含 tz 占位但参数漏传 tzname（M9 时区修复漏此分支） | A | test_app.py::test_traffic_by_hour_timeseries_both_grains | analytics app.py 补 [tzname]+params |
| 2026-11-06 | 登录锁定窗口恒 1 秒（实测传 3600/86400 均 1.0s） | interval '%s seconds' 字面量内 %s 变 $1 不绑定 | A | test_auth.py::test_lockout_window_matches_policy | auth.py make_interval(secs => %s) |
| 2026-11-06 | 全部工具 trace latency_ms 恒 0ms | t0 写在 run_tool 之后 | A | test_graph.py::test_tool_trace_latency_is_measured | graph.py t0 前移 |
| 2026-11-06 | 跨租户 venue_id 经 /pois/nearest 读穿 | 未比对场地租户与 token 租户（红线违例） | A | test_m2_spatial.py::test_pois_nearest_cross_tenant_venue_denied | content _venue_of_tenant + active 复核 |
| 2026-11-06 | guest 活动列表恒空 | 活动状态机无 published 态，guest 过滤永不匹配（S-1 把 POI 词汇误套活动） | A | test_activities_coupons_knowledge.py::test_guest_sees_active_activities | content act_list status='active' |
| 2026-11-06 | events 缺必填字段直落 500 泄堆栈 | EventsBody 收未校验 dict，event_id/actor_type 无前置校验 | A | test_app.py::test_events_missing_required_fields_use_error_envelope | events.py _normalize 校验 + 端点 422 信封 |
| 2026-11-06 | admin 全局 502 页使 API 客户端抛裸 SyntaxError | mapResponse 裸 JSON.parse 绕过信封与 401 登出 | A | admin tests/auth.test.ts 非 JSON 两用例 | api.ts try/catch + 401 补触发 |
| 2026-11-06 | 知识编辑内容可能被静默覆盖 | 渲染期 setState + 『（载入中…）』哨兵串回填 | A | 手工（React hook 行为，渲染测试缺口照旧） | Knowledge.tsx useEffect 函数式回填 |
| 2026-11-06 | chaos SVG 注入/堆栈泄漏断言从未可能失败 | grep -qv 逐行取反，多行输入恒真 | A | 就地提取双分支验证（含旧逻辑恒真空证） | chaos_test.sh 断言整体匹配后取反 |
| 2026-11-06 | 部署回滚静默空转 | SAGE_TAG 先于 git pull 计算，回滚点与当前同 tag | A | git 沙箱实测（pull 后 HEAD + 显式覆盖） | deploy.sh tag 移到 pull 后 |
| 2026-11-06 | trace/stats/recommend-rank 公网裸奔；限流塌缩全局单桶；JWT 公开示例值可签发 | nginx 暴露面过宽 + client.host 代理失真 + .env.example 公开密钥 | A | test_auth.py client_ip/_secret 两用例 + nginx -t | admin.conf 收敛+XFF；client_ip()；_secret() 守卫；A6 状态更新 |
| 2026-11-06 | seed 活动恒处状态机外 published 态（guest 修复后暴露为列表恒空） | seed.py 沿用 S-1 词汇误套，插值超出 ACT_TRANSITIONS 枚举 | B | test_tools.py::test_promotion_list（数量断言对共享库） | seed.py 活动 upsert 两处 status='active' + dev 库一次性 UPDATE |
| 2026-11-06 | 知识检索三测试突红（文档批次零代码改动） | D-029 双场地并存 + 测试夹具 fetchone() 无排序，行序漂移后取到无 chunk 的第二场地（8b4b4da 同类残留） | B | knowledge-rag tests 本地全量（CI 全新库不触发） | 两处夹具钉 v.name='山雀里·栖云广场' |
| 2026-11-06 | 公网问答设施问句全走兜底（本地 dev 与测试从未暴露） | compose agent 容器漏注 SVC_CONTENT、content 漏注 SVC_KNOWLEDGE_RAG（容器内 127.0.0.1 缺省指向自身）；补 env 时 service 级 environment 浅合并覆盖锚点丢 DATABASE_URL，content 崩溃循环 | A | 公网冒烟 + 服务器 agent_traces（nearest 空/route 2004 兜底文案） | compose.demo.yml 两处 environment 补齐（DB 变量重述） |
