"""
Order-Modell mit Enums und Dataclass.

DESIGN-ENTSCHEIDUNGEN:
- Enum statt Strings: Typ-Sicherheit, IDE-Autovervollständigung, kein Typo-Risiko.
  Side.BUY ist eindeutig, "BUY" vs "buy" vs "Buy" nicht.
- @dataclass: Reduziert Boilerplate (kein __init__, __repr__), erzwingt Feld-Deklaration.
- remaining_qty als separates Feld: Erlaubt Partial Fills ohne die Original-Menge zu verlieren.
  order.quantity ist immer die ursprüngliche Menge, remaining_qty trackt den Rest.
- OrderStatus als Enum: Klarer Lebenszyklus einer Order (NEW → PARTIALLY_FILLED → FILLED / CANCELLED).
- order_id als int mit Klassenvariable: Thread-safe genug für single-threaded Matching,
  ersetzt den globalen IDGenerator. Jede Order bekommt automatisch eine eindeutige ID.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class Side(Enum):
    """Kauf- oder Verkaufsseite. Enum statt String verhindert Tippfehler."""
    BUY = auto()
    SELL = auto()


class OrderType(Enum):
    """LIMIT: Preis-garantiert, bleibt im Buch. MARKET: sofortige Ausführung zum besten Preis."""
    LIMIT = auto()
    MARKET = auto()


class OrderStatus(Enum):
    """Lebenszyklus einer Order.

    NEW → PARTIALLY_FILLED → FILLED (vollständig ausgeführt)
    NEW → CANCELLED (vom Händler storniert)
    """
    NEW = auto()
    PARTIALLY_FILLED = auto()
    FILLED = auto()
    CANCELLED = auto()


# Klassenweiter ID-Zähler – ersetzt den globalen IDGenerator.
# Einfacher, da Order die einzige Klasse ist, die IDs braucht.
_next_order_id: int = 0


def _generate_order_id() -> int:
    """Erzeugt eine monoton steigende Order-ID."""
    global _next_order_id
    _next_order_id += 1
    return _next_order_id


def reset_order_id_counter() -> None:
    """Setzt den ID-Zähler zurück (nützlich für Tests)."""
    global _next_order_id
    _next_order_id = 0


@dataclass
class Order:
    """Repräsentiert eine einzelne Order im Orderbuch.

    Felder:
        side: BUY oder SELL
        order_type: LIMIT oder MARKET
        symbol: Markt-Bezeichnung (z.B. "XAUUSD")
        quantity: Ursprüngliche Menge (unveränderlich nach Erstellung)
        price: Limit-Preis. Bei MARKET-Orders 0.0 (wird ignoriert).
        timestamp: Zeitpunkt der Order-Erstellung (für Price-Time-Priority)
        trader_id: ID des Händlers, der die Order aufgegeben hat
        order_id: Automatisch generierte eindeutige ID
        remaining_qty: Verbleibende Menge nach Partial Fills
        status: Aktueller Status im Lebenszyklus
    """
    side: Side
    order_type: OrderType
    symbol: str
    quantity: float
    price: float
    timestamp: datetime
    trader_id: int
    order_id: int = field(default_factory=_generate_order_id)
    remaining_qty: float = field(init=False)
    status: OrderStatus = field(default=OrderStatus.NEW, init=False)

    def __post_init__(self) -> None:
        self.remaining_qty = self.quantity

    def fill(self, qty: float) -> None:
        """Reduziert remaining_qty und aktualisiert Status.

        Warum separate Methode statt direkter Feld-Manipulation:
        - Kapselt die Status-Logik (PARTIALLY_FILLED vs FILLED)
        - Verhindert inkonsistente Zustände (remaining < 0)
        """
        self.remaining_qty -= qty
        if self.remaining_qty <= 0:
            self.remaining_qty = 0
            self.status = OrderStatus.FILLED
        else:
            self.status = OrderStatus.PARTIALLY_FILLED

    def cancel(self) -> None:
        """Markiert die Order als storniert."""
        self.status = OrderStatus.CANCELLED

    @property
    def is_active(self) -> bool:
        """True wenn die Order noch im Orderbuch stehen kann."""
        return self.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)

    def __repr__(self) -> str:
        return (
            f"Order(id={self.order_id}, {self.side.name} {self.order_type.name} "
            f"{self.symbol} qty={self.remaining_qty}/{self.quantity} "
            f"@{self.price:.2f})"
        )
