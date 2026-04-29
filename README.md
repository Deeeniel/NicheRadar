# NicheRadar

A shadow orderbook monitoring bot targeting niche event markets on Polymarket.

The current project does not execute real orders; it focuses solely on reading public markets, scoring external evidence, generating signals, filtering for risk, monitoring a targeted watchlist, triggering alerts for changes, storing data in SQLite, and simulating shadow fills.

## Objectives

This bot does not pursue high-frequency arbitrage, nor does it engage in BTC 5m options, tail-risk lotteries, whale copy-trading, or settlement harvesting. The current strategic focus is:

* Focus on niche event markets with clear rules and externally verifiable evidence.
* Prioritize markets related to content releases, album drops, AI/company events, and product launches.
* Only record shadow fills when the model direction, risk control, target price band, and orderbook price are simultaneously satisfied.
* Ensure all signals and simulated executions are auditable and replayable.

## Current Capabilities

* Pull market metadata from the Polymarket Gamma API.
* Read YES/NO orderbooks from the Polymarket CLOB API.
* Explicitly map YES/NO tokens based on `outcomes` and `clobTokenIds`.
* Parse common market types: `content_release`, `announcement`, `ipo_event`, `social_activity`.
* Fetch external evidence from RSS/Atom/Google News RSS feeds.
* Generate `p_model`, direction, edge, net edge, and maximum entry price.
* Split model profiles, baseline probabilities, and evidence weights by music releases, product launches, and IPO events.
* Apply risk filters based on trading volume, time to expiration, spread, confidence level, and edge.
* Perform targeted polling, append JSONL logs, and write to SQLite for the watchlist.
* Record alerts when prices enter target bands, signals become available, or evidence scores jump.
* Record shadow fills that meet criteria without triggering real orders.
* Write marks for existing shadow fills based on subsequent snapshots to observe floating performance.
* Replay shadow PnL, supporting statistics based on the latest mark, manual closing price, or final settlement direction.
* Generate SQLite reports and a local HTML dashboard to summarize edges, alerts, shadow fills, and PnL performance.
* Implement portfolio-level exposure control for shadow fills, triggering circuit breakers upon losses or excessive positions.
* Generate `model_profile` calibration reports based on shadow fills, marks, and optional settlement files.
* Generate offline backtest reports based on local SQLite snapshots, shadow fills, marks, and settlement files.
* Display backtest summaries, profile calibration, and profile PnL within the dashboard.
* Include basic retry/backoff mechanisms for Polymarket API and RSS fetching.
* Support SQLite HTTP caching and in-process request rate limiting for Gamma/CLOB/RSS.
* Ensure a single slug or market read failure does not interrupt the entire watchlist cycle.
* Provide minimum regression testing.

## Directory Structure

* `bot/api.py`: Public read API client for Polymarket.
* `bot/market_scanner.py`: Gamma market row conversion, YES/NO orderbook completion.
* `bot/market_parser.py`: Market title/rule parsing.
* `bot/evidence_collector.py`: RSS/Atom evidence fetching and scoring.
* `bot/signal_engine.py`: Model probability, trading direction, and edge calculations.
* `bot/risk_engine.py`: Market and signal filtering.
* `bot/portfolio_risk.py`: Portfolio-level shadow risk, exposure, and circuit breakers.
* `bot/watchlist.py`: Watchlist configuration, snapshots, and alerts.
* `bot/shadow.py`: Shadow fill simulation.
* `bot/shadow_replay.py`: Shadow PnL replay.
* `bot/backtest_dataset.py`: Standard backtest sample generation from SQLite and settlement files.
* `bot/backtest_engine.py`: Replay of shadow fill entry rules and strategy filtering.
* `bot/backtest_metrics.py`: Calculation of Brier score, log loss, calibration buckets, PnL, and reliability status.
* `bot/backtest_reporting.py`: Markdown/JSON backtest report generation.
* `bot/reporting.py`: SQLite report summarization.
* `bot/calibration.py`: Aggregation of shadow samples by `model_profile` with calibration recommendations.
* `bot/storage.py`: SQLite data persistence.
* `data/watchlist.json`: Targeted monitoring markets.
* `data/evidence_sources.json`: External evidence sources.
* `data/shadow_settlements.example.json`: Example of manual closing/settlement for shadow replays.
* `logs/`: Runtime outputs, including JSONL and SQLite databases.
* `logs/http_cache.sqlite`: HTTP response cache.
* `tests/`: Regression tests.

