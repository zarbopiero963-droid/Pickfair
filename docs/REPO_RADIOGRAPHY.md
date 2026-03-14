# Pickfair - Repository Radiography

Questo documento serve a dare all’assistente AI una radiografia strutturale del repository.

Il messaggio chiave è semplice:

**il repo è grande, stratificato, pieno di test e non va trattato come un piccolo progetto toy.**

Pickfair è un sistema complesso che combina:

- UI desktop
- core trading engine
- OMS (order management system)
- guardrails
- pipeline async
- Telegram integration
- simulation framework
- plugin architecture
- database concurrency
- CI avanzata
- suite di test molto ampia

Per questo motivo qualsiasi modifica deve essere **minima, compatibile e prudente**.

---

# Repository Analysis Pipeline

Pickfair include una pipeline di **radiografia automatica del repository**.

Questa pipeline produce file di contesto che l’AI deve preferire rispetto all’analisi completa del codice.

Output principali:

audit_out/

ai_reduced_context.json  
root_cause.md  
fix_suggestions.md  
priority_fix_order.md  
fix_context.json  

Se questi file esistono, **devono essere usati come contesto primario**.

---

# Root overview

## File root principali

- .bandit  
- .coveragerc  
- .editorconfig  
- .gitignore  
- .ruff.toml  
- AVVIA.bat  
- CONTRIBUTING.md  
- Makefile  
- Pickfair.spec  
- README.txt  
- auto_throttle.py  
- auto_updater.py  
- automation_engine.py  
- automation_optimizer.py  
- betfair_client.py  
- build.bat  
- build.py  
- circuit_breaker.py  
- database.py  
- devops_update.txt  
- dutching.py  
- dutching_cache.py  
- dutching_state.py  
- dutching_ui.py  
- executor_manager.py  
- goal_engine_pro.py  
- main.py  
- market_tracker.py  
- market_validator.py  
- order_manager.py  
- plugin_manager.py  
- plugin_runner.py  
- pnl_cache.py  
- pnl_engine.py  
- repo_update_engine.py  
- safe_mode.py  
- safety_logger.py  
- shutdown_manager.py  
- simulation_broker.py  
- simulation_speed.py  
- telegram_listener.py  
- telegram_sender.py  
- theme.py  
- tick_dispatcher.py  
- tick_storage.py  
- trading_config.py  
- tree_manager.py  
- ui_optimizer.py  
- ui_queue.py  

---

# Directory map

## .github/

Contiene:

- workflow CI/CD  
- script di audit  
- script AI reasoning  
- script di supporto repository  

### .github/scripts/

- ai_reasoning_layer.py  
- build_priority_fix_order.py  
- build_fix_context.py  
- repo_ultra_audit_narrative.py  

Questi script producono la **radiografia del repository**.

---

### .github/workflows/

Workflow stratificati:

Radiography / Forensics

- repo_api_report_v4.yml  
- repo_autopsy.yml  
- repo_forensics.yml  
- repo_ultra_audit_narrative.yml  

CI standard

- pickfair_ci.yml  
- run_tests.yml  
- tests.yml  

Stress / Quality

- pickfair_ultra_ci.yml  
- test_quality.yml  

System validation

- system_validation.yml  

AI guardrails

- ai-guardrails.yml  

---

# AI / Quant Engines

## ai/

Motori di analisi:

- ai_guardrail.py  
- ai_pattern_engine.py  
- wom_engine.py  

---

# Application Modules

## app_modules/

Moduli applicativi UI:

- betting  
- monitoring  
- simulation  
- streaming  
- telegram  
- ui module  

---

# Controllers

## controllers/

- dutching_controller.py  
- telegram_controller.py  

---

# Core Trading System

## core/

Componenti HFT / OMS:

- event bus  
- trading engine  
- analytics  
- tick ring buffer  
- safety layer  
- async database writer  

Questa è la parte più sensibile del sistema.

---

# Guardrails

## guardrails/

Contiene:

- policy di sicurezza  
- snapshot delle API pubbliche  
- dipendenze consentite  
- moduli critici  
- semantic specs  

Questi file **definiscono i contratti del sistema**.

---

# Scripts

## scripts/

Strumenti di analisi repository e contract tests.

---

# Test Suite

## tests/

La cartella tests è **parte del contratto del repository**.

Non è solo verifica:  
è **la definizione del comportamento corretto**.

Categorie principali:

### Functional tests

verificano:

- trading engine  
- database  
- plugin  
- telegram  
- simulation  

### Contract tests

proteggono:

- payload JSON  
- API pubbliche  
- retrocompatibilità  

### Guardrail tests

proteggono:

- dipendenze  
- scope file critici  
- import smoke  
- reasoning guard  

---

# Moduli sensibili

File che rompono facilmente:

- auto_updater.py  
- executor_manager.py  
- telegram_listener.py  
- plugin_manager.py  
- betfair_client.py  
- controllers/dutching_controller.py  
- database.py  
- core/trading_engine.py  
- ui/mini_ladder.py  
- simulation_broker.py  

---

# Perché il repository va trattato con prudenza

Un fix locale può rompere:

- contratti lontani  
- snapshot JSON  
- plugin  
- UI async  
- simulation  

Quindi:

- evitare refactor grandi  
- evitare redesign  
- evitare cambi estetici  

---

# AI Interaction Protocol

Quando l’assistente AI analizza questo repository deve assumere:

1. il comportamento corretto è definito dai test  
2. i contratti pubblici sono più importanti dell’eleganza  
3. ogni fix deve essere minimo  
4. non deve improvvisare redesign  
5. deve leggere test e fixture correlate prima di proporre modifiche  
6. se esiste `fix_context.json`, usarlo come contesto primario