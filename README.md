# NicheRadar

一个面向 Polymarket 小众事件市场的影子盘监控机器人。

当前项目不接真实下单，只做公开市场读取、外部证据评分、信号生成、风控过滤、watchlist 定向监控、变化告警、SQLite 落库和 shadow fill 模拟。

## 目标

这个机器人不追求高频套利，也不做 BTC 5m、尾部彩票、鲸鱼跟单或结算收割。当前策略方向是：

- 关注规则清楚、外部证据可验证的小众事件市场
- 优先内容发布、专辑发布、AI/公司事件、产品发布类市场
- 只在模型方向、风控、目标价带和盘口价格同时满足时记录 shadow fill
- 所有信号和模拟成交都可审计、可回放

## 当前能力

- 从 Polymarket Gamma API 拉市场元数据
- 从 Polymarket CLOB API 读取 YES/NO 两侧 orderbook
- 根据 `outcomes` 和 `clobTokenIds` 显式映射 YES/NO token
- 解析常见市场类型：`content_release`、`announcement`、`ipo_event`、`social_activity`
- 从 RSS/Atom/Google News RSS 抓外部证据
- 生成 `p_model`、方向、edge、net edge、最大入场价
- 按音乐发布、产品发布、IPO 事件拆分模型 profile、基准概率和证据权重
- 按成交量、到期时间、价差、置信度、edge 做风控过滤
- 对 watchlist 做定向轮询、JSONL 追加、SQLite 落库
- 记录价格进目标带、信号转可用、证据分跳升等 alert
- 记录满足条件的 shadow fill，不触发真实订单
- 对已有 shadow fill 按后续快照写入 mark，便于观察浮动表现
- 回放 shadow PnL，支持按最新 mark、手动平仓价或最终结算方向统计
- 生成 SQLite 报表和本地 HTML dashboard，汇总 edge、alert、shadow fill 和 PnL 表现
- 对 shadow fill 做组合级敞口控制，并在亏损或仓位过多时触发熔断
- 基于 shadow fill、mark 和可选 settlement 文件生成 model_profile 校准报告
- 基于本地 SQLite 快照、shadow fill、mark 和 settlement 文件生成离线 backtest 报告
- 在 dashboard 中展示 backtest summary、profile 校准和 profile PnL
- Polymarket API 和 RSS 抓取带基础 retry/backoff
- Gamma/CLOB/RSS 支持 SQLite HTTP 缓存和进程内请求限速
- 单个 slug 或盘口读取失败不会中断整轮 watchlist
- 提供最小回归测试

## 目录

- `bot/api.py`：Polymarket 公开读 API 客户端
- `bot/market_scanner.py`：Gamma 市场行转换、YES/NO orderbook 补全
- `bot/market_parser.py`：市场标题/规则解析
- `bot/evidence_collector.py`：RSS/Atom 证据抓取和评分
- `bot/signal_engine.py`：模型概率、交易方向和 edge 计算
- `bot/risk_engine.py`：市场和信号过滤
- `bot/portfolio_risk.py`：组合级 shadow 风险、敞口和熔断
- `bot/watchlist.py`：watchlist 配置、快照、告警
- `bot/shadow.py`：shadow fill 模拟
- `bot/shadow_replay.py`：shadow PnL 回放
- `bot/backtest_dataset.py`：从 SQLite 和 settlement 文件生成标准回测样本
- `bot/backtest_engine.py`：重放 shadow fill 入场规则和策略过滤
- `bot/backtest_metrics.py`：计算 Brier、log loss、校准桶、PnL 和可靠性状态
- `bot/backtest_reporting.py`：输出 Markdown/JSON backtest 报告
- `bot/reporting.py`：SQLite 报表汇总
- `bot/calibration.py`：按 `model_profile` 汇总 shadow 样本并给出校准建议
- `bot/storage.py`：SQLite 落库
- `data/watchlist.json`：定向监控市场
- `data/evidence_sources.json`：外部证据源
- `data/shadow_settlements.example.json`：shadow 回放的手动平仓/结算示例
- `logs/`：运行输出，包含 JSONL 和 SQLite
- `logs/http_cache.sqlite`：HTTP 响应缓存
- `tests/`：回归测试

## 运行

使用示例数据：

```powershell
python -m bot.main --sample-data data/sample_markets.json
```

扫描 Polymarket 实时市场：

```powershell
python -m bot.main --live --limit 20 --evidence-sources data/evidence_sources.json
```

运行一次 watchlist：

```powershell
python -m bot.main --watchlist data/watchlist.json --evidence-sources data/evidence_sources.json
```

持续运行 watchlist，每 5 分钟跑一次，共 12 轮：

