"""
Trading Engine (UI-Agnostic)
Motore finanziario puro. Gestisce l'intero ciclo di vita degli ordini (Real e Virtual).
Nessuna dipendenza grafica. Interagisce solo con API, DB e EventBus.
"""

__all__ = ["TradingEngine"]


class TradingEngine:
    def __init__(self, bus, db, client_getter, executor):
        self.bus = bus
        self.db = db
        self.client_getter = (
            client_getter  # Lambda per ottenere il client sempre aggiornato
        )
        self.executor = executor

        # Sottoscrizioni ai comandi operativi
        self.bus.subscribe("CMD_QUICK_BET", self._handle_quick_bet)
        self.bus.subscribe("CMD_PLACE_DUTCHING", self._handle_place_dutching)
        self.bus.subscribe("CMD_EXECUTE_CASHOUT", self._handle_cashout)

    def _handle_quick_bet(self, payload):
        """Piazza una scommessa singola rapida."""

        def task():
            runner = payload["runner"]
            bet_type = payload["bet_type"]
            price = payload["price"]
            stake = payload["stake"]
            sim_mode = payload["simulation_mode"]
            market = payload["market"]

            if sim_mode:
                try:
                    commission = 0.045
                    if bet_type == "BACK":
                        profit = (stake * (price - 1)) * (1 - commission)
                        liability = stake
                    else:
                        profit = stake * (1 - commission)
                        liability = stake * (price - 1)

                    settings = self.db.get_simulation_settings()
                    current_balance = settings.get("virtual_balance", 10000.0)

                    if liability > current_balance:
                        self.bus.publish(
                            "QUICK_BET_FAILED",
                            f"Saldo virtuale insufficiente.\nSaldo: {current_balance}\nRichiesto: {liability}",
                        )
                        return

                    new_balance = current_balance - liability
                    self.db.increment_simulation_bet_count(new_balance)

                    self.db.save_simulation_bet(
                        event_name=market.get("eventName", "Quick Bet"),
                        market_id=market["marketId"],
                        market_name=market.get("marketName", ""),
                        side=bet_type,
                        selection_id=str(runner["selectionId"]),
                        selection_name=runner["runnerName"],
                        price=price,
                        stake=stake,
                        status="MATCHED",
                    )
                    self.bus.publish(
                        "QUICK_BET_SUCCESS",
                        {
                            "runner_name": runner["runnerName"],
                            "price": price,
                            "stake": stake,
                            "new_balance": new_balance,
                            "sim": True,
                        },
                    )
                except Exception as e:
                    self.bus.publish("QUICK_BET_FAILED", str(e))
            else:
                try:
                    client = self.client_getter()
                    if not client:
                        raise Exception("Client non connesso")

                    result = client.place_bet(
                        market_id=market["marketId"],
                        selection_id=runner["selectionId"],
                        side=bet_type,
                        price=price,
                        size=stake,
                        persistence_type="LAPSE",
                    )

                    if result.get("status") == "SUCCESS":
                        matched = sum(
                            r.get("sizeMatched", 0)
                            for r in result.get("instructionReports", [])
                        )
                        self.db.save_bet(
                            event_name=market.get("eventName", ""),
                            market_id=market["marketId"],
                            market_name=market.get("marketName", ""),
                            bet_type=bet_type,
                            selections=runner["runnerName"],
                            total_stake=stake,
                            potential_profit=(
                                (stake * (price - 1)) * 0.955
                                if bet_type == "BACK"
                                else stake * 0.955
                            ),
                            status="MATCHED" if matched > 0 else "UNMATCHED",
                        )
                        self.bus.publish(
                            "QUICK_BET_SUCCESS",
                            {
                                "runner_name": runner["runnerName"],
                                "price": price,
                                "matched": matched,
                                "sim": False,
                            },
                        )
                    else:
                        self.bus.publish(
                            "QUICK_BET_FAILED", f"Stato API: {result.get('status')}"
                        )
                except Exception as e:
                    self.bus.publish("QUICK_BET_FAILED", str(e))

        self.executor.submit("engine_quick_bet", task)

    def _handle_place_dutching(self, payload):
        """Piazza un blocco di scommesse dutching."""

        def task():
            market = payload["market"]
            event = payload["event"]
            results = payload["results"]
            bet_type = payload["bet_type"]
            total_stake = payload["total_stake"]
            use_best_price = payload["use_best_price"]
            sim_mode = payload["simulation_mode"]

            if sim_mode:
                try:
                    sim_settings = self.db.get_simulation_settings()
                    virtual_balance = sim_settings.get("virtual_balance", 0)
                    new_balance = virtual_balance - total_stake
                    self.db.increment_simulation_bet_count(new_balance)

                    selections_info = [
                        {
                            "name": r.get("runnerName", "Unknown"),
                            "price": r["price"],
                            "stake": r["stake"],
                        }
                        for r in results
                    ]

                    self.db.save_simulation_bet(
                        event_name=event["name"],
                        market_id=market["marketId"],
                        market_name=market.get("marketName", ""),
                        side=bet_type,
                        selections=selections_info,
                        total_stake=total_stake,
                        potential_profit=results[0]["profitIfWins"] if results else 0,
                    )
                    self.bus.publish(
                        "DUTCHING_SUCCESS",
                        {
                            "sim": True,
                            "total_stake": total_stake,
                            "profit": results[0]["profitIfWins"] if results else 0,
                            "new_balance": new_balance,
                        },
                    )
                except Exception as e:
                    self.bus.publish("DUTCHING_FAILED", str(e))
                return

            try:
                client = self.client_getter()
                if not client:
                    raise Exception("Client non connesso")

                instructions = []
                market_id = market["marketId"]

                if use_best_price:
                    book = client.get_market_book(market_id)
                    current_prices = {}
                    if book and book.get("runners"):
                        for runner in book["runners"]:
                            sel_id = runner.get("selectionId")
                            ex = runner.get("ex", {})
                            if bet_type == "BACK":
                                backs = ex.get("availableToBack", [])
                                if backs:
                                    current_prices[sel_id] = backs[0].get("price", 1.01)
                            else:
                                lays = ex.get("availableToLay", [])
                                if lays:
                                    current_prices[sel_id] = lays[0].get("price", 1000)

                    for r in results:
                        price = current_prices.get(r["selectionId"], r["price"])
                        instructions.append(
                            {
                                "selectionId": r["selectionId"],
                                "side": bet_type,
                                "price": price,
                                "size": r["stake"],
                            }
                        )
                else:
                    instructions = [
                        {
                            "selectionId": r["selectionId"],
                            "side": bet_type,
                            "price": r["price"],
                            "size": r["stake"],
                        }
                        for r in results
                    ]

                result = client.place_bets(market_id, instructions)
                reports = result.get("instructionReports", [])

                all_matched = all(
                    r.get("status") == "SUCCESS" and r.get("sizeMatched", 0) > 0
                    for r in reports
                )
                any_matched = any(r.get("sizeMatched", 0) > 0 for r in reports)

                if result.get("status") == "SUCCESS":
                    bet_status = (
                        "MATCHED"
                        if all_matched
                        else "PARTIALLY_MATCHED" if any_matched else "PENDING"
                    )
                elif result.get("status") == "FAILURE":
                    bet_status = "FAILED"
                else:
                    bet_status = result.get("status", "UNKNOWN")

                selections_with_names = []
                for i, r in enumerate(results):
                    report = reports[i] if i < len(reports) else {}
                    selections_with_names.append(
                        {
                            "runnerName": r.get("runnerName", "Unknown"),
                            "selectionId": r["selectionId"],
                            "price": r["price"],
                            "stake": r["stake"],
                            "sizeMatched": report.get("sizeMatched", 0),
                            "betId": report.get("betId"),
                            "instructionStatus": report.get("status", "UNKNOWN"),
                        }
                    )

                self.db.save_bet(
                    event["name"],
                    market["marketId"],
                    market.get("marketName", ""),
                    bet_type,
                    selections_with_names,
                    total_stake,
                    results[0]["profitIfWins"] if results else 0,
                    bet_status,
                )

                if result.get("status") == "SUCCESS":
                    matched = sum(r.get("sizeMatched", 0) for r in reports)
                    self.bus.publish(
                        "DUTCHING_SUCCESS", {"sim": False, "matched": matched}
                    )
                else:
                    self.bus.publish(
                        "DUTCHING_FAILED", f"Stato API: {result.get('status')}"
                    )
            except Exception as e:
                self.bus.publish("DUTCHING_FAILED", str(e))

        self.executor.submit("engine_dutching", task)

    def _handle_cashout(self, payload):
        """Esegue il Cashout in sicurezza."""

        def task():
            try:
                client = self.client_getter()
                if not client:
                    raise Exception("Client non connesso")

                market_id = payload["market_id"]
                selection_id = payload["selection_id"]
                side = payload["side"]
                stake = payload["stake"]
                price = payload["price"]
                bet_id = payload["bet_id"]
                green_up = payload["green_up"]
                original_pos = payload["original_pos"]

                result = client.execute_cashout(
                    market_id, selection_id, side, stake, price
                )

                if result.get("status") == "SUCCESS":
                    self.db.save_cashout_transaction(
                        market_id=market_id,
                        selection_id=selection_id,
                        original_bet_id=bet_id,
                        cashout_bet_id=result.get("betId"),
                        original_side=original_pos["side"],
                        original_stake=original_pos["stake"],
                        original_price=original_pos["price"],
                        cashout_side=side,
                        cashout_stake=stake,
                        cashout_price=result.get("averagePriceMatched") or price,
                        profit_loss=green_up,
                    )
                    self.bus.publish("CASHOUT_SUCCESS", {"green_up": green_up})
                elif result.get("status") == "ERROR":
                    self.bus.publish(
                        "CASHOUT_FAILED",
                        f"Errore: {result.get('error', 'Sconosciuto')}",
                    )
                else:
                    self.bus.publish(
                        "CASHOUT_FAILED", f"Stato API: {result.get('status')}"
                    )
            except Exception as e:
                self.bus.publish("CASHOUT_FAILED", str(e))

        self.executor.submit("engine_cashout", task)

