"""
Account mit Settlement-Logik.

DESIGN-ENTSCHEIDUNGEN:

1. Settlement separiert von Trade:
   ────────────────────────────────
   VORHER: Trade.execute() manipuliert direkt Account-Felder (Kapital, Assets).
   Das verletzt Single Responsibility – ein Trade ist ein Datum, kein Aktor.
   Account-Logik war über Trade und Händler verstreut.

   NACHHER: Account.settle_trade() ist die einzige Methode die Account-Felder ändert.
   Klarer Verantwortlicher, leichter zu testen und zu debuggen.

2. Reservierungssystem:
   ─────────────────────
   Dein Reservierungssystem (reserved_kapital, reserved_assets) war eine gute Idee!
   Es verhindert, dass ein Trader mehr ausgibt als er hat, wenn mehrere Limit-Orders
   gleichzeitig offen sind. Ich übernehme das Konzept, kapsle es aber sauberer.

3. available_capital / available_assets als Properties:
   ──────────────────────────────────────────────────────
   Statt jedes Mal `kapital - reserved_kapital` zu rechnen, gibt es eine Property.
   Liest sich wie ein Attribut, berechnet aber immer den aktuellen Wert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from exchange_sim.models.trade import Trade


@dataclass
class Account:
    """Konto eines Händlers mit Kapital, Assets und Reservierungen.

    Das Reservierungssystem stellt sicher, dass offene Limit-Orders
    nicht mehr Kapital/Assets beanspruchen als verfügbar ist.

    Beispiel:
        Kapital: 10.000, Reserviert: 3.000 → Verfügbar: 7.000
        Neue Limit-Buy-Order über 5.000 → ok (5.000 ≤ 7.000)
        Neue Limit-Buy-Order über 8.000 → abgelehnt (8.000 > 7.000)
    """
    capital: float
    assets: dict[str, float] = field(default_factory=dict)
    reserved_capital: float = field(default=0.0, init=False)
    reserved_assets: dict[str, float] = field(default_factory=dict, init=False)
    trade_history: list[Trade] = field(default_factory=list, init=False)

    @property
    def available_capital(self) -> float:
        """Verfügbares Kapital (abzgl. Reservierungen für offene Orders)."""
        return self.capital - self.reserved_capital

    def available_asset_qty(self, symbol: str) -> float:
        """Verfügbare Menge eines Assets (abzgl. Reservierungen)."""
        held = self.assets.get(symbol, 0.0)
        reserved = self.reserved_assets.get(symbol, 0.0)
        return held - reserved

    def reserve_capital(self, amount: float) -> bool:
        """Reserviert Kapital für eine Buy-Limit-Order.

        Returns:
            True wenn genug Kapital verfügbar, False sonst.
        """
        if amount > self.available_capital:
            return False
        self.reserved_capital += amount
        return True

    def release_capital(self, amount: float) -> None:
        """Gibt reserviertes Kapital frei (bei Order-Cancel)."""
        self.reserved_capital = max(0.0, self.reserved_capital - amount)

    def reserve_assets(self, symbol: str, qty: float) -> bool:
        """Reserviert Assets für eine Sell-Limit-Order.

        Returns:
            True wenn genug Assets verfügbar, False sonst.
        """
        if qty > self.available_asset_qty(symbol):
            return False
        self.reserved_assets[symbol] = self.reserved_assets.get(symbol, 0.0) + qty
        return True

    def release_assets(self, symbol: str, qty: float) -> None:
        """Gibt reservierte Assets frei (bei Order-Cancel)."""
        current = self.reserved_assets.get(symbol, 0.0)
        self.reserved_assets[symbol] = max(0.0, current - qty)

    def settle_trade(self, trade: Trade, trader_id: int) -> None:
        """Führt die Kontobuchung für einen Trade durch.

        WARUM hier und nicht in Trade?
        → Account ist der Eigentümer seiner Daten. Nur Account darf
          seine Felder ändern. Trade ist ein unveränderliches Datum.

        Args:
            trade: Der auszuführende Trade
            trader_id: ID dieses Traders (um Käufer/Verkäufer zu bestimmen)
        """
        if trader_id == trade.buyer_id:
            # Käufer: Kapital abziehen, Assets gutschreiben
            cost = trade.price * trade.quantity
            self.capital -= cost
            self.assets[trade.symbol] = self.assets.get(trade.symbol, 0.0) + trade.quantity
            # Reservierung auflösen (Limit-Order hatte Kapital reserviert)
            self.release_capital(cost)

        elif trader_id == trade.seller_id:
            # Verkäufer: Assets abziehen, Kapital gutschreiben
            revenue = trade.price * trade.quantity
            self.capital += revenue
            self.assets[trade.symbol] = self.assets.get(trade.symbol, 0.0) - trade.quantity
            # Reservierung auflösen
            self.release_assets(trade.symbol, trade.quantity)

        self.trade_history.append(trade)

    @property
    def total_trades(self) -> int:
        return len(self.trade_history)

    def portfolio_value(self, prices: dict[str, float]) -> float:
        """Berechnet den Gesamtwert: Kapital + Summe(asset_qty * preis).

        Args:
            prices: Aktuelle Marktpreise {symbol: price}
        """
        asset_value = sum(
            qty * prices.get(symbol, 0.0)
            for symbol, qty in self.assets.items()
        )
        return self.capital + asset_value

    def __repr__(self) -> str:
        return f"Account(capital={self.capital:.2f}, assets={self.assets})"
