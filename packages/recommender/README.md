# M7 recommender — 八因子推荐打分（PRD 8.4 / F-16）

## 做什么

对候选 POI 做可解释打分：`score = Σ(factor_score_i × weight_i)`，八因子
（距离 0.22 / 楼层差 0.10 / 营业状态 0.15 / 当前优惠 0.15 / 商户权重 0.10 /
热度 0.10 / 标签匹配 0.13 / 位置便利度 0.05）。`scoring.py` 是纯函数内核
（零 DB、零业务词）；`features.py` 从共享表装配泛化特征（坐标/楼层/营业
时间/标签/热度/主动线距离）；**营销旗标由调用方传入**——营销数据表不进内核。
每条打分写 `recommend_logs`（因子明细 + 理由，PRD 8.5）。候选空返回空列表
不报错；休息中候选直接过滤；权重固定配置文件（F-16：不做后台可调，调权走
git 修订）。

## 对外接口

- `POST /recommend/rank`：`{tenant_id, venue_id, candidates:[poi_id],
  position:{x,y,floor_id}, tags, promotion_poi_ids, message_id?}` →
  `{ranked: [{poi_id, name, score, factors(8 因子), reasons(≤3 条), floor}]}`
- `GET /health`
- 契约细节：`python -m uvicorn recommender.app:make_app --factory --port 8944`
- 时间注入点：环境变量 `SAGE_TIME_OVERRIDE`（ISO，测试/演示用；生产留空走真实时钟）

## 如何单独运行

```bash
cd packages/recommender && make demo   # 真库三条候选打分 + factors/reasons 展示
# 前置：根目录 make migrate && make seed
```

## 示例（make demo 真实输出摘要）

```
#1 巨幕星云影院 score=0.7184  reasons=['距离最近','正在营业','同层或就近楼层']
   factors: distance=0.9583 hot=1.0 business=1.0 merchant=1.0 ...
#2 …
```

## 如何摘出复用到其他项目

- **复制**：`recommender/`（scoring+features+app 约 300 行）与 `config/recommend_weights.yaml`
- **改配置**：权重与归一化刻度都在 yaml（和必须 1.0）；候选特征 SQL 按你的
  实体表改（需提供坐标/楼层/营业时段/热度/权重五类泛化列）；营销类旗标保持
  调用方注入
- **跑验证**：`pytest tests/ -q`（16 条纯内核 + 7 条服务集成，覆盖率 94%）
- **适用**：任何"多因子加权排序 + 可解释理由"场景（网点推荐/内容排序/排班
  优先级），内核与业务表解耦的设计可直接平移
