# Pickfair - Repository Radiography

Questo documento serve a dare all’assistente AI una radiografia strutturale del repository.  
Il messaggio chiave è semplice:

**il repo è grande, stratificato, pieno di test e non va trattato come un piccolo progetto toy.**

---

## Root overview

### File root principali
- `.bandit`
- `.coveragerc`
- `.editorconfig`
- `.gitignore`
- `.ruff.toml`
- `AVVIA.bat`
- `CONTRIBUTING.md`
- `Makefile`
- `Pickfair.spec`
- `README.txt`
- `auto_throttle.py`
- `auto_updater.py`
- `automation_engine.py`
- `automation_optimizer.py`
- `betfair_client.py`
- `build.bat`
- `build.py`
- `circuit_breaker.py`
- `database.py`
- `devops_update.txt`
- `dutching.py`
- `dutching_cache.py`
- `dutching_state.py`
- `dutching_ui.py`
- `executor_manager.py`
- `goal_engine_pro.py`
- `main.py`
- `market_tracker.py`
- `market_validator.py`
- `mypy.ini`
- `order_manager.py`
- `plugin_manager.py`
- `plugin_runner.py`
- `pnl_cache.py`
- `pnl_engine.py`
- `pyproject.toml`
- `pytest.ini`
- `repo_update_engine.py`
- `requirements-dev.txt`
- `requirements.txt`
- `safe_mode.py`
- `safety_logger.py`
- `shutdown_manager.py`
- `simulation_broker.py`
- `simulation_speed.py`
- `telegram_listener.py`
- `telegram_sender.py`
- `theme.py`
- `tick_dispatcher.py`
- `tick_storage.py`
- `trading_config.py`
- `tree_manager.py`
- `ui_optimizer.py`
- `ui_queue.py`
- `uv.lock`

---

## Directory map

### `.github/`
Contiene:
- workflow CI/CD
- script di audit
- script AI reasoning
- script di supporto repository

#### `.github/scripts/`
- `ai_reasoning_layer.py`
- `build_priority_fix_order.py`
- `check_per_file_coverage.py`
- `generate_repo_autopsy.py`
- `repo_autopsy.py`
- `repo_ultra_audit_narrative.py`

#### `.github/workflows/`
Workflow numerosi e stratificati:
- `ai-guardrails.yml`
- `build-license-generator.yml`
- `build.yml`
- `pickfair_ci.yml`
- `pickfair_logs.yml`
- `pickfair_ultra_ci.yml`
- `repo-update.yml`
- `repo_api_report_v4.yml`
- `repo_autopsy.yml`
- `repo_forensics.yml`
- `repo_ultra_audit_narrative.yml`
- `run_tests.yml`
- `system_validation.yml`
- `test_quality.yml`
- `tests.yml`

---

### `ai/`
Motori AI/quant:
- `ai_guardrail.py`
- `ai_pattern_engine.py`
- `wom_engine.py`

---

### `app_modules/`
Moduli UI applicativi:
- `betting_module.py`
- `monitoring_module.py`
- `simulation_module.py`
- `streaming_module.py`
- `telegram_module.py`
- `ui_module.py`

---

### `controllers/`
Controller applicativi:
- `dutching_controller.py`
- `telegram_controller.py`

---

### `core/`
Core HFT / OMS:
- `async_db_writer.py`
- `event_bus.py`
- `fast_analytics.py`
- `perf_counters.py`
- `risk_middleware.py`
- `safety_layer.py`
- `tick_ring_buffer.py`
- `trading_engine.py`

---

### `docs/`
Documentazione tecnica:
- `ARCHITECTURE.md`
- `FAILURE_MODES.md`
- `PAYLOAD_CONTRACTS.md`
- `PERFORMANCE_TARGETS.md`
- `TESTING_STRATEGY.md`

---

### `guardrails/`
Specifiche e snapshot:
- `allowed_dependencies.json`
- `allowed_files.json`
- `allowed_scope_files.json`
- `critical_modules.json`
- `guard_config.json`
- `guard_probes.py`
- `public_api_snapshot.json`
- `runtime_smoke_specs.json`
- `semantic_specs.json`

---

### `scripts/`
Script di supporto audit / repo:
- `check_architecture_rules.py`
- `check_contract_snapshots.py`
- `extract_failure_context.py`
- `find_shallow_tests.py`
- `generate_fix_backlog.py`
- `generate_fix_from_logs.py`
- `list_top_shallow_tests.py`
- `prioritize_test_cleanup.py`
- `repo_api_report_v4.py`
- `run_targeted_tests.py`

---

### `tests/`
Cartella enorme, parte del contratto del repository.

#### `tests/contracts/`
- `test_payload_snapshots.py`

#### `tests/fixtures/`
- `dutching_inputs.py`
- `market_ticks.py`
- `order_responses.py`
- `system_payloads.py`
- `telegram_messages.py`

#### `tests/guardrails/`
- `test_contract_snapshot.py`
- `test_impact_analysis.py`
- `test_import_smoke.py`
- `test_mutation_probe_strength.py`
- `test_no_new_dependencies.py`
- `test_public_api_matches_snapshot.py`
- `test_reasoning_guard_smoke.py`
- `test_scope_lock.py`

#### Test suite generale
Il repository contiene una suite monumentale:
- database
- dutching
- event bus
- executor manager
- telegram
- pnl
- plugin
- safe mode
- shutdown
- simulation
- trading engine
- tick pipeline
- wom
- market tracker
- market validator
- performance / latency / stress / regression

---

### `tools/`
Strumenti di reasoning / supporto:
- `ai_reasoning_guard.py`
- `compute_targeted_tests.py`
- `pr_comment_report.py`
- `repo_guardrail.py`

---

### `ui/`
Componenti UI:
- `draggable_runner.py`
- `mini_ladder.py`
- `toolbar.py`
- `tabs/telegram_tab_ui.py`

---

## Moduli che tendono a essere sensibili

Questi file sono spesso ad alto rischio quando rompono:
- `auto_updater.py`
- `executor_manager.py`
- `telegram_listener.py`
- `plugin_manager.py`
- `betfair_client.py`
- `controllers/dutching_controller.py`
- `database.py`
- `core/trading_engine.py`
- `ui/mini_ladder.py`
- `simulation_broker.py`

---

## Perché il repository va trattato con prudenza

Perché include contemporaneamente:
- UI
- core HFT
- OMS
- guardrails
- Telegram async
- simulation
- plugin system
- DB concurrency
- CI complessa
- test suite enorme

Quindi:
- un fix locale può rompere contratti lontani
- un refactor “pulito” può distruggere retrocompatibilità
- un miglioramento estetico può rompere decine di test

---

## Regola operativa per l’AI

Quando l’assistente vede questo repository, deve assumere:

1. che il comportamento corretto sia espresso dai test
2. che i contratti pubblici siano più importanti dell’eleganza
3. che ogni fix debba essere minimo
4. che non deve improvvisare redesign
5. che deve leggere test e fixture correlate prima di proporre modifiche
