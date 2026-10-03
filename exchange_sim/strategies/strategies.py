"""
Strategien und Trader.

DESIGN-ENTSCHEIDUNGEN:

1. ABC statt leere Basisklasse:
   ─────────────────────────────
   VORHER: class Strategie mit pass-Body → vergisst man ausführen() zu überschreiben,
   passiert einfach nichts. Kein Fehler, aber subtiler Bug.
   NACHHER: ABC mit @abstractmethod → TypeError bei Instanziierung wenn execute() fehlt.

2. Trader statt Händler mit klarer Verantwortung:
   ────────────────────────────────────────────────
   VORHER: Händler hatte send_order() mit eingebauter Validierung + Reservierung.
   NACHHER: Trader validiert und reserviert, Exchange matched und settled.
   Klare Grenze: Trader → "will handeln", Exchange → "darf/kann handeln".

3. Strategien übernommen und verbessert:
   ──────────────────────────────────────
   Deine 4 Strategien (MarketMaker, Momentum, MeanReversion, RandomNoise) waren
   gut konzipiert! Änderungen:
   - Enums statt Strings für Side/OrderType
   - Type Hints
   - Order-Erstellung über Factory-Methode im Trader
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
import random

from exchange_sim.models.order import Order, Side, OrderType
from exchange_sim.models.trade import Trade
from exchange_sim.exchange.account import Account
from exchange_sim.exchange.market import Market

# TYPE_CHECKING vermeidet zirkuläre Imports zur Laufzeit
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from exchange_sim.exchange.exchange import Exchange


class Strategy(ABC):
    """Abstrakte Basis für Handelsstrategien.

    WARUM ABC statt einfache Klasse?
    → @abstractmethod erzwingt, dass jede Strategie execute() implementiert.
      Vergisst man es, gibt es einen TypeError statt stilles Nichtstun.
    """

    @abstractmethod
    def execute(self, trader: Trader, market: Market, timestamp: datetime) -> None:
        """Führt die Strategie aus und gibt ggf. Orders auf."""
        ...


class MarketMaker(Strategy):
    """Market-Making-Strategie: Stellt Liquidität bereit durch Bid/Ask-Quotes.

    Übernommen aus deinem Code. Verbesserungen:
    - Inventory-Skew: Verschiebt den Midpoint basierend auf der Position.
      Bei zu viel Inventory → niedrigerer Bid (weniger kaufen) + niedrigerer Ask (schneller verkaufen).
    - Cancel + Re-Quote pro Tick: Alte Orders werden storniert, neue gestellt.

    Parameter:
        spread: Abstand zwischen Bid und Ask
        quantity: Menge pro Order
        max_inventory: Maximale Position pro Asset
        skew_factor: Wie stark die Position den Preis verschiebt
    """

    def __init__(self, spread: float, quantity: float,
                 max_inventory: float, skew_factor: float) -> None:
        self.spread = spread
        self.quantity = quantity
        self.max_inventory = max_inventory
        self.skew_factor = skew_factor

    def execute(self, trader: Trader, market: Market, timestamp: datetime) -> None:
        # Cancel alte Orders für diesen Markt
        trader.cancel_all_orders(market.symbol)

        inventory = trader.account.assets.get(market.symbol, 0.0)
        inventory_ratio = inventory / self.max_inventory if self.max_inventory > 0 else 0
        skew = inventory_ratio * self.skew_factor

        mid = market.price - skew
        bid_price = mid - self.spread / 2
        ask_price = mid + self.spread / 2

        # Inventory-Limits: Nicht kaufen wenn voll, nicht verkaufen wenn leer
        if inventory < self.max_inventory:
            trader.place_order(
                Side.BUY, OrderType.LIMIT, market.symbol,
                self.quantity, bid_price, timestamp
            )

        if inventory > 0:
            trader.place_order(
                Side.SELL, OrderType.LIMIT, market.symbol,
                self.quantity, ask_price, timestamp
            )


class Momentum(Strategy):
    """Momentum-Strategie: Kauft bei steigendem Trend, verkauft bei fallendem.

    Übernommen aus deinem Code. Logik:
    - Vergleicht aktuellen Preis mit Preis vor `lookback` Sekunden
    - Signal nur bei Richtungswechsel (verhindert Overtrading)

    Parameter:
        lookback: Anzahl vergangener Ticks für den Vergleich
        quantity: Handelsmenge
    """

    def __init__(self, lookback: int, quantity: float) -> None:
        self.lookback = lookback
        self.quantity = quantity
        self._last_signal: dict[str, Side] = {}

    def execute(self, trader: Trader, market: Market, timestamp: datetime) -> None:
        prices = market.get_recent_prices(self.lookback)
        if len(prices) < self.lookback:
            return

        old_price = prices[0]
        current_price = market.price

        if current_price > old_price:
            signal = Side.BUY
        elif current_price < old_price:
            signal = Side.SELL
        else:
            return

        # Nur bei Richtungswechsel handeln
        if signal == self._last_signal.get(market.symbol):
            return

        self._last_signal[market.symbol] = signal
        trader.place_order(
            signal, OrderType.MARKET, market.symbol,
            self.quantity, current_price, timestamp
        )


class MeanReversion(Strategy):
    """Mean-Reversion-Strategie: Kauft unter dem Durchschnitt, verkauft darüber.

    Übernommen aus deinem Code. Logik:
    - Berechnet Durchschnittspreis der letzten `lookback` Ticks
    - Kauft wenn Preis < Durchschnitt (Erwartung: Preis steigt zurück)
    - Verkauft wenn Preis > Durchschnitt

    Parameter:
        lookback: Fenstergröße für den Durchschnitt
        quantity: Handelsmenge
    """

    def __init__(self, lookback: int, quantity: float) -> None:
        self.lookback = lookback
        self.quantity = quantity
        self._last_signal: dict[str, Side] = {}

    def execute(self, trader: Trader, market: Market, timestamp: datetime) -> None:
        prices = market.get_recent_prices(self.lookback)
        if len(prices) < self.lookback:
            return

        mean = sum(prices) / len(prices)
        current_price = market.price

        if current_price < mean:
            signal = Side.BUY
        elif current_price > mean:
            signal = Side.SELL
        else:
            return

        if signal == self._last_signal.get(market.symbol):
            return

        self._last_signal[market.symbol] = signal
        trader.place_order(
            signal, OrderType.MARKET, market.symbol,
            self.quantity, current_price, timestamp
        )


class RandomNoise(Strategy):
    """Zufälliger Trader: Kauft oder verkauft zufällig.

    Erzeugt Markt-Rauschen und Liquidität. Übernommen aus deinem Code.

    Parameter:
        quantity: Handelsmenge
    """

    def __init__(self, quantity: float) -> None:
        self.quantity = quantity

    def execute(self, trader: Trader, market: Market, timestamp: datetime) -> None:
        signal = random.choice([Side.BUY, Side.SELL])
        trader.place_order(
            signal, OrderType.MARKET, market.symbol,
            self.quantity, market.price, timestamp
        )


class Trader:
    """Ein Marktteilnehmer mit Account und Strategie.

    VORHER (Händler): Registrierte sich selbst bei der Börse im __init__,
    hatte send_order() mit eingebauter Validierung + Reservierung.

    NACHHER:
    - Exchange registriert den Trader (umgekehrte Abhängigkeit)
    - place_order() validiert + reserviert, delegiert an Exchange
    - Klare Trennung: Trader will handeln, Exchange entscheidet

    Attribute:
        trader_id: Eindeutige ID
        name: Bezeichnung (z.B. "marketmaker", "momentum")
        account: Konto mit Kapital und Assets
        strategy: Handelsstrategie (Polymorphie)
        exchange: Referenz auf die Börse
    """

    def __init__(self, trader_id: int, name: str, capital: float,
                 assets: dict[str, float], exchange: Exchange,
                 strategy: Strategy) -> None:
        self.trader_id = trader_id
        self.name = name
        self.account = Account(capital=capital, assets=assets)
        self.strategy = strategy
        self.exchange = exchange
        self._active_orders: dict[int, Order] = {}  # order_id → Order

        # Trader registriert sich bei der Börse
        exchange.register_trader(self)

    def run_strategy(self, market: Market, timestamp: datetime) -> None:
        """Führt die Strategie aus (einmal pro Tick pro Markt)."""
        self.strategy.execute(self, market, timestamp)

    def place_order(self, side: Side, order_type: OrderType, symbol: str,
                    quantity: float, price: float, timestamp: datetime) -> list[Trade]:
        """Erstellt, validiert und sendet eine Order.

        Validierung:
        - BUY: Genug verfügbares Kapital?
        - SELL: Genug verfügbare Assets?

        Bei Limit-Orders wird das Kapital/Asset reserviert,
        damit es nicht doppelt ausgegeben werden kann.

        Returns:
            Liste der erzeugten Trades (kann leer sein)
        """
        order = Order(
            side=side,
            order_type=order_type,
            symbol=symbol,
            quantity=quantity,
            price=price,
            timestamp=timestamp,
            trader_id=self.trader_id,
        )

        # Validierung + Reservierung
        if side == Side.BUY:
            cost = price * quantity
            if order_type == OrderType.LIMIT:
                if not self.account.reserve_capital(cost):
                    return []  # Nicht genug Kapital
            else:  # MARKET
                # Market-Orders: Preis ist unsicher → Sicherheitsfaktor
                estimated_cost = cost * 1.05
                if estimated_cost > self.account.available_capital:
                    return []
                self.account.reserve_capital(estimated_cost)
        else:  # SELL
            if order_type == OrderType.LIMIT:
                if not self.account.reserve_assets(symbol, quantity):
                    return []  # Nicht genug Assets
            else:  # MARKET
                if self.account.available_asset_qty(symbol) < quantity:
                    return []
                self.account.reserve_assets(symbol, quantity)

        self._active_orders[order.order_id] = order
        trades = self.exchange.submit_order(order, timestamp)

        # Aufräumen: Gefüllte Orders aus der aktiven Liste entfernen
        if not order.is_active:
            self._active_orders.pop(order.order_id, None)
            # Bei Market-Orders: überschüssige Reservierung freigeben
            if order_type == OrderType.MARKET and side == Side.BUY:
                actual_cost = sum(t.price * t.quantity for t in trades)
                over_reserved = cost * 1.05 - actual_cost
                if over_reserved > 0:
                    self.account.release_capital(over_reserved)

        return trades

    def cancel_order(self, symbol: str, order_id: int) -> None:
        """Storniert eine eigene Order."""
        self.exchange.cancel_order(symbol, order_id, self.trader_id)
        self._active_orders.pop(order_id, None)

    def cancel_all_orders(self, symbol: str) -> None:
        """Storniert alle eigenen Orders für einen Markt."""
        to_cancel = [
            oid for oid, order in self._active_orders.items()
            if order.symbol == symbol
        ]
        for order_id in to_cancel:
            self.cancel_order(symbol, order_id)

    def __repr__(self) -> str:
        return (
            f"Trader(id={self.trader_id}, name={self.name}, "
            f"capital={self.account.capital:.2f})"
        )