```powershell
python -m bot.main --watchlist data/watchlist.json --evidence-sources data/evidence_sources.json --iterations 12 --poll-seconds 300 --log-file logs/watchlist_snapshots.jsonl --alert-file logs/watchlist_alerts.jsonl --shadow-file logs/shadow_fills.jsonl --db-file logs/watchlist.sqlite
```

`watchlist` 模式默认允许最长 `120` 天到期窗口，可以用 `--watchlist-max-days` 覆盖。普通 `--live` 扫描仍使用 `BotConfig` 里的短窗口。

默认缓存参数：

- `--cache-file logs/http_cache.sqlite`
- `--gamma-cache-seconds 30`
- `--book-cache-seconds 10`
- `--rss-cache-seconds 900`
- `--api-rate-limit-seconds 0.10`
- `--rss-rate-limit-seconds 0.25`

## 输出

JSONL：

- `logs/watchlist_snapshots.jsonl`：每轮市场快照、证据分、模型信号、过滤原因
- `logs/watchlist_alerts.jsonl`：变化告警
- `logs/shadow_fills.jsonl`：满足条件的模拟成交

SQLite：

- `watchlist_snapshots`
- `watchlist_alerts`
- `shadow_fills`
- `evidence_runs`
- `shadow_marks`

`evidence_runs` 会保存证据总分和组件分数：`preheat_score`、`cadence_score`、`partner_score`、`source_reliability`。`signal_reasons_detail` 会写入本次使用的 `model_profile`，便于回放时区分音乐发布、产品发布和 IPO 事件。

简单查看 SQLite 统计：

```powershell
@'
import sqlite3
with sqlite3.connect("logs/watchlist.sqlite") as con:
    for table in ["watchlist_snapshots", "watchlist_alerts", "shadow_fills", "evidence_runs", "shadow_marks"]:
        print(table, con.execute(f"select count(*) from {table}").fetchone()[0])
'@ | python -
```

## Shadow Fill 条件

一条 shadow fill 必须同时满足：

- `market_ok == true`
- `signal_ok == true`
- `model_side == preferred_side`
- 当前对应侧 `ask <= max_entry_price`
- 组合风控允许新增敞口

这意味着 shadow fill 是“当前模型愿意按盘口价模拟买入”的记录，不代表真实订单已经成交。

如果使用默认 `--db-file`，同一 `slug + side` 已经存在 shadow fill 时，不会重复开新的模拟仓。后续每轮会写入 `shadow_marks`，用当前 YES/NO mid 标记已有模拟仓的浮动表现。

## 组合风控

shadow fill 现在会按模拟资金池控制敞口。默认参数：

- `--shadow-bankroll 1000`
- `--shadow-position-risk-pct 0.02`，每笔 shadow fill 默认风险金额为 20
- `--max-total-risk-pct 0.20`
- `--max-market-risk-pct 0.02`
- `--max-event-type-risk-pct 0.08`
- `--circuit-breaker-loss-pct 0.05`
- `--max-open-shadow-positions 10`

组合风控在写入 `shadow_fills` 前执行。若触发总敞口、单市场敞口、事件类型敞口、最大持仓数或亏损熔断，新候选会打印 `shadow_fill_blocked`，但不会写入模拟成交。

## Shadow PnL 回放

按 SQLite 里的 `shadow_fills` 和最新 `shadow_marks` 回放当前未实现盈亏：

```powershell
python -m bot.main --shadow-replay --db-file logs/watchlist.sqlite
```

输出会按 `event_type` 汇总 `total_pnl`、`realized_pnl`、`unrealized_pnl`、`avg_pnl`、`win_rate`，并列出每笔 shadow position。

如果要模拟手动平仓或最终结算，可以传入 JSON：

```powershell
python -m bot.main --shadow-replay --db-file logs/watchlist.sqlite --settlement-file data/shadow_settlements.example.json --replay-json logs/shadow_replay.json
```

结算文件支持两种形式：

- 最终结算：`slug` + `winning_side`，其中 `winning_side` 是 `BUY_YES` 或 `BUY_NO`
- 手动平仓：`slug` + 可选 `side` + `close_price` + `status=closed`

不带 `side` 时，同一个 `slug` 下所有 shadow fill 都会应用该结算记录。

## SQLite 报表

生成终端摘要、Markdown 报表、本地 HTML dashboard 和可选 JSON：

```powershell
python -m bot.main --dashboard-report --db-file logs/watchlist.sqlite --report-file logs/dashboard_report.md --report-html logs/dashboard.html --report-json logs/dashboard_report.json
```

报表包含：

- 按 `event_type` 聚合的 `avg_net_edge`、`max_net_edge`、信号通过数量和平均证据分
- alert reason 计数
- shadow PnL 按事件类型汇总
- backtest summary、profile 校准表和 profile PnL 表
- 组合敞口、未实现 PnL、熔断状态和按事件类型的风险分布
- 最新市场里 net edge 最高的条目

