"""
Orderbuch mit effizienten Datenstrukturen.

DESIGN-ENTSCHEIDUNGEN:

1. SortedDict[float, deque[Order]] als Kern-Datenstruktur:
   ──────────────────────────────────────────────────────
   VORHER (dein Code): list[Order] + sort() nach jedem Insert
   - Insert: O(n log n) wegen vollständigem sort()
   - Best Price: O(1) via [0], aber nach teurem Sort
   - Cancel: O(n) lineare Suche + O(n) remove()

   NACHHER: SortedDict (basiert auf B-Tree) + deque pro Price-Level
   - Insert: O(log P) wobei P = Anzahl verschiedener Preise
   - Best Price: O(log P) via peekitem()
   - Cancel: O(1) amortisiert via order_id → Order Lookup + deque.remove()

   WARUM SortedDict statt heapq?
   - heapq unterstützt kein effizientes Cancel (müsste lazy-delete machen)
   - heapq kann nicht über Price-Levels iterieren (für Markttiefe-Anzeige)
   - SortedDict erlaubt O(log P) Zugriff auf jedes Price-Level

   WARUM deque statt list pro Price-Level?
   - Alle Orders am gleichen Preis folgen FIFO (Time-Priority)
   - deque.popleft() ist O(1), list.pop(0) ist O(n)

2. _orders Dict für O(1) Cancel:
   ──────────────────────────────
   VORHER: Lineare Suche durch alle Orders O(n)
   NACHHER: dict[order_id, Order] → O(1) Lookup, dann O(k) deque.remove()
   wobei k = Anzahl Orders am gleichen Preis (typisch < 10)

3. Trennung OrderBook / MatchingEngine:
   ─────────────────────────────────────
   OrderBook = Datenstruktur (add, remove, peek)
   MatchingEngine = Algorithmus (match orders, erzeugt Trades)
   Warum? Testbarkeit und Single Responsibility.
   OrderBook kann unabhängig von Matching-Logik getestet werden.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from sortedcontainers import SortedDict

from exchange_sim.models.order import Order, Side, OrderType, OrderStatus


class PriceLevel:
    """Eine Warteschlange von Orders zum gleichen Preis.

    WARUM eigene Klasse statt nackter deque?
    - Kapselt die FIFO-Logik und trackt Gesamtmenge pro Level
    - total_qty ermöglicht O(1) Abfrage der verfügbaren Liquidität pro Preis
    """

    __slots__ = ("price", "orders", "total_qty")

    def __init__(self, price: float) -> None:
        self.price = price
        self.orders: deque[Order] = deque()
        self.total_qty: float = 0.0

    def add(self, order: Order) -> None:
        """Fügt eine Order am Ende der Queue hinzu (Time-Priority)."""
        self.orders.append(order)
        self.total_qty += order.remaining_qty

    def peek(self) -> Optional[Order]:
        """Gibt die älteste Order zurück ohne sie zu entfernen."""
        return self.orders[0] if self.orders else None

    def pop(self) -> Optional[Order]:
        """Entfernt und gibt die älteste Order zurück."""
        if not self.orders:
            return None
        order = self.orders.popleft()  # O(1) dank deque
        self.total_qty -= order.remaining_qty
        return order

    def remove(self, order: Order) -> bool:
        """Entfernt eine spezifische Order (für Cancel). O(k) wobei k = Orders am Level."""
        try:
            self.orders.remove(order)
            self.total_qty -= order.remaining_qty
            return True
        except ValueError:
            return False

    def update_qty(self, delta: float) -> None:
        """Aktualisiert total_qty nach einem Partial Fill."""
        self.total_qty += delta

    @property
    def is_empty(self) -> bool:
        return len(self.orders) == 0

    def __len__(self) -> int:
        return len(self.orders)

    def __repr__(self) -> str:
        return f"PriceLevel({self.price:.2f}, orders={len(self.orders)}, qty={self.total_qty:.1f})"


class OrderBook:
    """Orderbuch mit Price-Time-Priority.

    Verwaltet Bids (Kauforders) und Asks (Verkaufsorders) in sortierten
    Preis-Stufen. Jede Preis-Stufe enthält eine FIFO-Queue von Orders.

    Bids: SortedDict mit negiertem Key → höchster Preis zuerst
    Asks: SortedDict mit normalem Key → niedrigster Preis zuerst

    WARUM negierter Key für Bids?
    SortedDict sortiert aufsteigend. Bids müssen absteigend sortiert sein
    (höchster Kaufpreis hat Priorität). Negierung dreht die Sortierung um,
    ohne dass wir eine custom Comparator-Klasse brauchen.
    peekitem(0) gibt dann immer den besten Preis zurück.
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        # Bids: key = -price (höchster Preis = kleinster Key → peekitem(0))
        self._bids: SortedDict[float, PriceLevel] = SortedDict()
        # Asks: key = price (niedrigster Preis = kleinster Key → peekitem(0))
        self._asks: SortedDict[float, PriceLevel] = SortedDict()
        # O(1) Lookup für Cancel: order_id → Order
        self._orders: dict[int, Order] = {}

    def add(self, order: Order) -> None:
        """Fügt eine Limit-Order ins Orderbuch ein. O(log P).

        Market-Orders werden NICHT ins Buch eingefügt – sie werden
        direkt von der MatchingEngine verarbeitet.
        """
        if order.order_type == OrderType.MARKET:
            return  # Market-Orders gehen nie ins Buch
        if not order.is_active:
            return

        book = self._bids if order.side == Side.BUY else self._asks
        key = -order.price if order.side == Side.BUY else order.price

        if key not in book:
            book[key] = PriceLevel(order.price)

        book[key].add(order)
        self._orders[order.order_id] = order

    def cancel(self, order_id: int) -> Optional[Order]:
        """Storniert eine Order per ID. O(1) Lookup + O(k) Entfernung vom Level.

        Returns:
            Die stornierte Order, oder None wenn nicht gefunden.
        """
        order = self._orders.pop(order_id, None)
        if order is None:
            return None

        book = self._bids if order.side == Side.BUY else self._asks
        key = -order.price if order.side == Side.BUY else order.price

        level = book.get(key)
        if level is not None:
            level.remove(order)
            if level.is_empty:
                del book[key]

        order.cancel()
        return order

    def best_bid(self) -> Optional[Order]:
        """Höchster Kaufpreis. O(log P)."""
        if not self._bids:
            return None
        level: PriceLevel = self._bids.peekitem(0)[1]
        return level.peek()

    def best_ask(self) -> Optional[Order]:
        """Niedrigster Verkaufspreis. O(log P)."""
        if not self._asks:
            return None
        level: PriceLevel = self._asks.peekitem(0)[1]
        return level.peek()

    @property
    def spread(self) -> Optional[float]:
        """Bid-Ask-Spread. None wenn eine Seite leer ist."""
        bid = self.best_bid()
        ask = self.best_ask()
        if bid is None or ask is None:
            return None
        return ask.price - bid.price

    @property
    def mid_price(self) -> Optional[float]:
        """Mittelpreis zwischen bestem Bid und Ask."""
        bid = self.best_bid()
        ask = self.best_ask()
        if bid is None or ask is None:
            return None
        return (bid.price + ask.price) / 2

    def _pop_best(self, side: Side) -> Optional[Order]:
        """Entfernt die beste Order von einer Seite. Intern für MatchingEngine."""
        book = self._bids if side == Side.BUY else self._asks
        if not book:
            return None

        key, level = book.peekitem(0)
        order = level.pop()
        if order is not None:
            self._orders.pop(order.order_id, None)
        if level.is_empty:
            del book[key]
        return order

    def _peek_best(self, side: Side) -> Optional[Order]:
        """Gibt die beste Order zurück ohne sie zu entfernen."""
        book = self._bids if side == Side.BUY else self._asks
        if not book:
            return None
        level: PriceLevel = book.peekitem(0)[1]
        return level.peek()

    def _update_level_qty(self, order: Order, filled_qty: float) -> None:
        """Aktualisiert die Level-Qty nach einem Partial Fill."""
        book = self._bids if order.side == Side.BUY else self._asks
        key = -order.price if order.side == Side.BUY else order.price
        level = book.get(key)
        if level is not None:
            level.update_qty(-filled_qty)

    def _remove_if_filled(self, order: Order) -> None:
        """Entfernt eine vollständig gefüllte Order aus dem Buch."""
        if order.status == OrderStatus.FILLED:
            book = self._bids if order.side == Side.BUY else self._asks
            key = -order.price if order.side == Side.BUY else order.price
            level = book.get(key)
            if level is not None:
                level.remove(order)
                if level.is_empty:
                    del book[key]
            self._orders.pop(order.order_id, None)

    def get_depth(self, side: Side, levels: int = 5) -> list[tuple[float, float]]:
        """Gibt die Top-N Price-Levels zurück als [(price, total_qty), ...].

        Nützlich für Markttiefe-Visualisierung.
        """
        book = self._bids if side == Side.BUY else self._asks
        result = []
        for _, level in book.items():
            if len(result) >= levels:
                break
            result.append((level.price, level.total_qty))
        return result

    @property
    def bid_count(self) -> int:
        """Gesamtanzahl aller Bid-Orders."""
        return sum(len(level) for level in self._bids.values())

    @property
    def ask_count(self) -> int:
        """Gesamtanzahl aller Ask-Orders."""
        return sum(len(level) for level in self._asks.values())

    def __repr__(self) -> str:
        bid = self.best_bid()
        ask = self.best_ask()
        bid_str = f"{bid.price:.2f}" if bid else "---"
        ask_str = f"{ask.price:.2f}" if ask else "---"
        return f"OrderBook({self.symbol} bid={bid_str} ask={ask_str})"