## Running

Using sample data:
```powershell
python -m bot.main --sample-data data/sample_markets.json
```

Scanning live Polymarket markets:
```powershell
python -m bot.main --live --limit 20 --evidence-sources data/evidence_sources.json
```

Running a watchlist once:
```powershell
python -m bot.main --watchlist data/watchlist.json --evidence-sources data/evidence_sources.json
```

Running a watchlist continuously (every 5 minutes for 12 iterations):
```powershell
python -m bot.main --watchlist data/watchlist.json --evidence-sources data/evidence_sources.json --iterations 12 --poll-seconds 300 --log-file logs/watchlist_snapshots.jsonl --alert-file logs/watchlist_alerts.jsonl --shadow-file logs/shadow_fills.jsonl --db-file logs/watchlist.sqlite
```

The `watchlist` mode allows a maximum expiry window of `120` days by default, which can be overridden using `--watchlist-max-days`. The standard `--live` scan still utilizes the short window defined in `BotConfig`.

Default cache parameters:

* `--cache-file logs/http_cache.sqlite`
* `--gamma-cache-seconds 30`
* `--book-cache-seconds 10`
* `--rss-cache-seconds 900`
* `--api-rate-limit-seconds 0.10`
* `--rss-rate-limit-seconds 0.25`

## Output

JSONL:

* `logs/watchlist_snapshots.jsonl`: Market snapshots, evidence scores, model signals, and filter reasons per iteration.
* `logs/watchlist_alerts.jsonl`: Change alerts.
* `logs/shadow_fills.jsonl`: Simulated executions meeting the criteria.

SQLite:

* `watchlist_snapshots`
* `watchlist_alerts`
* `shadow_fills`
* `evidence_runs`
* `shadow_marks`

`evidence_runs` stores the total evidence score and component scores: `preheat_score`, `cadence_score`, `partner_score`, and `source_reliability`. `signal_reasons_detail` logs the `model_profile` used during the run, facilitating the distinction between music releases, product launches, and IPO events during replays.

Quick check of SQLite statistics:
```powershell
@'
import sqlite3
with sqlite3.connect("logs/watchlist.sqlite") as con:
    for table in ["watchlist_snapshots", "watchlist_alerts", "shadow_fills", "evidence_runs", "shadow_marks"]:
        print(table, con.execute(f"select count(*) from {table}").fetchone()[0])
'@ | python -
```

## Shadow Fill Conditions

A shadow fill must simultaneously satisfy:

* `market_ok == true`
* `signal_ok == true`
* `model_side == preferred_side`
* Current `ask` on the corresponding side `<= max_entry_price`
* Portfolio risk control permits new exposure

This implies a shadow fill is a record indicating "the current model is willing to simulate a buy at the orderbook price", and does not represent an actual executed order.

If the default `--db-file` is used, a new simulated position will not be opened if a shadow fill already exists for the same `slug + side`. Subsequent iterations will write to `shadow_marks`, using the current YES/NO mid to track the floating performance of existing simulated positions.

## Portfolio Risk Control

Shadow fills are now exposure-controlled against a simulated fund pool. Default parameters:

* `--shadow-bankroll 1000`
* `--shadow-position-risk-pct 0.02`, setting the default risk amount per shadow fill to 20.
* `--max-total-risk-pct 0.20`
* `--max-market-risk-pct 0.02`
* `--max-event-type-risk-pct 0.08`
* `--circuit-breaker-loss-pct 0.05`
* `--max-open-shadow-positions 10`

