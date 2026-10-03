"""
Matching-Engine – separiert vom Orderbuch.

DESIGN-ENTSCHEIDUNGEN:

1. Warum separate Klasse statt Methode im Orderbuch?
   ──────────────────────────────────────────────────
   Im alten Code war match() eine Methode von Orderbuch. Das vermischt
   Datenstruktur (wo stehen die Orders?) mit Algorithmus (wie werden sie
   gematcht?). Trennung ermöglicht:
   - Unabhängiges Testen von Orderbuch-Operationen vs. Matching-Logik
   - Austauschbarer Matching-Algorithmus (z.B. Pro-Rata statt Price-Time)

2. Vollständiges Matching für Market-Orders:
   ──────────────────────────────────────────
   VORHER: Market-Order matcht nur gegen EINE Gegenorder → Menge geht verloren
   NACHHER: While-Loop bis remaining == 0 oder keine Liquidität mehr

3. Trade-Preis-Bestimmung:
   ────────────────────────
   Der Trade wird immer zum Preis der ruhenden Order (maker) ausgeführt.
   LIMIT buy 100 @ 50 trifft LIMIT sell 80 @ 48 → Trade @ 48 (Preis der Ask)
   Das ist Standard bei allen Börsen und fair für den Maker.
"""

from __future__ import annotations

from datetime import datetime

from exchange_sim.models.order import Order, Side, OrderType
from exchange_sim.models.trade import Trade
from exchange_sim.orderbook.orderbook import OrderBook


class MatchingEngine:
    """Price-Time-Priority Matching-Engine.

    Verarbeitet eingehende Orders gegen das Orderbuch und erzeugt Trades.
    Market-Orders werden sofort gegen ruhende Limit-Orders gematcht.
    Limit-Orders werden erst gegen Gegenorders gematcht, dann ins Buch eingefügt.

    Matching-Algorithmus:
    1. Eingehende Order (aggressor) gegen beste Gegenorder (ruhend) prüfen
    2. Bei Preisübereinstimmung: Trade erzeugen mit min(aggressor.remaining, ruhend.remaining)
    3. Ruhende Order aktualisieren (Partial Fill) oder entfernen (Full Fill)
    4. Wiederholen bis: aggressor vollständig gefüllt ODER keine passenden Gegenorders
    5. Falls aggressor eine Limit-Order ist und nicht vollständig gefüllt: ins Buch einfügen
    """

    def __init__(self, orderbook: OrderBook) -> None:
        self._book = orderbook

    def process(self, order: Order, timestamp: datetime) -> list[Trade]:
        """Verarbeitet eine eingehende Order und gibt erzeugte Trades zurück.

        Args:
            order: Die eingehende Order (aggressor)
            timestamp: Zeitpunkt der Verarbeitung

        Returns:
            Liste der erzeugten Trades (kann leer sein)
        """
        trades = self._match(order, timestamp)

        # Nicht vollständig gefüllte Limit-Orders kommen ins Buch
        if order.order_type == OrderType.LIMIT and order.is_active:
            self._book.add(order)

        return trades

    def _match(self, aggressor: Order, timestamp: datetime) -> list[Trade]:
        """Matcht eine aggressor-Order gegen die Gegenseite des Orderbuchs.

        VORHER (dein Code):
          Market-Orders → nur 1 Match, dann return
          Limit-Orders → while-Loop, aber Market/Limit-Logik dupliziert

        NACHHER: Ein einheitlicher While-Loop für beide Order-Typen.
        Der einzige Unterschied: Limit-Orders prüfen zusätzlich den Preis.
        """
        trades: list[Trade] = []
        contra_side = Side.SELL if aggressor.side == Side.BUY else Side.BUY

        while aggressor.remaining_qty > 0:
            resting = self._book._peek_best(contra_side)
            if resting is None:
                break  # Keine Gegenorders mehr

            # Preis-Check: Nur für Limit-Orders relevant
            if aggressor.order_type == OrderType.LIMIT:
                if not self._prices_cross(aggressor, resting):
                    break  # Preise überschneiden sich nicht → kein Match

            # Match gefunden → Trade erzeugen
            fill_qty = min(aggressor.remaining_qty, resting.remaining_qty)

            # Trade-Preis = Preis der ruhenden Order (maker-price)
            trade_price = resting.price

            trade = Trade(
                price=trade_price,
                quantity=fill_qty,
                buy_order_id=aggressor.order_id if aggressor.side == Side.BUY else resting.order_id,
                sell_order_id=aggressor.order_id if aggressor.side == Side.SELL else resting.order_id,
                buyer_id=aggressor.trader_id if aggressor.side == Side.BUY else resting.trader_id,
                seller_id=aggressor.trader_id if aggressor.side == Side.SELL else resting.trader_id,
                symbol=aggressor.symbol,
                timestamp=timestamp,
            )
            trades.append(trade)

            # Orders aktualisieren
            aggressor.fill(fill_qty)
            resting.fill(fill_qty)

            # Level-Qty aktualisieren
            self._book._update_level_qty(resting, fill_qty)

            # Vollständig gefüllte ruhende Order aus dem Buch entfernen
            if not resting.is_active:
                self._book._pop_best(contra_side)

        return trades

    @staticmethod
    def _prices_cross(aggressor: Order, resting: Order) -> bool:
        """Prüft ob sich die Preise überschneiden (Match möglich).

        BUY aggressor: aggressor.price >= resting.price (Käufer zahlt mindestens Ask)
        SELL aggressor: aggressor.price <= resting.price (Verkäufer akzeptiert höchstens Bid)
        """
        if aggressor.side == Side.BUY:
            return aggressor.price >= resting.price
        else:
            return aggressor.price <= resting.price