HTML dashboard 是单文件静态页面，生成后可以直接在浏览器打开 `logs/dashboard.html`。`--report-limit` 可以控制明细条数。

如果已经维护了 settlement 文件，dashboard 也可以传入同一个文件，让 shadow PnL 和 backtest summary 优先使用 settlement 目标：

```powershell
python -m bot.main --dashboard-report --db-file logs/watchlist.sqlite --settlement-file data/shadow_settlements.json --report-file logs/dashboard_report.md --report-html logs/dashboard.html --report-json logs/dashboard_report.json
```

## 离线 Backtest

离线 backtest 的目标不是证明模型已经可靠，而是检查当前项目是否能用不含未来信息的数据评估模型。

第一版只使用本地已有数据：

- `watchlist_snapshots`
- `shadow_fills`
- `shadow_marks`
- 可选 `settlement_file`

生成 Markdown 和 JSON 报告：

```powershell
python -m bot.main --backtest --db-file logs/watchlist.sqlite --backtest-report logs/backtest_report.md --backtest-json logs/backtest_report.json
```

如果有手动平仓或最终结算文件，应传入 `--settlement-file`，报告会优先使用 `settlement_file`，其次使用 `latest_mark`，最后才回退到 `snapshot_mid`：

```powershell
python -m bot.main --backtest --db-file logs/watchlist.sqlite --settlement-file data/shadow_settlements.example.json --backtest-report logs/backtest_report.md --backtest-json logs/backtest_report.json
```

在把 settlement 文件用于回测前，先运行校验命令：

```powershell
python -m bot.main --validate-settlements --db-file logs/watchlist.sqlite --settlement-file data/shadow_settlements.json --settlement-validation-json logs/settlement_validation.json
```

校验会检查：

- settlement 文件覆盖了多少条 `shadow_fills`
- 是否存在重复的 `slug + side`
- settlement slug 或 side 是否无法匹配本地 shadow fill
- `winning_side` 和 `close_price` 是否互相冲突
- 哪些 shadow fill 仍未 settlement

可选过滤：

```powershell
python -m bot.main --backtest --db-file logs/watchlist.sqlite --backtest-profile music_release --backtest-event-type content_release --backtest-from 2026-04-01 --backtest-to 2026-06-30
```

报告包含：

- 样本数量、settled samples、mark-only samples、shadow fills
- settled sample coverage
- target source 分布，明确区分 `settlement_file`、`latest_mark`、`snapshot_mid`
- Brier score、market mid Brier score、log loss、calibration error
- profile 级校准表
- profile/event/platform/side 级 PnL
- net edge 和 evidence score 分桶表现
- 亏损样本列表
- 样本不足警告和是否可用于调参的建议

当前判定规则保持保守：

- settled samples 少于 30 时，状态为 `insufficient`
- 每个 `model_profile` 少于 30 条 settled samples 时，不建议自动调参
- 每个 `model_profile` 少于 100 条 settled samples 时，不认为模型已被证明可靠
- `latest_mark` 和 `snapshot_mid` 只能用于诊断，不能当作最终预测能力证明

## Model Profile 校准

第一步优化已落地为离线校准报告。报告会从 SQLite 的 `shadow_fills` 读取入场样本，关联当时的 `watchlist_snapshots` 特征，并按 `model_profile` 汇总：

- 平均 `p_model`、目标 YES 概率、校准误差和 Brier score
- 目标来源计数：优先 `settlement_file`，其次 `latest_mark`，最后回退到 `snapshot_yes_mid`
- 样本量足够时给出 `base_logit` 和 `evidence_weight` 建议
- 样本量不足时只输出诊断，不建议直接改 live 参数

生成校准报告：

```powershell
python -m bot.main --calibration-report --db-file logs/watchlist.sqlite --calibration-file logs/calibration_report.md --calibration-json logs/calibration_report.json
```

如果已有手动平仓或最终结算文件，应一起传入，让校准优先使用更可信的目标：

```powershell
python -m bot.main --calibration-report --db-file logs/watchlist.sqlite --settlement-file data/shadow_settlements.example.json --calibration-json logs/calibration_report.json
```

`--calibration-min-samples` 控制每个 `model_profile` 至少需要多少条 shadow 样本才输出参数建议，默认是 `5`。当目标来源不是 `settlement_file` 时，建议只把报告当作临时漂移监控，不直接改模型权重。

## 当前 Watchlist

当前配置在 `data/watchlist.json`：

- `GPT-6 before GTA VI`
- `Playboi Carti new album before GTA VI`
- `Rihanna new album before GTA VI`
- `OpenAI no IPO by Dec 31 2026`
- `Tesla Optimus release by Jun 30 2026`
- `Apple cellular MacBook by Jun 30`

