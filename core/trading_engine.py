"""
Trading Engine (UI-Agnostic)
Livello Istituzionale: Pattern Saga, Recovery, Persistence Completa, Simulazione, Best Price.
"""
__all__ = ["TradingEngine"]

import time
import uuid
import json
import logging
import threading
from circuit_breaker import TransientError, PermanentError

logger = logging.getLogger(__name__)

class TradingEngine:
    def __init__(self, bus, db, client_getter, executor):
        self.bus = bus
        self.db = db
        self.client_getter = client_getter
        self.executor = executor

        self.is_killed = False
        self._active_submissions = set()
        self._lock_mutex = threading.Lock()

        self.bus.subscribe("CMD_QUICK_BET", self._handle_quick_bet)
        self.bus.subscribe("CMD_PLACE_DUTCHING", self._handle_place_dutching)
        self.bus.subscribe("CMD_EXECUTE_CASHOUT", self._handle_cashout)
        self.bus.subscribe("STATE_UPDATE_SAFE_MODE", self._toggle_kill_switch)
        self.bus.subscribe("CLIENT_CONNECTED", lambda _: self._recover_pending_sagas())

    def _toggle_kill_switch(self, is_safe):
        self.is_killed = bool(is_safe)

    def _acquire_lock(self, customer_ref):
        with self._lock_mutex:
            if customer_ref in self._active_submissions: return False
            self._active_submissions.add(customer_ref)
            return True

    def _release_lock(self, customer_ref):
        with self._lock_mutex:
            self._active_submissions.discard(customer_ref)

    def _recover_pending_sagas(self):
        def task():
            pending = self.db.get_pending_sagas()
            if not pending: return
            client = self.client_getter()
            if not client: return

            logger.warning(f"[Recovery] Trovate {len(pending)} saghe pendenti post-crash.")

            for saga in pending:
                customer_ref = saga['customer_ref']
                market_id = saga['market_id']
                raw_payload = saga.get('raw_payload', '{}')

                try:
                    payload = json.loads(raw_payload)
                except:
                    payload = {}

                is_recovered, _ = self._reconcile_orders(client, market_id, customer_ref)

                if is_recovered:
                    self.db.mark_saga_reconciled(customer_ref)

                    if 'results' in payload:
                        self.db.save_bet(
                            event_name=payload.get('event_name', 'Recuperato'),
                            market_id=market_id,
                            market_name=payload.get('market_name', ''),
                            bet_type=payload.get('bet_type', ''),
                            selections=payload.get('results', []),
                            total_stake=payload.get('total_stake', 0.0),
                            potential_profit=0.0,
                            status='RECOVERED'
                        )
                    elif 'green_up' in payload:
                        self.db.save_cashout_transaction(
                            market_id=market_id,
                            selection_id=payload.get('selection_id', ''),
                            original_bet_id='', cashout_bet_id=customer_ref,
                            original_side='', original_stake=0, original_price=0,
                            cashout_side=payload.get('side', ''),
                            cashout_stake=payload.get('stake', 0),
                            cashout_price=payload.get('price', 0),
                            profit_loss=0.0
                        )
                    elif 'stake' in payload:
                        self.db.save_bet(
                            event_name=payload.get('event_name', 'Recuperato'),
                            market_id=market_id,
                            market_name=payload.get('market_name', ''),
                            bet_type=payload.get('bet_type', ''),
                            selections=[{"selectionId": payload.get('selection_id'), "runnerName": payload.get('runner_name'), "price": payload.get('price'), "stake": payload.get('stake')}],
                            total_stake=payload.get('stake', 0.0),
                            potential_profit=0.0,
                            status='RECOVERED'
                        )
                    logger.info(f"[Recovery] Saga {customer_ref} riconciliata.")
                else:
                    self.db.mark_saga_failed(customer_ref)
                    logger.warning(f"[Recovery] Saga {customer_ref} marcata fallita.")

        self.executor.submit("saga_recovery", task)

    def _reconcile_orders(self, client, market_id, customer_ref):
        for delay in [0.5, 1.0, 2.0]:
            time.sleep(delay)
            try:
                try: orders = client.get_current_orders(market_ids=[market_id], customer_order_refs=[customer_ref])
                except TypeError: orders = client.get_current_orders()
                all_orders = orders.get('matched', []) + orders.get('unmatched', [])
                recovered = [o for o in all_orders if (o.get('customerOrderRef') == customer_ref or o.get('customerRef') == customer_ref) and str(o.get('marketId')) == str(market_id)]
                if recovered: return True, recovered
            except Exception: continue
        return False, []

    def _handle_quick_bet(self, payload):
        def task():
            if self.is_killed:
                self.bus.publish("QUICK_BET_FAILED", "SAFE MODE ATTIVO")
                return
            customer_ref = uuid.uuid4().hex[:32]
            if not self._acquire_lock(customer_ref): return
            try:
                market_id = payload['market_id']
                selection_id = payload['selection_id']
                bet_type = payload['bet_type']
                price = float(payload['price'])
                stake = float(payload['stake'])
                sim_mode = payload['simulation_mode']

                if sim_mode:
                    sim_settings = self.db.get_simulation_settings()
                    v_balance = sim_settings.get("virtual_balance", 0.0)
                    liability = stake * (price - 1) if bet_type == "LAY" else stake

                    if v_balance >= liability:
                        new_bal = v_balance - liability
                        self.db.save_simulation_bet(
                            event_name=payload.get('event_name', ''),
                            market_id=market_id, market_name=payload.get('market_name', ''),
                            side=bet_type, selection_id=selection_id,
                            selection_name=payload.get('runner_name', ''),
                            price=price, stake=stake, status="MATCHED"
                        )
                        self.db.increment_simulation_bet_count(new_bal)
                        self.bus.publish("QUICK_BET_SUCCESS", {"runner_name": payload['runner_name'], "price": price, "stake": stake, "new_balance": new_bal, "sim": True})
                    else:
                        self.bus.publish("QUICK_BET_FAILED", "Saldo virtuale insufficiente")
                    return

                client = self.client_getter()
                if not client: raise Exception("Client non connesso")
                self.db.create_pending_saga(customer_ref, market_id, selection_id, payload)

                try:
                    result = client.place_bet(market_id=market_id, selection_id=selection_id, side=bet_type, price=price, size=stake, persistence_type='LAPSE', customer_ref=customer_ref)
                    if result.get('status') == 'SUCCESS':
                        self.db.mark_saga_reconciled(customer_ref)
                        matched = sum(r.get('sizeMatched', 0) for r in result.get('instructionReports', []))
                        status = "MATCHED" if matched >= stake else ("PARTIALLY_MATCHED" if matched > 0 else "UNMATCHED")

                        self.db.save_bet(
                            event_name=payload.get('event_name', ''), market_id=market_id, market_name=payload.get('market_name', ''),
                            bet_type=bet_type, selections=[{"selectionId": selection_id, "runnerName": payload.get('runner_name', ''), "price": price, "stake": stake}],
                            total_stake=stake, potential_profit=0.0, status=status
                        )
                        self.bus.publish("QUICK_BET_SUCCESS", {"runner_name": payload['runner_name'], "price": price, "matched": matched, "sim": False})
                    else:
                        self.db.mark_saga_failed(customer_ref)
                        self.db.save_bet(
                            event_name=payload.get('event_name', ''), market_id=market_id, market_name=payload.get('market_name', ''),
                            bet_type=bet_type, selections=[{"selectionId": selection_id, "runnerName": payload.get('runner_name', ''), "price": price, "stake": stake}],
                            total_stake=stake, potential_profit=0.0, status="FAILED"
                        )
                        self.bus.publish("QUICK_BET_FAILED", f"Stato API: {result.get('status')}")
                except Exception as e:
                    is_recovered, recovered_reports = self._reconcile_orders(client, market_id, customer_ref)
                    if is_recovered:
                        self.db.mark_saga_reconciled(customer_ref)
                        matched = sum(r.get('sizeMatched', 0) for r in recovered_reports)
                        status = "MATCHED" if matched >= stake else ("PARTIALLY_MATCHED" if matched > 0 else "UNMATCHED")

                        self.db.save_bet(
                            event_name=payload.get('event_name', ''), market_id=market_id, market_name=payload.get('market_name', ''),
                            bet_type=bet_type, selections=[{"selectionId": selection_id, "runnerName": payload.get('runner_name', ''), "price": price, "stake": stake}],
                            total_stake=stake, potential_profit=0.0, status=status
                        )
                        self.bus.publish("QUICK_BET_SUCCESS", {"runner_name": payload['runner_name'], "price": price, "matched": matched, "sim": False, "recovered": True})
                    else:
                        self.db.mark_saga_failed(customer_ref)
                        self.db.save_bet(
                            event_name=payload.get('event_name', ''), market_id=market_id, market_name=payload.get('market_name', ''),
                            bet_type=bet_type, selections=[{"selectionId": selection_id, "runnerName": payload.get('runner_name', ''), "price": price, "stake": stake}],
                            total_stake=stake, potential_profit=0.0, status="FAILED"
                        )
                        if isinstance(e, PermanentError): self.bus.publish("SAFE_MODE_TRIGGER", {"reason": "Circuit Breaker", "details": str(e)})
                        self.bus.publish("QUICK_BET_FAILED", f"Errore Rete: {str(e)}")
            finally: self._release_lock(customer_ref)
        self.executor.submit("engine_quick_bet", task)

    def _handle_place_dutching(self, payload):
        def task():
            if self.is_killed:
                self.bus.publish("DUTCHING_FAILED", "SAFE MODE ATTIVO")
                return
            customer_ref = uuid.uuid4().hex[:32]
            if not self._acquire_lock(customer_ref): return
            try:
                market_id = payload['market_id']
                bet_type = payload['bet_type']
                results = payload['results']
                sim_mode = payload['simulation_mode']
                total_stake = payload['total_stake']
                use_best_price = payload.get('use_best_price', False)
                requested_size = sum(r['stake'] for r in results)

                if sim_mode:
                    sim_settings = self.db.get_simulation_settings()
                    v_balance = sim_settings.get("virtual_balance", 0.0)

                    total_risk = sum(r['stake'] * (r.get('price', 1.0) - 1.0) for r in results) if bet_type == "LAY" else total_stake

                    if v_balance >= total_risk:
                        new_bal = v_balance - total_risk
                        self.db.save_simulation_bet(
                            event_name=payload.get('event_name', ''),
                            market_id=market_id, market_name=payload.get('market_name', ''),
                            side=bet_type, status="MATCHED", selections=results, total_stake=total_stake
                        )
                        self.db.increment_simulation_bet_count(new_bal)
                        self.bus.publish("DUTCHING_SUCCESS", {"sim": True, "total_stake": total_stake, "new_balance": new_bal})
                    else:
                        self.bus.publish("DUTCHING_FAILED", "Saldo virtuale insufficiente")
                    return

                client = self.client_getter()
                if not client: raise Exception("Client non connesso")
                self.db.create_pending_saga(customer_ref, market_id, None, payload)

                try:
                    instructions = []
                    if use_best_price:
                        book = client.get_market_book(market_id)
                        current_prices = {}
                        if book and book.get('runners'):
                            for r in book['runners']:
                                sel_id = r.get('selectionId')
                                ex = r.get('ex', {})
                                if bet_type == 'BACK':
                                    avail = ex.get('availableToBack', [])
                                    current_prices[sel_id] = avail[0].get('price', 1.01) if avail else 1.01
                                else:
                                    avail = ex.get('availableToLay', [])
                                    current_prices[sel_id] = avail[0].get('price', 1000.0) if avail else 1000.0
                        for r in results:
                            price = current_prices.get(r['selectionId'], r['price'])
                            instructions.append({'selectionId': r['selectionId'], 'side': bet_type, 'price': price, 'size': r['stake']})
                    else:
                        instructions = [{'selectionId': r['selectionId'], 'side': bet_type, 'price': r['price'], 'size': r['stake']} for r in results]

                    result = client.place_orders(market_id, instructions, customer_ref=customer_ref)
                    reports = result.get('instructionReports', [])

                    if result.get('status') == 'SUCCESS':
                        self.db.mark_saga_reconciled(customer_ref)
                        matched = sum(r.get('sizeMatched', 0) for r in reports)
                        status = "MATCHED" if matched >= requested_size - 0.01 else ("PARTIALLY_MATCHED" if matched > 0 else "UNMATCHED")

                        self.db.save_bet(
                            event_name=payload.get('event_name', ''), market_id=market_id, market_name=payload.get('market_name', ''),
                            bet_type=bet_type, selections=results, total_stake=total_stake, potential_profit=0.0, status=status
                        )
                        self.bus.publish("DUTCHING_SUCCESS", {"sim": False, "matched": matched})
                    else:
                        self.db.mark_saga_failed(customer_ref)
                        self.db.save_bet(
                            event_name=payload.get('event_name', ''), market_id=market_id, market_name=payload.get('market_name', ''),
                            bet_type=bet_type, selections=results, total_stake=total_stake, potential_profit=0.0, status="FAILED"
                        )
                        self.bus.publish("DUTCHING_FAILED", f"Stato API: {result.get('status')}")
                except Exception as e:
                    is_recovered, recovered_reports = self._reconcile_orders(client, market_id, customer_ref)
                    if is_recovered:
                        self.db.mark_saga_reconciled(customer_ref)
                        matched = sum(r.get('sizeMatched', 0) for r in recovered_reports)
                        status = "MATCHED" if matched >= requested_size - 0.01 else ("PARTIALLY_MATCHED" if matched > 0 else "UNMATCHED")

                        self.db.save_bet(
                            event_name=payload.get('event_name', ''), market_id=market_id, market_name=payload.get('market_name', ''),
                            bet_type=bet_type, selections=results, total_stake=total_stake, potential_profit=0.0, status=status
                        )
                        self.bus.publish("DUTCHING_SUCCESS", {"sim": False, "matched": matched, "recovered": True})
                    else:
                        self.db.mark_saga_failed(customer_ref)
                        self.db.save_bet(
                            event_name=payload.get('event_name', ''), market_id=market_id, market_name=payload.get('market_name', ''),
                            bet_type=bet_type, selections=results, total_stake=total_stake, potential_profit=0.0, status="FAILED"
                        )
                        if isinstance(e, PermanentError): self.bus.publish("SAFE_MODE_TRIGGER", {"reason": "Circuit Breaker", "details": str(e)})
                        self.bus.publish("DUTCHING_FAILED", f"Errore Rete: {str(e)}")
            finally: self._release_lock(customer_ref)
        self.executor.submit("engine_dutching", task)

    def _handle_cashout(self, payload):
        def task():
            if self.is_killed:
                self.bus.publish("CASHOUT_FAILED", "SAFE MODE ATTIVO")
                return
            customer_ref = uuid.uuid4().hex[:32]
            if not self._acquire_lock(customer_ref): return
            try:
                client = self.client_getter()
                if not client: raise Exception("Client non connesso")

                market_id = payload['market_id']
                selection_id = payload['selection_id']
                side = payload['side']
                stake = payload['stake']
                price = payload['price']
                green_up = payload['green_up']

                self.db.create_pending_saga(customer_ref, market_id, selection_id, payload)
                instructions = [{'selectionId': selection_id, 'side': side, 'orderType': 'LIMIT', 'limitOrder': {'size': stake, 'price': price, 'persistenceType': 'LAPSE'}}]

                try:
                    result = client.place_orders(market_id, instructions, customer_ref=customer_ref)
                    if result.get('status') == 'SUCCESS':
                        self.db.mark_saga_reconciled(customer_ref)
                        self.db.save_cashout_transaction(
                            market_id=market_id, selection_id=selection_id, original_bet_id='', cashout_bet_id=customer_ref,
                            original_side='', original_stake=0, original_price=0, cashout_side=side, cashout_stake=stake, cashout_price=price, profit_loss=green_up
                        )
                        self.bus.publish("CASHOUT_SUCCESS", {"green_up": green_up})
                    else:
                        self.db.mark_saga_failed(customer_ref)
                        self.bus.publish("CASHOUT_FAILED", f"Stato API: {result.get('status')}")
                except Exception as e:
                    is_recovered, recovered_reports = self._reconcile_orders(client, market_id, customer_ref)
                    if is_recovered:
                        self.db.mark_saga_reconciled(customer_ref)
                        self.db.save_cashout_transaction(
                            market_id=market_id, selection_id=selection_id, original_bet_id='', cashout_bet_id=customer_ref,
                            original_side='', original_stake=0, original_price=0, cashout_side=side, cashout_stake=stake, cashout_price=price, profit_loss=green_up
                        )
                        self.bus.publish("CASHOUT_SUCCESS", {"green_up": green_up, "recovered": True})
                    else:
                        self.db.mark_saga_failed(customer_ref)
                        if isinstance(e, PermanentError): self.bus.publish("SAFE_MODE_TRIGGER", {"reason": "Circuit Breaker Cashout", "details": str(e)})
                        self.bus.publish("CASHOUT_FAILED", f"Errore Rete: {str(e)}")
            finally: self._release_lock(customer_ref)
        self.executor.submit("engine_cashout", task)

