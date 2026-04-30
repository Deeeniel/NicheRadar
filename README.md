# NicheRadar

NicheRadar is a shadow-market monitoring bot for niche Polymarket event markets.

It does not place real orders. The project focuses on:

- reading public markets
- parsing rules and external evidence
- generating signals and simulated fills
- writing snapshots, alerts, fills, and marks to SQLite
- replaying and validating shadow PnL
- producing dashboard, calibration, backtest, and settlement validation reports

## What It Does

- Pulls market metadata from the Polymarket Gamma API.
- Loads YES/NO orderbooks from the Polymarket CLOB API.
- Parses event types such as content releases, announcements, IPO events, and related niche markets.
- Scores external evidence from RSS / Atom / news-style sources.
- Produces `p_model`, edge, net edge, confidence, and a max entry price.
- Filters signals using market, signal, and portfolio risk rules.
- Runs targeted watchlists with JSONL logging and SQLite persistence.
- Writes shadow fills only when all entry conditions are met.
- Marks existing shadow fills with subsequent snapshots.
- Replays shadow PnL using latest marks or settlement files.
- Generates dashboard, calibration, backtest, and settlement validation reports.
- Bootstraps report commands on fresh databases before reading.

## Repository Layout

- [bot/main.py](bot/main.py): CLI entrypoint.
- [bot/app.py](bot/app.py): Application service layer and CLI orchestration.
- [bot/cli.py](bot/cli.py): CLI argument definitions.
- [bot/report_commands.py](bot/report_commands.py): Report command routing.
- [bot/watchlist_runner.py](bot/watchlist_runner.py): Watchlist polling loop.
- [bot/report_data.py](bot/report_data.py): Dashboard data loading and reuse layer.
- [bot/storage.py](bot/storage.py): SQLite persistence and schema bootstrap.
- [bot/positions.py](bot/positions.py): Position reconstruction from fills, marks, and settlements.
- [bot/risk_manager.py](bot/risk_manager.py): Signal and portfolio risk filtering.
- [bot/reporting.py](bot/reporting.py): Dashboard summarization and rendering.
- [bot/backtest/](bot/backtest): Offline backtest, calibration, replay, metrics, and settlement validation.
- [data/watchlist.json](data/watchlist.json): Example watchlist.
- [data/evidence_sources.json](data/evidence_sources.json): Evidence source registry.
- [tests/](tests): Regression tests.

## Quick Start

Run sample data:

```powershell
python -m bot.main --sample-data data/sample_markets.json
```

Run live market scanning:

```powershell
python -m bot.main --live --limit 20 --evidence-sources data/evidence_sources.json
```

Run a watchlist once:

```powershell
python -m bot.main --watchlist data/watchlist.json --evidence-sources data/evidence_sources.json
```

Run a watchlist continuously:

```powershell
python -m bot.main --watchlist data/watchlist.json --evidence-sources data/evidence_sources.json --iterations 12 --poll-seconds 300 --log-file logs/watchlist_snapshots.jsonl --alert-file logs/watchlist_alerts.jsonl --shadow-file logs/shadow_fills.jsonl --db-file logs/watchlist.sqlite
```

## Reports

Generate the dashboard:

```powershell
python -m bot.main --dashboard-report --db-file logs/watchlist.sqlite --report-file logs/dashboard_report.md --report-html logs/dashboard.html --report-json logs/dashboard_report.json
```

Replay shadow PnL:

```powershell
python -m bot.main --shadow-replay --db-file logs/watchlist.sqlite
```

Validate settlements:

```powershell
python -m bot.main --validate-settlements --db-file logs/watchlist.sqlite --settlement-file data/shadow_settlements.json --settlement-validation-json logs/settlement_validation.json
```

Run offline backtests:

```powershell
python -m bot.main --backtest --db-file logs/watchlist.sqlite --backtest-report logs/backtest_report.md --backtest-json logs/backtest_report.json
```

Build a calibration report:

```powershell
python -m bot.main --calibration-report --db-file logs/watchlist.sqlite --calibration-file logs/calibration_report.md --calibration-json logs/calibration_report.json
```

Report commands initialize the SQLite schema automatically, so they work on fresh database paths as well.

## Output Artifacts

JSONL:

- `logs/watchlist_snapshots.jsonl`
- `logs/watchlist_alerts.jsonl`
- `logs/shadow_fills.jsonl`

SQLite tables:

- `watchlist_snapshots`
- `watchlist_alerts`
- `shadow_fills`
- `evidence_runs`
- `shadow_marks`

The database is also used for:

- replay summaries
- portfolio risk state
- calibration samples
- backtest samples

## Risk Model

Shadow fills must satisfy all of the following:

- `market_ok == true`
- `signal_ok == true`
- `model_side == preferred_side`
- the relevant ask price is at or below `max_entry_price`
- portfolio risk rules permit the new exposure

Portfolio control includes:

- bankroll fraction per fill
- total exposure limit
- per-market exposure limit
- per-event-type exposure limit
- maximum number of open shadow positions
- circuit breaker behavior on losses

If a candidate is blocked, the watchlist runner prints a blocking reason instead of writing a fill.

## Backtest and Validation

Backtest samples are derived from local SQLite history and can use one of three target sources:

- `settlement_file`
- `latest_mark`
- `snapshot_mid`

Settlement validation checks:

- settlement coverage over shadow fills
- duplicate settlement rows
- unknown slugs or sides
- close-price and winning-side conflicts
- per-slug coverage summaries

## Testing

Run the full regression suite:

```powershell
python -m unittest discover -s tests -q
```

The current test suite covers:

- API retry behavior
- market parsing and token mapping
- risk filtering
- watchlist alerts and fills
- shadow replay and settlement handling
- dashboard/report output
- portfolio risk enforcement
- SQLite persistence and compatibility behavior
- calibration, backtest, and settlement validation
- fresh-database report command behavior

## Limitations

- The bot does not place or manage real orders.
- Rate limiting is still in-process, not cross-process.
- External evidence sources are still noisy and latency-sensitive.
- Portfolio risk is currently only applied to shadow fills, not real positions.

## Next Work

The codebase currently focuses on monitoring, simulation, and reporting. The remaining higher-risk future step is real-order execution, which would require:

- authenticated CLOB access
- maker-only order placement
- execution synchronization
- cancellation handling
- real position state management
- real-position risk control