Portfolio risk control is executed prior to writing to `shadow_fills`. If a candidate triggers total exposure, single-market exposure, event type exposure, max position count, or loss circuit breakers, it will print `shadow_fill_blocked` without recording the simulated execution.

## Shadow PnL Replay

Replay current unrealized PnL based on `shadow_fills` and the latest `shadow_marks` in SQLite:
```powershell
python -m bot.main --shadow-replay --db-file logs/watchlist.sqlite
```

The output will aggregate `total_pnl`, `realized_pnl`, `unrealized_pnl`, `avg_pnl`, and `win_rate` by `event_type`, listing each shadow position.

To simulate manual closing or final settlement, pass a JSON file:
```powershell
python -m bot.main --shadow-replay --db-file logs/watchlist.sqlite --settlement-file data/shadow_settlements.example.json --replay-json logs/shadow_replay.json
```

The settlement file supports two formats:

* Final settlement: `slug` + `winning_side`, where `winning_side` is either `BUY_YES` or `BUY_NO`.
* Manual closing: `slug` + optional `side` + `close_price` + `status=closed`.

If `side` is omitted, the settlement record applies to all shadow fills under the same `slug`.

## SQLite Reporting

Generate terminal summaries, Markdown reports, a local HTML dashboard, and optional JSON data:
```powershell
python -m bot.main --dashboard-report --db-file logs/watchlist.sqlite --report-file logs/dashboard_report.md --report-html logs/dashboard.html --report-json logs/dashboard_report.json
```

Reports include:

* `avg_net_edge`, `max_net_edge`, number of passed signals, and average evidence score aggregated by `event_type`.
* Alert reason counts.
* Shadow PnL summarized by event type.
* Backtest summaries, profile calibration tables, and profile PnL tables.
* Portfolio exposure, unrealized PnL, circuit breaker status, and risk distribution by event type.
* Top entries with the highest net edge in the latest markets.

The HTML dashboard is a single static page; once generated, open `logs/dashboard.html` directly in a browser. The `--report-limit` parameter controls the number of detailed rows.

If a settlement file is maintained, it can be passed to the dashboard so that the shadow PnL and backtest summary prioritize the settlement targets:
```powershell
python -m bot.main --dashboard-report --db-file logs/watchlist.sqlite --settlement-file data/shadow_settlements.json --report-file logs/dashboard_report.md --report-html logs/dashboard.html --report-json logs/dashboard_report.json
```

## Offline Backtest

The goal of the offline backtest is not to prove the model is already reliable, but to verify whether the current project can evaluate the model using data free of future information.

The initial version solely uses existing local data:

* `watchlist_snapshots`
* `shadow_fills`
* `shadow_marks`
* Optional `settlement_file`

Generate Markdown and JSON reports:
```powershell
python -m bot.main --backtest --db-file logs/watchlist.sqlite --backtest-report logs/backtest_report.md --backtest-json logs/backtest_report.json
```

If a manual closing or final settlement file exists, it should be passed via `--settlement-file`. The report prioritizes the `settlement_file`, falls back to `latest_mark`, and finally defaults to `snapshot_mid`:
```powershell
python -m bot.main --backtest --db-file logs/watchlist.sqlite --settlement-file data/shadow_settlements.example.json --backtest-report logs/backtest_report.md --backtest-json logs/backtest_report.json
```

Before using a settlement file for backtesting, run the validation command:
```powershell
python -m bot.main --validate-settlements --db-file logs/watchlist.sqlite --settlement-file data/shadow_settlements.json --settlement-validation-json logs/settlement_validation.json
```

Validation checks:

* How many `shadow_fills` are covered by the settlement file.
* Whether duplicate `slug + side` entries exist.
* Whether a settlement slug or side fails to match any local shadow fill.
* Whether `winning_side` and `close_price` contradict each other.
* Which shadow fills remain unsettled.

