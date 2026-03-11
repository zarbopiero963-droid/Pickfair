"""
Trading Engine (UI-Agnostic)
Livello Istituzionale: OMS unico, Pattern Saga, Recovery, Persistence Completa,
Simulazione, Best Price, stati ordine coerenti, eventi UI coerenti.

Micro-stake:
- attivo automaticamente per stake < 2.00
- BACK usa stub price 1.01
- LAY usa stub price 1000.0
- sequenza: PLACE stub -> CANCEL riduzione -> REPLACE quota reale
- in caso di errore: rollback con CANCEL totale del residuo
- in caso di crash: auto-cleanup degli stub al riavvio
"""

__all__ = ["TradingEngine"]

import json
import logging
import threading
import time
import uuid

from circuit_breaker import PermanentError

logger = logging.getLogger(__name__)


class TradingEngine:
    MIN_EXCHANGE_STAKE = 2.0
    MICRO_MIN_STAKE = 0.10

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

    # =========================================================
    # BASIC INTERNALS
    # =========================================================

    def _toggle_kill_switch(self, payload):
        if isinstance(payload, dict):
            self.is_killed = bool(payload.get("enabled", False))
        else:
            self.is_killed = bool(payload)

    def _acquire_lock(self, customer_ref):
        with self._lock_mutex:
            if customer_ref in self._active_submissions:
                return False
            self._active_submissions.add(customer_ref)
            return True

    def _release_lock(self, customer_ref):
        with self._lock_mutex:
            self._active_submissions.discard(customer_ref)

    def _compute_order_status(self, matched_amount, requested_amount):
        matched_amount = float(matched_amount or 0.0)
        requested_amount = float(requested_amount or 0.0)

        if matched_amount <= 0:
            return "UNMATCHED"
        if matched_amount + 0.01 >= requested_amount:
            return "MATCHED"
        return "PARTIALLY_MATCHED"

    def _safe_sum_matched(self, reports):
        total = 0.0
        for report in reports or []:
            total += float(
                self._resp_get(
                    report,
                    "sizeMatched",
                    self._resp_get(report, "size_matched", 0),
                )
                or 0
            )
        return total

    def _extract_order_price(self, order):
        if not isinstance(order, dict):
            return 0.0

        if "priceSize" in order and isinstance(order["priceSize"], dict):
            try:
                return float(order["priceSize"].get("price", 0) or 0)
            except Exception:
                return 0.0

        try:
            return float(order.get("price", 0) or 0)
        except Exception:
            return 0.0

    def _extract_order_remaining_size(self, order):
        if not isinstance(order, dict):
            return 0.0

        for key in ("sizeRemaining", "remainingSize", "size_left", "size"):
            if key in order:
                try:
                    return float(order.get(key, 0) or 0)
                except Exception:
                    pass

        if "priceSize" in order and isinstance(order["priceSize"], dict):
            try:
                return float(order["priceSize"].get("size", 0) or 0)
            except Exception:
                pass

        return 0.0

    def _is_stub_micro_order(self, order):
        price = self._extract_order_price(order)
        remaining = self._extract_order_remaining_size(order)

        if remaining <= 0:
            return False

        return abs(price - 1.01) < 0.0001 or abs(price - 1000.0) < 0.0001

    def _cancel_stub_orders(self, client, market_id, recovered_reports):
        stub_orders = [
            order for order in (recovered_reports or []) if self._is_stub_micro_order(order)
        ]
        if not stub_orders:
            return False

        instructions = []
        for order in stub_orders:
            bet_id = order.get("betId")
            if bet_id:
                instructions.append({"betId": str(bet_id)})

        if not instructions:
            return False

        logger.warning(
            "[Recovery] Trovati %s stub micro-stake su market_id=%s. Cleanup automatico.",
            len(instructions),
            market_id,
        )

        try:
            self._call_cancel_orders(
                client=client,
                market_id=market_id,
                instructions=instructions,
            )
            return True
        except Exception as e:
            logger.error(
                "[Recovery] Cleanup stub fallito su market_id=%s: %s",
                market_id,
                e,
            )
            return False

    # =========================================================
    # RESPONSE / CLIENT NORMALIZATION
    # =========================================================

    def _resp_get(self, obj, key, default=None):
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _response_status(self, resp):
        return self._resp_get(resp, "status")

    def _response_instruction_reports(self, resp):
        reports = self._resp_get(resp, "instructionReports")
        if reports is None:
            reports = self._resp_get(resp, "instruction_reports")
        return list(reports or [])

    def _extract_bet_id(self, report):
        return self._resp_get(report, "betId", self._resp_get(report, "bet_id"))

    def _wrapper_or_raw_client(self, client):
        raw = getattr(client, "client", None)
        return raw if raw is not None else client

    def _call_place_bet(
        self,
        client,
        market_id,
        selection_id,
        side,
        price,
        size,
        customer_ref,
    ):
        if hasattr(client, "place_bet"):
            return client.place_bet(
                market_id=market_id,
                selection_id=selection_id,
                side=side,
                price=price,
                size=size,
                persistence_type="LAPSE",
                customer_ref=customer_ref,
            )

        raw = self._wrapper_or_raw_client(client)
        if hasattr(raw, "betting") and hasattr(raw.betting, "place_orders"):
            instructions = [
                {
                    "selectionId": selection_id,
                    "side": side,
                    "orderType": "LIMIT",
                    "limitOrder": {
                        "size": size,
                        "price": price,
                        "persistenceType": "LAPSE",
                    },
                }
            ]
            return raw.betting.place_orders(
                market_id=market_id,
                instructions=instructions,
                customer_ref=customer_ref,
            )

        raise AttributeError("Client non supporta place_bet/place_orders")

    def _call_place_orders(self, client, market_id, instructions, customer_ref):
        if hasattr(client, "place_orders"):
            return client.place_orders(
                market_id,
                instructions,
                customer_ref=customer_ref,
            )

        raw = self._wrapper_or_raw_client(client)
        if hasattr(raw, "betting") and hasattr(raw.betting, "place_orders"):
            return raw.betting.place_orders(
                market_id=market_id,
                instructions=instructions,
                customer_ref=customer_ref,
            )

        raise AttributeError("Client non supporta place_orders")

    def _call_cancel_orders(self, client, market_id, instructions):
        if hasattr(client, "cancel_orders"):
            try:
                return client.cancel_orders(market_id, instructions)
            except TypeError:
                return client.cancel_orders(
                    market_id=market_id,
                    instructions=instructions,
                )

        raw = self._wrapper_or_raw_client(client)
        if hasattr(raw, "betting") and hasattr(raw.betting, "cancel_orders"):
            return raw.betting.cancel_orders(
                market_id=market_id,
                instructions=instructions,
            )

        raise AttributeError("Client non supporta cancel_orders")

    def _call_replace_orders(self, client, market_id, instructions):
        if hasattr(client, "replace_orders"):
            try:
                return client.replace_orders(market_id, instructions)
            except TypeError:
                return client.replace_orders(
                    market_id=market_id,
                    instructions=instructions,
                )

        raw = self._wrapper_or_raw_client(client)
        if hasattr(raw, "betting") and hasattr(raw.betting, "replace_orders"):
            return raw.betting.replace_orders(
                market_id=market_id,
                instructions=instructions,
            )

        raise AttributeError("Client non supporta replace_orders")

    # =========================================================
    # MICRO-STAKE
    # =========================================================

    def _needs_micro_stake(self, stake):
        stake = float(stake or 0.0)
        return self.MICRO_MIN_STAKE <= stake < self.MIN_EXCHANGE_STAKE

    def _micro_stub_price(self, side):
        side = str(side or "").upper()
        return 1.01 if side == "BACK" else 1000.0

    def _build_limit_instruction(self, selection_id, side, price, size):
        return {
            "selectionId": int(selection_id),
            "side": str(side).upper(),
            "orderType": "LIMIT",
            "limitOrder": {
                "size": float(size),
                "price": float(price),
                "persistenceType": "LAPSE",
            },
        }

    def _build_cancel_instruction(self, bet_id, size_reduction=None):
        data = {"betId": str(bet_id)}
        if size_reduction is not None:
            data["sizeReduction"] = float(size_reduction)
        return data

    def _build_replace_instruction(self, bet_id, new_price):
        return {
            "betId": str(bet_id),
            "newPrice": float(new_price),
        }

    def _execute_micro_stake(
        self,
        client,
        market_id,
        selection_id,
        side,
        price,
        stake,
        customer_ref,
    ):
        requested_stake = float(stake)
        if requested_stake < self.MICRO_MIN_STAKE:
            raise ValueError(f"Stake micro troppo basso: {requested_stake}")

        stub_price = self._micro_stub_price(side)
        stub_size = float(self.MIN_EXCHANGE_STAKE)
        size_reduction = round(stub_size - requested_stake, 2)

        if size_reduction <= 0:
            raise ValueError("size_reduction non valida per micro-stake")

        place_resp = self._call_place_bet(
            client=client,
            market_id=market_id,
            selection_id=selection_id,
            side=side,
            price=stub_price,
            size=stub_size,
            customer_ref=customer_ref,
        )

        if self._response_status(place_resp) != "SUCCESS":
            raise RuntimeError(
                f"Micro-stake step PLACE fallito: {self._response_status(place_resp)}"
            )

        place_reports = self._response_instruction_reports(place_resp)
        if not place_reports:
            raise RuntimeError("Micro-stake step PLACE senza instructionReports")

        first_report = place_reports[0]
        bet_id = self._extract_bet_id(first_report)
        matched_now = self._safe_sum_matched(place_reports)

        if matched_now > 0:
            raise RuntimeError(
                f"Micro-stake stub già abbinato ({matched_now}) - abort"
            )

        try:
            cancel_resp = self._call_cancel_orders(
                client=client,
                market_id=market_id,
                instructions=[
                    self._build_cancel_instruction(
                        bet_id,
                        size_reduction=size_reduction,
                    )
                ],
            )
            if self._response_status(cancel_resp) != "SUCCESS":
                raise RuntimeError(
                    f"Micro-stake step CANCEL fallito: {self._response_status(cancel_resp)}"
                )

            replace_resp = self._call_replace_orders(
                client=client,
                market_id=market_id,
                instructions=[self._build_replace_instruction(bet_id, new_price=price)],
            )
            if self._response_status(replace_resp) != "SUCCESS":
                raise RuntimeError(
                    f"Micro-stake step REPLACE fallito: {self._response_status(replace_resp)}"
                )

            reports = self._response_instruction_reports(replace_resp) or place_reports

            return {
                "status": "SUCCESS",
                "instructionReports": reports,
                "micro": True,
                "betId": bet_id,
            }

        except Exception:
            try:
                self._call_cancel_orders(
                    client=client,
                    market_id=market_id,
                    instructions=[self._build_cancel_instruction(bet_id)],
                )
            except Exception as rollback_error:
                logger.critical(
                    "[MicroStake] Rollback fallito bet_id=%s market_id=%s err=%s",
                    bet_id,
                    market_id,
                    rollback_error,
                )
            raise

    # =========================================================
    # RECOVERY
    # =========================================================

    def _recover_pending_sagas(self):
        def task():
            pending = self.db.get_pending_sagas()
            if not pending:
                return

            client = self.client_getter()
            if not client:
                return

            logger.warning(
                "[Recovery] Trovate %s saghe pendenti post-crash.",
                len(pending),
            )

            for saga in pending:
                customer_ref = saga["customer_ref"]
                market_id = saga["market_id"]
                raw_payload = saga.get("raw_payload", "{}")

                try:
                    payload = json.loads(raw_payload)
                except Exception:
                    payload = {}

                is_recovered, recovered_reports = self._reconcile_orders(
                    client,
                    market_id,
                    customer_ref,
                )

                if not is_recovered:
                    self.db.mark_saga_failed(customer_ref)
                    logger.warning(
                        "[Recovery] Saga %s marcata fallita.",
                        customer_ref,
                    )
                    continue

                cleaned_stub = self._cancel_stub_orders(
                    client,
                    market_id,
                    recovered_reports,
                )
                if cleaned_stub:
                    _, recovered_reports = self._reconcile_orders(
                        client,
                        market_id,
                        customer_ref,
                    )

                self.db.mark_saga_reconciled(customer_ref)

                if "results" in payload:
                    matched = self._safe_sum_matched(recovered_reports)
                    requested_size = sum(
                        float(r.get("stake", 0) or 0)
                        for r in payload.get("results", [])
                    )
                    status = self._compute_order_status(matched, requested_size)

                    self.db.save_bet(
                        event_name=payload.get("event_name", "Recuperato"),
                        market_id=market_id,
                        market_name=payload.get("market_name", ""),
                        bet_type=payload.get("bet_type", ""),
                        selections=payload.get("results", []),
                        total_stake=payload.get("total_stake", 0.0),
                        potential_profit=0.0,
                        status=status,
                    )

                elif "green_up" in payload:
                    self.db.save_cashout_transaction(
                        market_id=market_id,
                        selection_id=payload.get("selection_id", ""),
                        original_bet_id="",
                        cashout_bet_id=customer_ref,
                        original_side="",
                        original_stake=0,
                        original_price=0,
                        cashout_side=payload.get("side", ""),
                        cashout_stake=payload.get("stake", 0),
                        cashout_price=payload.get("price", 0),
                        profit_loss=payload.get("green_up", 0.0),
                    )

                elif "stake" in payload:
                    matched = self._safe_sum_matched(recovered_reports)
                    requested_size = float(payload.get("stake", 0.0) or 0.0)
                    status = self._compute_order_status(matched, requested_size)

                    self.db.save_bet(
                        event_name=payload.get("event_name", "Recuperato"),
                        market_id=market_id,
                        market_name=payload.get("market_name", ""),
                        bet_type=payload.get("bet_type", ""),
                        selections=[
                            {
                                "selectionId": payload.get("selection_id"),
                                "runnerName": payload.get("runner_name"),
                                "price": payload.get("price"),
                                "stake": payload.get("stake"),
                            }
                        ],
                        total_stake=payload.get("stake", 0.0),
                        potential_profit=0.0,
                        status=status,
                    )

                logger.info("[Recovery] Saga %s riconciliata.", customer_ref)

        self.executor.submit("saga_recovery", task)

    def _reconcile_orders(self, client, market_id, customer_ref):
        for delay in [0.5, 1.0, 2.0]:
            time.sleep(delay)
            try:
                try:
                    orders = client.get_current_orders(
                        market_ids=[market_id],
                        customer_order_refs=[customer_ref],
                    )
                except TypeError:
                    orders = client.get_current_orders()

                current_orders = (
                    orders.get("currentOrders", [])
                    or orders.get("current_orders", [])
                    or []
                )
                matched_orders = orders.get("matched", []) or []
                unmatched_orders = orders.get("unmatched", []) or []

                all_orders = current_orders + matched_orders + unmatched_orders

                recovered = [
                    order
                    for order in all_orders
                    if (
                        order.get("customerOrderRef") == customer_ref
                        or order.get("customerRef") == customer_ref
                    )
                    and str(order.get("marketId")) == str(market_id)
                ]

                if recovered:
                    return True, recovered
            except Exception:
                continue

        return False, []

    # =========================================================
    # QUICK BET
    # =========================================================

    def _handle_quick_bet(self, payload):
        def task():
            customer_ref = uuid.uuid4().hex[:32]
            if not self._acquire_lock(customer_ref):
                return

            try:
                if self.is_killed:
                    self.bus.publish("QUICK_BET_FAILED", "SAFE MODE ATTIVO")
                    return

                market_id = payload["market_id"]
                selection_id = payload["selection_id"]
                bet_type = str(payload["bet_type"]).upper()
                price = float(payload["price"])
                stake = float(payload["stake"])

                if bool(payload.get("simulation_mode", False)):
                    sim_settings = self.db.get_simulation_settings()
                    v_balance = float(sim_settings.get("virtual_balance", 0.0) or 0.0)
                    liability = stake * (price - 1) if bet_type == "LAY" else stake

                    if v_balance >= liability:
                        new_bal = v_balance - liability
                        self.db.save_simulation_bet(
                            event_name=payload.get("event_name", ""),
                            market_id=market_id,
                            market_name=payload.get("market_name", ""),
                            side=bet_type,
                            selection_id=selection_id,
                            selection_name=payload.get("runner_name", ""),
                            price=price,
                            stake=stake,
                            status="MATCHED",
                        )
                        self.db.increment_simulation_bet_count(new_bal)

                        self.bus.publish(
                            "QUICK_BET_SUCCESS",
                            {
                                "market_id": market_id,
                                "selection_id": selection_id,
                                "event_name": payload.get("event_name", ""),
                                "market_name": payload.get("market_name", ""),
                                "bet_type": bet_type,
                                "runner_name": payload.get("runner_name", ""),
                                "price": price,
                                "stake": stake,
                                "matched": stake,
                                "status": "MATCHED",
                                "new_balance": new_bal,
                                "sim": True,
                                "micro": False,
                            },
                        )
                    else:
                        self.bus.publish("QUICK_BET_FAILED", "Saldo virtuale insufficiente")
                    return

                client = self.client_getter()
                if not client:
                    raise Exception("Client non connesso")

                self.db.create_pending_saga(customer_ref, market_id, selection_id, payload)

                try:
                    if self._needs_micro_stake(stake):
                        result = self._execute_micro_stake(
                            client=client,
                            market_id=market_id,
                            selection_id=selection_id,
                            side=bet_type,
                            price=price,
                            stake=stake,
                            customer_ref=customer_ref,
                        )
                    else:
                        result = self._call_place_bet(
                            client=client,
                            market_id=market_id,
                            selection_id=selection_id,
                            side=bet_type,
                            price=price,
                            size=stake,
                            customer_ref=customer_ref,
                        )

                    reports = self._response_instruction_reports(result)

                    if self._response_status(result) == "SUCCESS":
                        self.db.mark_saga_reconciled(customer_ref)
                        matched = self._safe_sum_matched(reports)
                        status = self._compute_order_status(matched, stake)

                        self.db.save_bet(
                            event_name=payload.get("event_name", ""),
                            market_id=market_id,
                            market_name=payload.get("market_name", ""),
                            bet_type=bet_type,
                            selections=[
                                {
                                    "selectionId": selection_id,
                                    "runnerName": payload.get("runner_name", ""),
                                    "price": price,
                                    "stake": stake,
                                }
                            ],
                            total_stake=stake,
                            potential_profit=0.0,
                            status=status,
                        )

                        self.bus.publish(
                            "QUICK_BET_SUCCESS",
                            {
                                "market_id": market_id,
                                "selection_id": selection_id,
                                "event_name": payload.get("event_name", ""),
                                "market_name": payload.get("market_name", ""),
                                "bet_type": bet_type,
                                "runner_name": payload.get("runner_name", ""),
                                "price": price,
                                "stake": stake,
                                "matched": matched,
                                "status": status,
                                "sim": False,
                                "micro": self._needs_micro_stake(stake),
                            },
                        )
                    else:
                        self.db.mark_saga_failed(customer_ref)
                        self.db.save_bet(
                            event_name=payload.get("event_name", ""),
                            market_id=market_id,
                            market_name=payload.get("market_name", ""),
                            bet_type=bet_type,
                            selections=[
                                {
                                    "selectionId": selection_id,
                                    "runnerName": payload.get("runner_name", ""),
                                    "price": price,
                                    "stake": stake,
                                }
                            ],
                            total_stake=stake,
                            potential_profit=0.0,
                            status="FAILED",
                        )
                        self.bus.publish(
                            "QUICK_BET_FAILED",
                            f"Stato API: {self._response_status(result)}",
                        )

                except Exception as e:
                    is_recovered, recovered_reports = self._reconcile_orders(
                        client,
                        market_id,
                        customer_ref,
                    )

                    if is_recovered:
                        self.db.mark_saga_reconciled(customer_ref)
                        matched = self._safe_sum_matched(recovered_reports)
                        status = self._compute_order_status(matched, stake)

                        self.db.save_bet(
                            event_name=payload.get("event_name", ""),
                            market_id=market_id,
                            market_name=payload.get("market_name", ""),
                            bet_type=bet_type,
                            selections=[
                                {
                                    "selectionId": selection_id,
                                    "runnerName": payload.get("runner_name", ""),
                                    "price": price,
                                    "stake": stake,
                                }
                            ],
                            total_stake=stake,
                            potential_profit=0.0,
                            status=status,
                        )

                        self.bus.publish(
                            "QUICK_BET_SUCCESS",
                            {
                                "market_id": market_id,
                                "selection_id": selection_id,
                                "event_name": payload.get("event_name", ""),
                                "market_name": payload.get("market_name", ""),
                                "bet_type": bet_type,
                                "runner_name": payload.get("runner_name", ""),
                                "price": price,
                                "stake": stake,
                                "matched": matched,
                                "status": status,
                                "sim": False,
                                "micro": self._needs_micro_stake(stake),
                                "recovered": True,
                            },
                        )
                    else:
                        self.db.mark_saga_failed(customer_ref)
                        self.db.save_bet(
                            event_name=payload.get("event_name", ""),
                            market_id=market_id,
                            market_name=payload.get("market_name", ""),
                            bet_type=bet_type,
                            selections=[
                                {
                                    "selectionId": selection_id,
                                    "runnerName": payload.get("runner_name", ""),
                                    "price": price,
                                    "stake": stake,
                                }
                            ],
                            total_stake=stake,
                            potential_profit=0.0,
                            status="FAILED",
                        )

                        if isinstance(e, PermanentError):
                            self.bus.publish(
                                "SAFE_MODE_TRIGGER",
                                {"reason": "Circuit Breaker", "details": str(e)},
                            )

                        self.bus.publish("QUICK_BET_FAILED", f"Errore Rete: {str(e)}")

            finally:
                self._release_lock(customer_ref)

        self.executor.submit("engine_quick_bet", task)

    # =========================================================
    # DUTCHING
    # =========================================================

    def _handle_place_dutching(self, payload):
        def task():
            customer_ref = uuid.uuid4().hex[:32]
            if not self._acquire_lock(customer_ref):
                return

            try:
                if self.is_killed:
                    self.bus.publish("DUTCHING_FAILED", "SAFE MODE ATTIVO")
                    return

                market_id = payload["market_id"]
                bet_type = payload["bet_type"]
                results = payload["results"]
                sim_mode = bool(payload.get("simulation_mode", False))
                total_stake = float(payload["total_stake"])
                use_best_price = bool(payload.get("use_best_price", False))
                requested_size = sum(float(r.get("stake", 0) or 0) for r in results)

                if sim_mode:
                    sim_settings = self.db.get_simulation_settings()
                    v_balance = float(sim_settings.get("virtual_balance", 0.0) or 0.0)

                    total_risk = (
                        sum(
                            float(r.get("stake", 0) or 0)
                            * (float(r.get("price", 1.0) or 1.0) - 1.0)
                            for r in results
                        )
                        if bet_type == "LAY"
                        else total_stake
                    )

                    if v_balance >= total_risk:
                        new_bal = v_balance - total_risk
                        self.db.save_simulation_bet(
                            event_name=payload.get("event_name", ""),
                            market_id=market_id,
                            market_name=payload.get("market_name", ""),
                            side=bet_type,
                            status="MATCHED",
                            selections=results,
                            total_stake=total_stake,
                        )
                        self.db.increment_simulation_bet_count(new_bal)
                        self.bus.publish(
                            "DUTCHING_SUCCESS",
                            {
                                "sim": True,
                                "matched": requested_size,
                                "status": "MATCHED",
                                "total_stake": total_stake,
                                "new_balance": new_bal,
                            },
                        )
                    else:
                        self.bus.publish(
                            "DUTCHING_FAILED",
                            "Saldo virtuale insufficiente",
                        )
                    return

                client = self.client_getter()
                if not client:
                    raise Exception("Client non connesso")

                self.db.create_pending_saga(customer_ref, market_id, None, payload)

                try:
                    normal_instructions = []
                    micro_reports = []

                    best_price_map = {}
                    if use_best_price:
                        book = client.get_market_book(market_id)
                        if book and book.get("runners"):
                            for runner in book["runners"]:
                                sel_id = runner.get("selectionId")
                                ex = runner.get("ex", {})
                                if bet_type == "BACK":
                                    avail = ex.get("availableToBack", [])
                                    best_price_map[sel_id] = (
                                        avail[0].get("price", 1.01)
                                        if avail
                                        else 1.01
                                    )
                                else:
                                    avail = ex.get("availableToLay", [])
                                    best_price_map[sel_id] = (
                                        avail[0].get("price", 1000.0)
                                        if avail
                                        else 1000.0
                                    )

                    for r in results:
                        side = str(r.get("side", bet_type)).upper()
                        size = float(r.get("stake", 0) or 0)
                        target_price = float(
                            best_price_map.get(
                                r["selectionId"],
                                r.get("price", 0.0),
                            )
                        )

                        if self._needs_micro_stake(size):
                            micro_result = self._execute_micro_stake(
                                client=client,
                                market_id=market_id,
                                selection_id=r["selectionId"],
                                side=side,
                                price=target_price,
                                stake=size,
                                customer_ref=customer_ref,
                            )
                            micro_reports.extend(
                                self._response_instruction_reports(micro_result)
                            )
                        else:
                            normal_instructions.append(
                                self._build_limit_instruction(
                                    selection_id=r["selectionId"],
                                    side=side,
                                    price=target_price,
                                    size=size,
                                )
                            )

                    normal_reports = []
                    normal_status = "SUCCESS"

                    if normal_instructions:
                        normal_result = self._call_place_orders(
                            client=client,
                            market_id=market_id,
                            instructions=normal_instructions,
                            customer_ref=customer_ref,
                        )
                        normal_status = self._response_status(normal_result)
                        normal_reports = self._response_instruction_reports(normal_result)

                    all_reports = normal_reports + micro_reports

                    if normal_status == "SUCCESS":
                        self.db.mark_saga_reconciled(customer_ref)
                        matched = self._safe_sum_matched(all_reports)
                        status = self._compute_order_status(matched, requested_size)

                        self.db.save_bet(
                            event_name=payload.get("event_name", ""),
                            market_id=market_id,
                            market_name=payload.get("market_name", ""),
                            bet_type=bet_type,
                            selections=results,
                            total_stake=total_stake,
                            potential_profit=0.0,
                            status=status,
                        )
                        self.bus.publish(
                            "DUTCHING_SUCCESS",
                            {
                                "sim": False,
                                "matched": matched,
                                "status": status,
                                "total_stake": total_stake,
                            },
                        )
                    else:
                        self.db.mark_saga_failed(customer_ref)
                        self.db.save_bet(
                            event_name=payload.get("event_name", ""),
                            market_id=market_id,
                            market_name=payload.get("market_name", ""),
                            bet_type=bet_type,
                            selections=results,
                            total_stake=total_stake,
                            potential_profit=0.0,
                            status="FAILED",
                        )
                        self.bus.publish(
                            "DUTCHING_FAILED",
                            f"Stato API: {normal_status}",
                        )

                except Exception as e:
                    is_recovered, recovered_reports = self._reconcile_orders(
                        client,
                        market_id,
                        customer_ref,
                    )

                    if is_recovered:
                        self.db.mark_saga_reconciled(customer_ref)
                        matched = self._safe_sum_matched(recovered_reports)
                        status = self._compute_order_status(matched, requested_size)

                        self.db.save_bet(
                            event_name=payload.get("event_name", ""),
                            market_id=market_id,
                            market_name=payload.get("market_name", ""),
                            bet_type=bet_type,
                            selections=results,
                            total_stake=total_stake,
                            potential_profit=0.0,
                            status=status,
                        )
                        self.bus.publish(
                            "DUTCHING_SUCCESS",
                            {
                                "sim": False,
                                "matched": matched,
                                "status": status,
                                "total_stake": total_stake,
                                "recovered": True,
                            },
                        )
                    else:
                        self.db.mark_saga_failed(customer_ref)
                        self.db.save_bet(
                            event_name=payload.get("event_name", ""),
                            market_id=market_id,
                            market_name=payload.get("market_name", ""),
                            bet_type=bet_type,
                            selections=results,
                            total_stake=total_stake,
                            potential_profit=0.0,
                            status="FAILED",
                        )
                        if isinstance(e, PermanentError):
                            self.bus.publish(
                                "SAFE_MODE_TRIGGER",
                                {
                                    "reason": "Circuit Breaker",
                                    "details": str(e),
                                },
                            )
                        self.bus.publish(
                            "DUTCHING_FAILED",
                            f"Errore Rete: {str(e)}",
                        )
            finally:
                self._release_lock(customer_ref)

        self.executor.submit("engine_dutching", task)

    # =========================================================
    # CASHOUT
    # =========================================================

    def _handle_cashout(self, payload):
        def task():
            customer_ref = uuid.uuid4().hex[:32]
            if not self._acquire_lock(customer_ref):
                return

            try:
                if self.is_killed:
                    self.bus.publish("CASHOUT_FAILED", "SAFE MODE ATTIVO")
                    return

                client = self.client_getter()
                if not client:
                    raise Exception("Client non connesso")

                market_id = payload["market_id"]
                selection_id = payload["selection_id"]
                side = payload["side"]
                stake = float(payload["stake"])
                price = float(payload["price"])
                green_up = float(payload["green_up"])

                self.db.create_pending_saga(
                    customer_ref,
                    market_id,
                    selection_id,
                    payload,
                )

                try:
                    if self._needs_micro_stake(stake):
                        result = self._execute_micro_stake(
                            client=client,
                            market_id=market_id,
                            selection_id=selection_id,
                            side=side,
                            price=price,
                            stake=stake,
                            customer_ref=customer_ref,
                        )
                    else:
                        instructions = [
                            {
                                "selectionId": selection_id,
                                "side": side,
                                "orderType": "LIMIT",
                                "limitOrder": {
                                    "size": stake,
                                    "price": price,
                                    "persistenceType": "LAPSE",
                                },
                            }
                        ]
                        result = self._call_place_orders(
                            client=client,
                            market_id=market_id,
                            instructions=instructions,
                            customer_ref=customer_ref,
                        )

                    reports = self._response_instruction_reports(result)

                    if self._response_status(result) == "SUCCESS":
                        self.db.mark_saga_reconciled(customer_ref)
                        matched = self._safe_sum_matched(reports)
                        status = self._compute_order_status(matched, stake)

                        self.db.save_cashout_transaction(
                            market_id=market_id,
                            selection_id=selection_id,
                            original_bet_id="",
                            cashout_bet_id=customer_ref,
                            original_side="",
                            original_stake=0,
                            original_price=0,
                            cashout_side=side,
                            cashout_stake=stake,
                            cashout_price=price,
                            profit_loss=green_up,
                        )
                        self.bus.publish(
                            "CASHOUT_SUCCESS",
                            {
                                "green_up": green_up,
                                "matched": matched,
                                "status": status,
                                "micro": self._needs_micro_stake(stake),
                            },
                        )
                    else:
                        self.db.mark_saga_failed(customer_ref)
                        self.bus.publish(
                            "CASHOUT_FAILED",
                            f"Stato API: {self._response_status(result)}",
                        )

                except Exception as e:
                    is_recovered, recovered_reports = self._reconcile_orders(
                        client,
                        market_id,
                        customer_ref,
                    )

                    if is_recovered:
                        self.db.mark_saga_reconciled(customer_ref)
                        matched = self._safe_sum_matched(recovered_reports)
                        status = self._compute_order_status(matched, stake)

                        self.db.save_cashout_transaction(
                            market_id=market_id,
                            selection_id=selection_id,
                            original_bet_id="",
                            cashout_bet_id=customer_ref,
                            original_side="",
                            original_stake=0,
                            original_price=0,
                            cashout_side=side,
                            cashout_stake=stake,
                            cashout_price=price,
                            profit_loss=green_up,
                        )
                        self.bus.publish(
                            "CASHOUT_SUCCESS",
                            {
                                "green_up": green_up,
                                "matched": matched,
                                "status": status,
                                "recovered": True,
                            },
                        )
                    else:
                        self.db.mark_saga_failed(customer_ref)
                        if isinstance(e, PermanentError):
                            self.bus.publish(
                                "SAFE_MODE_TRIGGER",
                                {
                                    "reason": "Circuit Breaker Cashout",
                                    "details": str(e),
                                },
                            )
                        self.bus.publish(
                            "CASHOUT_FAILED",
                            f"Errore Rete: {str(e)}",
                        )
            finally:
                self._release_lock(customer_ref)

        self.executor.submit("engine_cashout", task)