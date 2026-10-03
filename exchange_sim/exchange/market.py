"""
Market und Candle.

DESIGN-ENTSCHEIDUNGEN:

1. Market besitzt OrderBook + MatchingEngine (Komposition):
   ─────────────────────────────────────────────────────────
   VORHER: Market hatte ein Orderbuch, Matching war im Orderbuch.
   NACHHER: Market hält OrderBook + MatchingEngine als Komposition.
   Market ist der Koordinator: nimmt Orders entgegen, leitet sie an die
   MatchingEngine weiter, verarbeitet die resultierenden Trades.

2. Candle-Logik übernommen und leicht verbessert:
   ────────────────────────────────────────────────
   Deine OHLCV-Candle-Logik war gut! Ich übernehme sie mit dataclass
   statt __init__-Boilerplate.

3. Preis-Historie als deque mit maxlen:
   ─────────────────────────────────────
   VORHER: Unbegrenzte Liste, wächst mit jedem Tick (86.400 Einträge/Tag).
   NACHHER: deque(maxlen=N) → automatisches Vergessen alter Daten.
   Strategien brauchen typisch nur die letzten 1-30 Minuten.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from exchange_sim.models.order import Order
from exchange_sim.models.trade import Trade
from exchange_sim.orderbook.orderbook import OrderBook
from exchange_sim.orderbook.matching import MatchingEngine


@dataclass
class Candle:
    """OHLCV-Kerze für eine Zeitperiode.

    Übernommen aus deinem Code, jetzt als dataclass.
    """
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def update(self, price: float, qty: float) -> None:
        """Aktualisiert die Kerze mit einem neuen Trade."""
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += qty


class Market:
    """Ein handelbarer Markt (z.B. XAUUSD).

    Koordiniert OrderBook, MatchingEngine und Preis-Tracking.
    Übernimmt dein Market-Konzept, aber mit sauberer Komposition.

    Attribute:
        symbol: Markt-Bezeichnung
        price: Letzter Handelspreis
        orderbook: Das Orderbuch für diesen Markt
        engine: Die Matching-Engine für diesen Markt
    """

    # Maximale Anzahl gespeicherter Preis-Punkte.
    # 7.200 = 2 Stunden bei 1-Sekunden-Ticks. Reicht für alle Strategien.
    MAX_PRICE_HISTORY = 7_200

    def __init__(self, symbol: str, initial_price: float) -> None:
        self.symbol = symbol
        self.price = initial_price
        self.orderbook = OrderBook(symbol)
        self.engine = MatchingEngine(self.orderbook)
        self.candles: list[Candle] = []
        # deque statt list: automatisches Vergessen alter Daten
        self.price_history: deque[tuple[datetime, float]] = deque(
            maxlen=self.MAX_PRICE_HISTORY
        )

    def submit_order(self, order: Order, timestamp: datetime) -> list[Trade]:
        """Verarbeitet eine Order über die MatchingEngine.

        Ablauf:
        1. MatchingEngine matcht die Order gegen Gegenorders
        2. Für jeden erzeugten Trade: Preis aktualisieren + Candle updaten
        3. Nicht gefüllte Limit-Orders wurden von der Engine ins Buch eingefügt

        Returns:
            Liste der erzeugten Trades
        """
        trades = self.engine.process(order, timestamp)
        for trade in trades:
            self._on_trade(trade, timestamp)
        return trades

    def cancel_order(self, order_id: int) -> Optional[Order]:
        """Storniert eine Order im Orderbuch."""
        return self.orderbook.cancel(order_id)

    def record_price(self, timestamp: datetime) -> None:
        """Zeichnet den aktuellen Preis auf (einmal pro Tick)."""
        self.price_history.append((timestamp, self.price))

    def _on_trade(self, trade: Trade, timestamp: datetime) -> None:
        """Callback nach einem Trade: Preis und Candle aktualisieren."""
        self.price = trade.price

        # Candle-Logik (übernommen aus deinem Code)
        candle_time = timestamp.replace(second=0, microsecond=0)

        if not self.candles or self.candles[-1].time != candle_time:
            self.candles.append(Candle(
                time=candle_time,
                open=trade.price,
                high=trade.price,
                low=trade.price,
                close=trade.price,
                volume=trade.quantity,
            ))
        else:
            self.candles[-1].update(trade.price, trade.quantity)

    def get_recent_prices(self, n: int) -> list[float]:
        """Gibt die letzten N Preise zurück (für Strategien)."""
        # Slicing auf deque ist O(k), aber k ist typisch klein (< 1800)
        history = list(self.price_history)
        return [p for _, p in history[-n:]]

    def __repr__(self) -> str:
        return f"Market({self.symbol} @ {self.price:.2f})"