Optional filtering:
```powershell
python -m bot.main --backtest --db-file logs/watchlist.sqlite --backtest-profile music_release --backtest-event-type content_release --backtest-from 2026-04-01 --backtest-to 2026-06-30
```

The report contains:

* Sample count, settled samples, mark-only samples, and shadow fills.
* Settled sample coverage.
* Target source distribution, clearly distinguishing between `settlement_file`, `latest_mark`, and `snapshot_mid`.
* Brier score, market mid Brier score, log loss, and calibration error.
* Profile-level calibration tables.
* PnL at the profile/event/platform/side levels.
* Bucket performance for net edge and evidence scores.
* List of loss-making samples.
* Insufficient sample warnings and recommendations on whether tuning is viable.

Current evaluation rules remain conservative:

* If settled samples are fewer than 30, the status is `insufficient`.
* Automatic parameter tuning is not recommended when a `model_profile` has fewer than 30 settled samples.
* A model is not considered proven reliable until a `model_profile` achieves at least 100 settled samples.
* `latest_mark` and `snapshot_mid` should only be used for diagnostics, not as definitive proof of predictive capability.

## Model Profile Calibration

The first optimization step is implemented as an offline calibration report. The report reads entry samples from `shadow_fills` in SQLite, links them with the concurrent `watchlist_snapshots` features, and aggregates them by `model_profile`:

* Average `p_model`, target YES probability, calibration error, and Brier score.
* Target source counts: prioritizes `settlement_file`, then `latest_mark`, and falls back to `snapshot_yes_mid`.
* Provides `base_logit` and `evidence_weight` recommendations when sample sizes are sufficient.
* Outputs only diagnostics without direct live parameter changes when sample sizes are insufficient.

Generate the calibration report:
```powershell
python -m bot.main --calibration-report --db-file logs/watchlist.sqlite --calibration-file logs/calibration_report.md --calibration-json logs/calibration_report.json
```

If manual closing or final settlement files exist, they should be passed together to prioritize highly credible targets during calibration:
```powershell
python -m bot.main --calibration-report --db-file logs/watchlist.sqlite --settlement-file data/shadow_settlements.example.json --calibration-json logs/calibration_report.json
```

`--calibration-min-samples` determines the minimum number of shadow samples required per `model_profile` to output parameter recommendations (default is `5`). When the target source is not a `settlement_file`, it is advised to treat the report as a temporary drift monitor and refrain from directly altering model weights.

## Current Watchlist

Current configuration in `data/watchlist.json`:

* `GPT-6 before GTA VI`
* `Playboi Carti new album before GTA VI`
* `Rihanna new album before GTA VI`
* `OpenAI no IPO by Dec 31 2026`
* `Tesla Optimus release by Jun 30 2026`
* `Apple cellular MacBook by Jun 30`

Currently, Tesla/Apple are primarily evidence monitoring items. Because news and rumors frequently misclassify "R&D/production progress" as a "release" in the rule context, shadow fills also demand that the model direction matches the `preferred_side`.

## Testing

```powershell
python -m unittest discover -s tests
```

Current test coverage includes:

* API retry
* BUY_NO edge calculation
* Outcome/token mapping
* Market parser
* Risk spread filtering
* Watchlist alert diffs
* Shadow fill filter conditions
* Shadow PnL replay, closing/settlement, and event type statistics
* SQLite report aggregation and local HTML dashboard outputs
* Portfolio-level shadow risk and circuit breaker filters
* SQLite evidence/mark writing
* HTTP cache and API retries
* `model_profile` shadow sample calibration reports
* Offline backtest dataset, entry replays, calibration buckets, PnL aggregation, and insufficient sample statuses
* Settlement file validation, coverage checks, and detection of duplicate/conflicting records

## Configuration Details

