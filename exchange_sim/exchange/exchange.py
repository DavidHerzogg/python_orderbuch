"""
Exchange (Börse) – zentrale Koordination.

DESIGN-ENTSCHEIDUNGEN:

1. Exchange als Fassade:
   ─────────────────────
   VORHER: Börse leitete Orders weiter und suchte linear nach dem Markt.
   NACHHER: Exchange nutzt ein dict[symbol, Market] statt list[Market].
   Markt-Lookup ist O(1) statt O(n). Bei 3 Märkten irrelevant,
   aber bei 100+ Märkten ein echter Unterschied.

2. Settlement in Exchange:
   ────────────────────────
   Exchange kennt alle Trader und ihre Accounts. Nach dem Matching
   führt Exchange das Settlement durch: Account.settle_trade()
   für beide Seiten des Trades. Das ist sauberer als wenn der Trade
   selbst die Accounts manipuliert.

3. Trader-Verwaltung:
   ───────────────────
   VORHER: Händler registriert sich selbst bei der Börse im __init__.
   NACHHER: Exchange.register_trader() – die Börse kontrolliert,
   wer handeln darf. Umgekehrte Abhängigkeit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from exchange_sim.models.order import Order, Side, OrderType
from exchange_sim.models.trade import Trade
from exchange_sim.exchange.market import Market

if TYPE_CHECKING:
    from exchange_sim.strategies.strategies import Trader


class Exchange:
    """Zentrale Koordination: nimmt Orders entgegen, leitet an Märkte weiter,
    führt Settlement durch.

    VORHER (Börse): list[Market] → lineare Suche O(n)
    NACHHER: dict[symbol, Market] → O(1) Lookup
    """

    def __init__(self, markets: list[Market]) -> None:
        # dict statt list: O(1) Markt-Lookup statt O(n)
        self._markets: dict[str, Market] = {m.symbol: m for m in markets}
        self._traders: dict[int, Trader] = {}
        self.is_open: bool = False

    @property
    def markets(self) -> list[Market]:
        """Alle Märkte als Liste (für Iteration)."""
        return list(self._markets.values())

    @property
    def symbols(self) -> list[str]:
        return list(self._markets.keys())

    def get_market(self, symbol: str) -> Optional[Market]:
        return self._markets.get(symbol)

    def register_trader(self, trader: Trader) -> None:
        """Registriert einen Trader an der Börse."""
        self._traders[trader.trader_id] = trader

    def get_trader(self, trader_id: int) -> Optional[Trader]:
        return self._traders.get(trader_id)

    @property
    def traders(self) -> list[Trader]:
        return list(self._traders.values())

    def submit_order(self, order: Order, timestamp: datetime) -> list[Trade]:
        """Nimmt eine Order entgegen, matcht sie und führt Settlement durch.

        Ablauf:
        1. Validierung (Börse offen? Markt existiert?)
        2. Weiterleitung an Market → MatchingEngine
        3. Settlement: Accounts beider Seiten aktualisieren

        Returns:
            Liste der erzeugten Trades (leer wenn keine Matches)
        """
        if not self.is_open:
            return []

        market = self._markets.get(order.symbol)
        if market is None:
            return []

        trades = market.submit_order(order, timestamp)

        # Settlement: Accounts aktualisieren
        for trade in trades:
            self._settle(trade)

        return trades

    def cancel_order(self, symbol: str, order_id: int, trader_id: int) -> Optional[Order]:
        """Storniert eine Order. Gibt reserviertes Kapital/Assets frei.

        Args:
            symbol: Markt-Symbol
            order_id: ID der zu stornierenden Order
            trader_id: ID des Traders (zur Autorisierung)

        Returns:
            Die stornierte Order, oder None bei Fehler
        """
        market = self._markets.get(symbol)
        if market is None:
            return None

        cancelled = market.cancel_order(order_id)
        if cancelled is None:
            return None

        # Autorisierung: Nur eigene Orders stornieren
        if cancelled.trader_id != trader_id:
            # Rückgängig machen – Order wieder ins Buch
            market.orderbook.add(cancelled)
            cancelled.status = cancelled.status  # Reset
            return None

        # Reservierungen freigeben
        trader = self._traders.get(trader_id)
        if trader is not None:
            if cancelled.side == Side.BUY:
                cost = cancelled.price * cancelled.remaining_qty
                trader.account.release_capital(cost)
            else:
                trader.account.release_assets(cancelled.symbol, cancelled.remaining_qty)

        return cancelled

    def _settle(self, trade: Trade) -> None:
        """Führt das Settlement für beide Seiten eines Trades durch.

        Settlement = Kontobuchung:
        - Käufer: Kapital ab, Assets rauf
        - Verkäufer: Kapital rauf, Assets ab
        """
        buyer = self._traders.get(trade.buyer_id)
        seller = self._traders.get(trade.seller_id)

        if buyer is not None:
            buyer.account.settle_trade(trade, trade.buyer_id)
        if seller is not None:
            seller.account.settle_trade(trade, trade.seller_id)

    def record_prices(self, timestamp: datetime) -> None:
        """Zeichnet den aktuellen Preis aller Märkte auf."""
        for market in self._markets.values():
            market.record_price(timestamp)

    def __repr__(self) -> str:
        return (
            f"Exchange(markets={list(self._markets.keys())}, "
            f"traders={len(self._traders)}, open={self.is_open})"
        )
