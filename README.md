# 🦅 Pickfair - Quantitative Betfair Trading System

**Versione:** 3.19.1+  
**Architettura:** Asincrona, Event-Driven, Multi-Thread, Ring-Buffered  
**Interfaccia:** CustomTkinter

Pickfair è un OMS (Order Management System) per Betfair Exchange progettato per tollerare volatilità, latenze di rete, input sporchi, errori parziali e recovery complessi. Non è un semplice bot UI: è un sistema di trading sportivo strutturato con core asincrono, guardrail, automazione PnL, copy-trading Telegram e pipeline DevOps molto estesa.

---

## Obiettivo del progetto

Pickfair esiste per:

- operare su mercati Exchange in modo disciplinato
- minimizzare crash, blocchi UI e corruzioni di stato
- mantenere retrocompatibilità tra moduli, test e contratti pubblici
- tollerare errori di rete, import-time failure, race condition e casi sporchi
- permettere fix mirati senza rompere la pipeline CI

---

## Architettura generale

Il sistema è costruito con una separazione netta tra:

- **UI**
- **Core operativo**
- **Controller**
- **Motori matematici**
- **Motori AI / Guardrail**
- **Layer Telegram**
- **Persistenza**
- **DevOps / CI / Guardrails**

### Componenti principali

- **UI Layer**
  - `app_modules/`
  - `ui/`
  - `ui_queue.py`
  - `dutching_ui.py`

- **Core Layer**
  - `core/event_bus.py`
  - `core/trading_engine.py`
  - `core/risk_middleware.py`
  - `core/tick_ring_buffer.py`
  - `core/async_db_writer.py`

- **Trading / OMS**
  - `betfair_client.py`
  - `order_manager.py`
  - `executor_manager.py`
  - `market_tracker.py`
  - `market_validator.py`

- **Dutching & PnL**
  - `dutching.py`
  - `dutching_state.py`
  - `dutching_cache.py`
  - `controllers/dutching_controller.py`
  - `pnl_engine.py`
  - `pnl_cache.py`

- **Telegram Ecosystem**
  - `telegram_listener.py`
  - `telegram_sender.py`
  - `controllers/telegram_controller.py`
  - `app_modules/telegram_module.py`

- **Automation / Safety**
  - `automation_engine.py`
  - `automation_optimizer.py`
  - `safe_mode.py`
  - `safety_logger.py`
  - `circuit_breaker.py`
  - `auto_throttle.py`

- **AI / Quant**
  - `ai/ai_guardrail.py`
  - `ai/ai_pattern_engine.py`
  - `ai/wom_engine.py`
  - `goal_engine_pro.py`

- **Simulation**
  - `simulation_broker.py`
  - `simulation_speed.py`
  - `app_modules/simulation_module.py`

- **Plugin System**
  - `plugin_manager.py`
  - `plugin_runner.py`

- **Persistence**
  - `database.py`
  - `core/async_db_writer.py`

---

## Interfaccia utente

L’interfaccia gira nel main thread e non deve mai contenere logica bloccante. Gli aggiornamenti da thread esterni passano tramite `ui_queue.py`.

### Tab e moduli visivi
- tab trading
- tab dashboard
- tab telegram
- tab settings
- tab simulazione
- componenti UI di ladder, toolbar, runner list, queue display

### Toolbar
- toggle simulazione
- safe mode / panic
- indicatori di stato
- controlli di cashout rapido
- modalità lordo / netto

---

## Dutching Engine

Pickfair include una UI dedicata e un motore matematico per Dutching e scenari misti.

### Funzioni principali
- stake available
- required profit
- mixed back/lay
- swap runner
- auto green
- offset quota
- what-if manuale
- preset stake
- supporto a loss hedging

---

## Telegram Ecosystem

### Listener
`telegram_listener.py` legge messaggi da canali e parserizza:

- segnali master
- messaggi custom regex
- casi sporchi
- cashout
- alias legacy

### Sender
`telegram_sender.py` inoltra operazioni in modo asincrono con protezione anti-flood e queue non bloccante.

---

## HFT Core e OMS

Il core è pensato per lavorare con tick ad alta frequenza e non deve crescere in RAM in modo incontrollato.

### Elementi chiave
- `EventBus` come nervo centrale
- `RiskMiddleware` come gatekeeper
- `tick_ring_buffer.py` per dati rolling bounded
- `TradingEngine` con pattern saga e recovery
- `async_db_writer.py` per scaricare scritture dal thread critico

---

## Guardrails e AI

Pickfair non si limita a inviare ordini: li filtra con regole di sicurezza.

### AI Guardrail
Controlla:
- liquidità
- spread
- volatilità
- contesto rischioso

### WoM Engine
Analizza:
- peso del denaro
- pressione reale del book
- possibili muri fasulli
- segnali di spoofing

---

## Goal Engine Pro

Modulo asincrono per rilevare eventi di mercato e situazioni tipo goal / goal annullato / VAR mediante cache e verifica stato.

---

## Simulazione

La simulazione è isolata dal live e usa broker dedicato.

### Include
- storico parallelo
- saldo virtuale
- ritardi simulati
- spread simulato
- ordini simulati

---

## Plugin System

Il sistema plugin consente di agganciare logica custom al flusso eventi senza modificare direttamente il core OMS.

---

## Database

Il database è un punto critico del progetto.

### Principi
- retrocompatibilità forte
- toleranza a kwargs legacy
- metodi storici non vanno rotti
- scritture massicce spostate su writer asincrono
- gestione rollback / transazioni / recovery

---

## Test e CI

La cartella `tests/` è parte integrante del contratto del progetto.  
Il comportamento corretto del repository è definito in larga parte dai test.

### Il repository contiene:
- unit test
- regression test
- contract test
- snapshot test
- guardrail test
- performance test
- resilience test
- property-based / fuzz-oriented test
- import smoke
- architecture checks

### Regola pratica
Se modifichi un comportamento, devi verificare anche:
- test direttamente collegati
- fixture collegate
- contract test
- snapshot test

---

## Filosofia del progetto

Pickfair non deve essere “elegante” nel senso accademico.  
Deve essere:

- stabile
- conservativo
- tollerante
- retrocompatibile
- fixabile in modo minimo
- resistente ai refactor distruttivi

---

## Regola d’oro per chi modifica il codice

Il compito non è reinterpretare il progetto.  
Il compito è riallineare il codice al contratto già espresso dal repository.

---

## Documenti da leggere prima di toccare il codice

1. `docs/AI_RULEBOOK.md`
2. `docs/REPO_RADIOGRAPHY.md`
3. `docs/PAYLOAD_CONTRACTS.md`
4. `docs/TESTING_STRATEGY.md`

---

## Stato corretto di un fix

Un fix è buono quando:

- risolve il bug mirato
- non cambia logica non coinvolta
- non introduce feature extra
- preserva compatibilità
- tocca pochi file
- migliora o preserva la CI