Default `BotConfig` values are in `bot/config.py`:

* `min_days_to_expiry`
* `max_days_to_expiry`
* `min_volume`
* `max_spread`
* `fee_buffer`
* `uncertainty_buffer`
* `min_net_edge`

The `watchlist` mode overrides `max_days_to_expiry`, defaulting to `--watchlist-max-days 120`.

## Current Limitations

* Lack of real order placement, cancellations, execution synchronization, and position management.
* The probability model remains a heuristic rule-based model; while parameters are split by event type, historical calibration is pending.
* External evidence sources rely on RSS/Google News RSS, which have noise and latency.
* Product launch markets are prone to misjudging rumors as valid evidence.
* Due to insufficient settlement samples, the backtest currently acts as a diagnostic mechanism, not proof of model reliability.
* Rate limiting is only in-process, lacking cross-process rate limit governance.
* Full breakpoint recovery and an order lifecycle state machine are not yet implemented.
* Portfolio risk control only covers shadow fills and is not yet integrated with real order lifecycles.

## Next Steps

It is recommended to proceed by "first validating, then expanding, and finally considering real orders."

### 1. Data Quality and Settlement Accumulation

* Establish a manual settlement process for every shadow fill and regularly maintain `data/shadow_settlements.json`.
* Highlight `settlement_file` coverage in the dashboard to prevent mistaking `latest_mark` as the final outcome.
* Add a settlement validation script to check for conflicting slug, side, winning_side, and close_price.
* Periodically export backtest JSONs to save evaluation snapshots at key timestamps, aiding in the comparison of pre- and post-iteration model changes.

### 2. Backtest Credibility Enhancements

* Introduce walk-forward splitting to compare PnL and calibration consistency across different time windows.
* Implement a market mid baseline, a random entry baseline, and a "target band entry only" baseline.
* Create combinatorial buckets for `net_edge`, `evidence_score`, `spread`, and `days_to_expiry` to identify truly effective versus ineffective filters.
* Show only diagnostics (no parameter recommendations) for profiles with fewer than 30 settled samples.

### 3. Evidence Layer Upgrades

* Maintain separate evidence source allowlists for music, products, IPOs, and AI releases.
* Introduce source reliability scoring to categorize official announcements, corporate blogs, regulatory filings, mainstream media, and rumor sources.
* Enforce stricter differentiation between "R&D progress" and a "release in the rule context" to reduce product launch false positives.
* Save original evidence summaries and URLs to ensure traceability of the basis for every shadow fill.

### 4. Model and Parameter Iteration

* Delay adjusting `base_logit`, `evidence_weight`, and component weights until each `model_profile` reaches at least 30 settled samples.
* Establish distinct reliability thresholds for `music_release`, `product_release`, and `ipo_event`, moving away from a shared global threshold.
* Compare the Brier score of `p_model` against the market mid; scale up shadow sizes only when consistently outperforming the baseline.
* Log parameter changes to a separate changelog to prevent confusion of model versions during future backtesting.

### 5. Dashboard and Operations Experience

* Add date, profile, event_type, and target_source filters to the HTML dashboard.
* Add equity curves, drawdown curves, and calibration reliability charts.
* Display watchlist health statuses: API error rates, cache hit rates, RSS latency, and last successful poll times.
* Enable one-click Markdown output for daily/weekly reports.

### 6. Prerequisites for Real Orders

Real order execution should only commence after validation mechanisms are stable. Minimum requirements:

* Settled samples reach the project's target threshold without noticeable degradation across multiple windows.
* Shadow PnL, calibration, and max drawdown stably outperform the baseline.
* The order lifecycle state machine, order cancellation, execution synchronization, position synchronization, and exception recovery are fully tested.
* Portfolio risk control extends to real positions, not just shadow fills.

Subsequently, proceed to independently implement CLOB authentication, signing, maker-only order placement, order cancellation, execution sync, and real position risk control.