其中 Tesla/Apple 当前更多是证据监控项。因为新闻和传闻容易把“研发/生产进展”误判成“规则意义上的 release”，shadow fill 还要求模型方向必须和 `preferred_side` 一致。

## 测试

```powershell
python -m unittest discover -s tests
```

当前测试覆盖：

- API retry
- BUY_NO edge 计算
- outcome/token 映射
- market parser
- risk spread 过滤
- watchlist alert diff
- shadow fill 过滤条件
- shadow PnL 回放、平仓/结算和按事件类型统计
- SQLite 报表聚合和本地 HTML dashboard 输出
- 组合级 shadow 风险和熔断过滤
- SQLite evidence/mark 写入
- HTTP cache 和 API retry
- model_profile shadow 样本校准报告
- 离线 backtest dataset、entry replay、校准桶、PnL 聚合和样本不足状态
- settlement 文件校验、覆盖率、重复/冲突记录检测

## 配置说明

`BotConfig` 默认值在 `bot/config.py`：

- `min_days_to_expiry`
- `max_days_to_expiry`
- `min_volume`
- `max_spread`
- `fee_buffer`
- `uncertainty_buffer`
- `min_net_edge`

`watchlist` 模式会覆盖 `max_days_to_expiry`，默认使用 `--watchlist-max-days 120`。

## 当前限制

- 没有真实下单、撤单、成交同步或持仓管理
- 概率模型仍是启发式规则模型，虽然已按事件类型拆分参数，但还没有历史校准
- 外部证据源依赖 RSS/Google News RSS，存在噪音和延迟
- 产品发布类市场容易把传闻误判为有效证据
- 当前 settlement 样本不足，backtest 主要是诊断机制，不是模型可靠性证明
- 只有进程内限速，还没有跨进程限速治理
- 还没有完整断点恢复和订单生命周期状态机
- 组合风控仍只覆盖 shadow fill，尚未接入真实订单生命周期

## 下一步

优先级建议按“先验证，再扩张，最后考虑真实下单”推进。

### 1. 数据质量和 settlement 积累

- 为每个 shadow fill 建立人工 settlement 流程，定期维护 `data/shadow_settlements.json`
- 在 dashboard 中突出 `settlement_file` 覆盖率，避免把 `latest_mark` 误当最终结果
- 增加 settlement 校验脚本，检查 slug、side、winning_side、close_price 是否互相冲突
- 定期导出 backtest JSON，保存关键时间点的评估快照，便于比较模型迭代前后变化

### 2. Backtest 可信度增强

- 增加 walk-forward 切分，比较不同时间窗口里的 PnL 和校准是否一致
- 增加 market mid baseline、随机入场 baseline 和“只按 target band 入场”baseline
- 把 `net_edge`、`evidence_score`、`spread`、`days_to_expiry` 做组合分桶，找出真正有效和无效的过滤条件
- 对 profile 少于 30 条 settled samples 的报告只显示诊断，不显示参数建议

### 3. Evidence 证据层升级

- 为音乐、产品、IPO、AI 发布等类型维护不同的证据源白名单
- 引入 source reliability 评分，把官方公告、公司博客、监管文件、主流媒体和传闻源分层
- 对“产品研发进展”和“规则意义上的 release”做更严格区分，降低产品发布误报
- 保存证据原文摘要和 URL，保证每次 shadow fill 都能追溯当时依据

### 4. 模型和参数迭代

- 等每个 `model_profile` 至少有 30 条 settled samples 后，再考虑调整 `base_logit`、`evidence_weight` 和组件权重
- 为 `music_release`、`product_release`、`ipo_event` 分别建立可靠性阈值，不共用一个全局阈值
- 比较 `p_model` 与市场 mid 的 Brier score，只有稳定优于 baseline 时才扩大 shadow 规模
- 把参数变更记录到单独 changelog，避免后续回测混淆模型版本

### 5. Dashboard 和运维体验

- 在 HTML dashboard 增加日期、profile、event_type、target_source 过滤
- 增加 equity curve、drawdown curve、calibration reliability chart
- 增加 watchlist 健康状态：API 错误率、缓存命中率、RSS 延迟、最近成功轮询时间
- 增加一键生成日报/周报的 Markdown 输出

### 6. 真实下单前置条件

真实下单应放在验证机制稳定之后。至少满足：

- settled samples 达到项目设定门槛，且多个窗口没有明显退化
- shadow PnL、校准和最大回撤稳定优于 baseline
- 订单生命周期状态机、撤单、成交同步、持仓同步和异常恢复已经测试
- 组合风控覆盖真实仓位，而不只是 shadow fill

之后再单独实现 CLOB 认证、签名、maker-only 下单、撤单、成交同步和真实仓位风控。
