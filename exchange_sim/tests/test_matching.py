"""
Tests für die MatchingEngine.

Testet Matching-Logik: Price-Time-Priority, Partial Fills,
Market vs. Limit-Orders, vollständige Fills.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime

from exchange_sim.models.order import Order, Side, OrderType, OrderStatus, reset_order_id_counter
from exchange_sim.models.trade import Trade
from exchange_sim.orderbook.orderbook import OrderBook
from exchange_sim.orderbook.matching import MatchingEngine


@pytest.fixture(autouse=True)
def reset_ids():
    reset_order_id_counter()
    yield


def make_order(side: Side, price: float, qty: float,
               order_type: OrderType = OrderType.LIMIT,
               timestamp: datetime | None = None,
               trader_id: int = 1) -> Order:
    return Order(
        side=side,
        order_type=order_type,
        symbol="TEST",
        quantity=qty,
        price=price,
        timestamp=timestamp or datetime(2026, 1, 1, 10, 0),
        trader_id=trader_id,
    )


NOW = datetime(2026, 1, 1, 10, 0, 0)


class TestLimitOrderMatching:
    """Tests für Limit-Order-Matching."""

    def test_no_match_when_prices_dont_cross(self):
        """Kein Match wenn Bid < Ask."""
        book = OrderBook("TEST")
        engine = MatchingEngine(book)

        # Ruhende Ask-Order
        ask = make_order(Side.SELL, 101.0, 5, trader_id=2)
        engine.process(ask, NOW)

        # Eingehender Bid unter dem Ask → kein Match
        bid = make_order(Side.BUY, 100.0, 5)
        trades = engine.process(bid, NOW)

        assert len(trades) == 0
        assert book.bid_count == 1  # Bid im Buch
        assert book.ask_count == 1  # Ask noch da

    def test_exact_match(self):
        """Exakter Match: gleicher Preis und gleiche Menge."""
        book = OrderBook("TEST")
        engine = MatchingEngine(book)

        ask = make_order(Side.SELL, 100.0, 5, trader_id=2)
        engine.process(ask, NOW)

        bid = make_order(Side.BUY, 100.0, 5)
        trades = engine.process(bid, NOW)

        assert len(trades) == 1
        assert trades[0].price == 100.0  # Maker-Preis (Ask)
        assert trades[0].quantity == 5
        assert book.bid_count == 0  # Beide gefüllt
        assert book.ask_count == 0

    def test_partial_fill_aggressor(self):
        """Aggressor wird nur teilweise gefüllt → Rest ins Buch."""
        book = OrderBook("TEST")
        engine = MatchingEngine(book)

        ask = make_order(Side.SELL, 100.0, 3, trader_id=2)
        engine.process(ask, NOW)

        # Bid will 5, aber nur 3 verfügbar
        bid = make_order(Side.BUY, 100.0, 5)
        trades = engine.process(bid, NOW)

        assert len(trades) == 1
        assert trades[0].quantity == 3
        assert bid.remaining_qty == 2.0
        assert bid.status == OrderStatus.PARTIALLY_FILLED
        assert book.bid_count == 1  # Rest im Buch

    def test_partial_fill_resting(self):
        """Ruhende Order wird nur teilweise gefüllt → bleibt im Buch."""
        book = OrderBook("TEST")
        engine = MatchingEngine(book)

        ask = make_order(Side.SELL, 100.0, 10, trader_id=2)
        engine.process(ask, NOW)

        bid = make_order(Side.BUY, 100.0, 3)
        trades = engine.process(bid, NOW)

        assert len(trades) == 1
        assert trades[0].quantity == 3
        assert ask.remaining_qty == 7.0
        assert book.ask_count == 1  # Ask noch im Buch mit Rest

    def test_multiple_fills_across_levels(self):
        """Aggressor füllt über mehrere Price-Levels hinweg."""
        book = OrderBook("TEST")
        engine = MatchingEngine(book)

        # Drei Asks auf verschiedenen Preisen
        engine.process(make_order(Side.SELL, 100.0, 3, trader_id=2), NOW)
        engine.process(make_order(Side.SELL, 101.0, 3, trader_id=3), NOW)
        engine.process(make_order(Side.SELL, 102.0, 3, trader_id=4), NOW)

        # Bid will 7 → füllt 3@100 + 3@101 + 1@102
        bid = make_order(Side.BUY, 102.0, 7)
        trades = engine.process(bid, NOW)

        assert len(trades) == 3
        assert trades[0].price == 100.0
        assert trades[0].quantity == 3
        assert trades[1].price == 101.0
        assert trades[1].quantity == 3
        assert trades[2].price == 102.0
        assert trades[2].quantity == 1

        # Bid vollständig gefüllt
        assert bid.status == OrderStatus.FILLED
        # Letzte Ask hat noch Rest
        assert book.ask_count == 1

    def test_trade_at_maker_price(self):
        """Trade-Preis ist immer der Maker-Preis (ruhende Order)."""
        book = OrderBook("TEST")
        engine = MatchingEngine(book)

        # Ask bei 98 (Maker)
        ask = make_order(Side.SELL, 98.0, 5, trader_id=2)
        engine.process(ask, NOW)

        # Bid bei 100 (Aggressor) → Trade bei 98 (Maker-Preis)
        bid = make_order(Side.BUY, 100.0, 5)
        trades = engine.process(bid, NOW)

        assert trades[0].price == 98.0  # Maker-Preis, nicht 100

    def test_price_time_priority(self):
        """Price-Time-Priority: besserer Preis zuerst, bei gleichem Preis FIFO."""
        book = OrderBook("TEST")
        engine = MatchingEngine(book)

        t1 = datetime(2026, 1, 1, 10, 0, 0)
        t2 = datetime(2026, 1, 1, 10, 0, 1)

        # Zwei Asks am gleichen Preis, unterschiedliche Zeit
        old_ask = make_order(Side.SELL, 100.0, 3, timestamp=t1, trader_id=2)
        new_ask = make_order(Side.SELL, 100.0, 3, timestamp=t2, trader_id=3)
        engine.process(old_ask, NOW)
        engine.process(new_ask, NOW)

        # Bid füllt nur 3 → sollte die ältere Ask matchen
        bid = make_order(Side.BUY, 100.0, 3)
        trades = engine.process(bid, NOW)

        assert len(trades) == 1
        assert trades[0].sell_order_id == old_ask.order_id  # Ältere zuerst


class TestMarketOrderMatching:
    """Tests für Market-Order-Matching."""

    def test_market_buy_against_asks(self):
        """Market-Buy matcht gegen alle verfügbaren Asks."""
        book = OrderBook("TEST")
        engine = MatchingEngine(book)

        engine.process(make_order(Side.SELL, 100.0, 3, trader_id=2), NOW)
        engine.process(make_order(Side.SELL, 101.0, 3, trader_id=3), NOW)

        # Market-Buy will 5
        market_buy = make_order(Side.BUY, 0.0, 5, OrderType.MARKET)
        trades = engine.process(market_buy, NOW)

        # VORHER (dein Code): Nur 1 Trade mit 3
        # NACHHER: 2 Trades (3@100 + 2@101) = vollständiger Fill
        assert len(trades) == 2
        assert sum(t.quantity for t in trades) == 5
        assert market_buy.status == OrderStatus.FILLED

    def test_market_sell_against_bids(self):
        """Market-Sell matcht gegen alle verfügbaren Bids."""
        book = OrderBook("TEST")
        engine = MatchingEngine(book)

        engine.process(make_order(Side.BUY, 101.0, 3, trader_id=2), NOW)
        engine.process(make_order(Side.BUY, 100.0, 3, trader_id=3), NOW)

        market_sell = make_order(Side.SELL, 0.0, 5, OrderType.MARKET)
        trades = engine.process(market_sell, NOW)

        assert len(trades) == 2
        assert trades[0].price == 101.0  # Bester Bid zuerst
        assert trades[1].price == 100.0
        assert sum(t.quantity for t in trades) == 5

    def test_market_order_no_liquidity(self):
        """Market-Order ohne Gegenorders → kein Trade, Order bleibt unfilled."""
        book = OrderBook("TEST")
        engine = MatchingEngine(book)

        market_buy = make_order(Side.BUY, 0.0, 5, OrderType.MARKET)
        trades = engine.process(market_buy, NOW)

        assert len(trades) == 0
        # Market-Order wird NICHT ins Buch eingefügt
        assert book.bid_count == 0

    def test_market_order_partial_fill(self):
        """Market-Order wird teilweise gefüllt wenn nicht genug Liquidität."""
        book = OrderBook("TEST")
        engine = MatchingEngine(book)

        engine.process(make_order(Side.SELL, 100.0, 3, trader_id=2), NOW)

        market_buy = make_order(Side.BUY, 0.0, 10, OrderType.MARKET)
        trades = engine.process(market_buy, NOW)

        assert len(trades) == 1
        assert trades[0].quantity == 3
        assert market_buy.remaining_qty == 7.0
        # Market-Order bleibt NICHT im Buch
        assert book.bid_count == 0


class TestTradeIntegrity:
    """Tests für die Integrität der erzeugten Trades."""

    def test_trade_contains_correct_ids(self):
        """Trade enthält korrekte Buyer/Seller IDs."""
        book = OrderBook("TEST")
        engine = MatchingEngine(book)

        ask = make_order(Side.SELL, 100.0, 5, trader_id=42)
        engine.process(ask, NOW)

        bid = make_order(Side.BUY, 100.0, 5, trader_id=7)
        trades = engine.process(bid, NOW)

        assert trades[0].buyer_id == 7
        assert trades[0].seller_id == 42
        assert trades[0].buy_order_id == bid.order_id
        assert trades[0].sell_order_id == ask.order_id

    def test_trade_is_immutable(self):
        """Trade ist frozen (unveränderlich)."""
        book = OrderBook("TEST")
        engine = MatchingEngine(book)

        engine.process(make_order(Side.SELL, 100.0, 5, trader_id=2), NOW)
        bid = make_order(Side.BUY, 100.0, 5)
        trades = engine.process(bid, NOW)

        with pytest.raises(AttributeError):
            trades[0].price = 999.0  # frozen=True verhindert das
