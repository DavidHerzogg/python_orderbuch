"""
Trade-Modell (Fill).

DESIGN-ENTSCHEIDUNGEN:
- Trade ist eine reine Datenklasse (frozen=True): Ein Trade ist ein historisches Faktum,
  das sich nach Erstellung nie ändert. frozen=True erzwingt Immutability.
- Kein execute(): Im alten Code hat Trade.execute() direkt Account-Felder manipuliert.
  Das verletzt Single Responsibility – ein Trade ist ein Datum, kein Aktor.
  Settlement passiert jetzt in Account.settle_trade().
- buy_order_id / sell_order_id statt Order-Referenzen: Vermeidet zirkuläre Abhängigkeiten
  und macht Trades serialisierbar (z.B. für Logging oder Persistenz).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Trade:
    """Ein ausgeführter Trade (Fill) zwischen zwei Orders.

    Unveränderlich nach Erstellung – ein Trade ist ein historisches Faktum.

    Felder:
        price: Ausführungspreis
        quantity: Ausgeführte Menge
        buy_order_id: ID der kaufenden Order
        sell_order_id: ID der verkaufenden Order
        buyer_id: Trader-ID des Käufers
        seller_id: Trader-ID des Verkäufers
        symbol: Markt-Symbol
        timestamp: Zeitpunkt der Ausführung
    """
    price: float
    quantity: float
    buy_order_id: int
    sell_order_id: int
    buyer_id: int
    seller_id: int
    symbol: str
    timestamp: datetime

    def __repr__(self) -> str:
        return (
            f"Trade({self.symbol} {self.quantity}@{self.price:.2f} "
            f"buyer={self.buyer_id} seller={self.seller_id})"
        )
