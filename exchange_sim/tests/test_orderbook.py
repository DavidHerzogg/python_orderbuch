"""
Tests für das Orderbuch.

Testet die Datenstruktur isoliert von der MatchingEngine.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime

from exchange_sim.models.order import Order, Side, OrderType, OrderStatus, reset_order_id_counter
from exchange_sim.orderbook.orderbook import OrderBook, PriceLevel


@pytest.fixture(autouse=True)
def reset_ids():
    """Setzt die Order-ID-Zähler vor jedem Test zurück."""
    reset_order_id_counter()
    yield


def make_order(side: Side, price: float, qty: float,
               order_type: OrderType = OrderType.LIMIT,
               timestamp: datetime | None = None) -> Order:
    """Hilfsfunktion zum schnellen Erstellen von Test-Orders."""
    return Order(
        side=side,
        order_type=order_type,
        symbol="TEST",
        quantity=qty,
        price=price,
        timestamp=timestamp or datetime(2026, 1, 1, 10, 0),
        trader_id=1,
    )


class TestPriceLevel:
    """Tests für die PriceLevel-Datenstruktur (deque-basierte FIFO-Queue)."""

    def test_add_and_peek(self):
        """Orders werden in FIFO-Reihenfolge verwaltet."""
        level = PriceLevel(100.0)
        o1 = make_order(Side.BUY, 100.0, 5)
        o2 = make_order(Side.BUY, 100.0, 3)

        level.add(o1)
        level.add(o2)

        assert level.peek() is o1  # Erste Order zuerst (FIFO)
        assert level.total_qty == 8.0
        assert len(level) == 2

    def test_pop_fifo_order(self):
        """pop() entfernt die älteste Order (FIFO / Time-Priority)."""
        level = PriceLevel(100.0)
        o1 = make_order(Side.BUY, 100.0, 5)
        o2 = make_order(Side.BUY, 100.0, 3)

        level.add(o1)
        level.add(o2)

        popped = level.pop()
        assert popped is o1
        assert level.total_qty == 3.0
        assert len(level) == 1

    def test_remove_specific_order(self):
        """remove() entfernt eine spezifische Order (für Cancel)."""
        level = PriceLevel(100.0)
        o1 = make_order(Side.BUY, 100.0, 5)
        o2 = make_order(Side.BUY, 100.0, 3)
        o3 = make_order(Side.BUY, 100.0, 7)

        level.add(o1)
        level.add(o2)
        level.add(o3)

        result = level.remove(o2)  # Mittlere Order entfernen
        assert result is True
        assert level.total_qty == 12.0
        assert len(level) == 2

    def test_empty_level(self):
        """Leeres Level: peek/pop geben None zurück."""
        level = PriceLevel(100.0)
        assert level.peek() is None
        assert level.pop() is None
        assert level.is_empty


class TestOrderBook:
    """Tests für das Orderbuch (SortedDict-basiert)."""

    def test_add_bid_price_priority(self):
        """Bids sind nach Preis absteigend sortiert (höchster zuerst)."""
        book = OrderBook("TEST")
        low = make_order(Side.BUY, 99.0, 5)
        high = make_order(Side.BUY, 101.0, 5)

        book.add(low)
        book.add(high)

        best = book.best_bid()
        assert best is not None
        assert best.price == 101.0  # Höchster Bid ist der Beste

    def test_add_ask_price_priority(self):
        """Asks sind nach Preis aufsteigend sortiert (niedrigster zuerst)."""
        book = OrderBook("TEST")
        high = make_order(Side.SELL, 101.0, 5)
        low = make_order(Side.SELL, 99.0, 5)

        book.add(high)
        book.add(low)

        best = book.best_ask()
        assert best is not None
        assert best.price == 99.0  # Niedrigster Ask ist der Beste

    def test_time_priority_same_price(self):
        """Bei gleichem Preis hat die ältere Order Priorität (FIFO)."""
        book = OrderBook("TEST")
        t1 = datetime(2026, 1, 1, 10, 0, 0)
        t2 = datetime(2026, 1, 1, 10, 0, 1)

        old = make_order(Side.BUY, 100.0, 5, timestamp=t1)
        new = make_order(Side.BUY, 100.0, 3, timestamp=t2)

        book.add(old)
        book.add(new)

        best = book.best_bid()
        assert best is old  # Ältere Order hat Priorität

    def test_market_orders_not_added(self):
        """Market-Orders werden nicht ins Buch eingefügt."""
        book = OrderBook("TEST")
        market_order = make_order(Side.BUY, 100.0, 5, OrderType.MARKET)

        book.add(market_order)

        assert book.best_bid() is None
        assert book.bid_count == 0

    def test_cancel_order(self):
        """Cancel entfernt die Order und gibt None bei unbekannter ID."""
        book = OrderBook("TEST")
        order = make_order(Side.BUY, 100.0, 5)
        book.add(order)

        # Cancel mit richtiger ID
        cancelled = book.cancel(order.order_id)
        assert cancelled is order
        assert cancelled.status == OrderStatus.CANCELLED
        assert book.best_bid() is None

        # Cancel mit unbekannter ID
        assert book.cancel(999) is None

    def test_cancel_cleans_empty_level(self):
        """Cancel einer letzten Order auf einem Level entfernt das Level."""
        book = OrderBook("TEST")
        order = make_order(Side.BUY, 100.0, 5)
        book.add(order)

        book.cancel(order.order_id)

        # Level sollte entfernt worden sein
        assert book.bid_count == 0
        depth = book.get_depth(Side.BUY)
        assert len(depth) == 0

    def test_spread_calculation(self):
        """Spread ist die Differenz zwischen bestem Ask und bestem Bid."""
        book = OrderBook("TEST")
        book.add(make_order(Side.BUY, 99.0, 5))
        book.add(make_order(Side.SELL, 101.0, 5))

        assert book.spread == 2.0
        assert book.mid_price == 100.0

    def test_spread_none_when_empty(self):
        """Spread ist None wenn eine Seite leer ist."""
        book = OrderBook("TEST")
        assert book.spread is None
        assert book.mid_price is None

    def test_depth_multiple_levels(self):
        """get_depth gibt die Top-N Price-Levels zurück."""
        book = OrderBook("TEST")
        book.add(make_order(Side.BUY, 100.0, 5))
        book.add(make_order(Side.BUY, 100.0, 3))  # Gleiches Level
        book.add(make_order(Side.BUY, 99.0, 4))
        book.add(make_order(Side.BUY, 98.0, 6))

        depth = book.get_depth(Side.BUY, levels=3)

        assert len(depth) == 3
        assert depth[0] == (100.0, 8.0)  # Bestes Level: 5+3=8
        assert depth[1] == (99.0, 4.0)
        assert depth[2] == (98.0, 6.0)

    def test_bid_ask_count(self):
        """bid_count und ask_count zählen alle Orders."""
        book = OrderBook("TEST")
        book.add(make_order(Side.BUY, 100.0, 5))
        book.add(make_order(Side.BUY, 99.0, 3))
        book.add(make_order(Side.SELL, 101.0, 4))

        assert book.bid_count == 2
        assert book.ask_count == 1
