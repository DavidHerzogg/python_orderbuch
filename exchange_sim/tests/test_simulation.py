"""
Integrationstests für Account-Settlement und die Simulation.

Testet das Zusammenspiel von OrderBook, MatchingEngine, Account und Exchange.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime

from exchange_sim.models.order import Order, Side, OrderType, reset_order_id_counter
from exchange_sim.models.trade import Trade
from exchange_sim.exchange.account import Account
from exchange_sim.exchange.market import Market
from exchange_sim.exchange.exchange import Exchange
from exchange_sim.strategies.strategies import Trader, RandomNoise, MarketMaker


@pytest.fixture(autouse=True)
def reset_ids():
    reset_order_id_counter()
    yield


NOW = datetime(2026, 1, 1, 10, 0, 0)


class TestAccount:
    """Tests für das Account-Modell."""

    def test_reserve_and_release_capital(self):
        """Reservierung und Freigabe von Kapital."""
        acc = Account(capital=10000.0)
        assert acc.available_capital == 10000.0

        assert acc.reserve_capital(3000.0) is True
        assert acc.available_capital == 7000.0

        # Zu viel reservieren → abgelehnt
        assert acc.reserve_capital(8000.0) is False
        assert acc.available_capital == 7000.0  # Unverändert

        acc.release_capital(3000.0)
        assert acc.available_capital == 10000.0

    def test_reserve_and_release_assets(self):
        """Reservierung und Freigabe von Assets."""
        acc = Account(capital=0.0, assets={"XAUUSD": 10.0})
        assert acc.available_asset_qty("XAUUSD") == 10.0

        assert acc.reserve_assets("XAUUSD", 7.0) is True
        assert acc.available_asset_qty("XAUUSD") == 3.0

        # Zu viel → abgelehnt
        assert acc.reserve_assets("XAUUSD", 5.0) is False

        acc.release_assets("XAUUSD", 7.0)
        assert acc.available_asset_qty("XAUUSD") == 10.0

    def test_settle_trade_buyer(self):
        """Settlement für den Käufer: Kapital ab, Assets rauf."""
        acc = Account(capital=10000.0, assets={"XAUUSD": 0.0})
        acc.reserve_capital(500.0)  # Simuliert vorab-Reservierung

        trade = Trade(
            price=100.0, quantity=5, buy_order_id=1, sell_order_id=2,
            buyer_id=1, seller_id=2, symbol="XAUUSD", timestamp=NOW,
        )

        acc.settle_trade(trade, trader_id=1)

        assert acc.capital == 9500.0  # 10000 - 100*5
        assert acc.assets["XAUUSD"] == 5.0
        assert len(acc.trade_history) == 1

    def test_settle_trade_seller(self):
        """Settlement für den Verkäufer: Assets ab, Kapital rauf."""
        acc = Account(capital=0.0, assets={"XAUUSD": 10.0})
        acc.reserve_assets("XAUUSD", 5.0)

        trade = Trade(
            price=100.0, quantity=5, buy_order_id=1, sell_order_id=2,
            buyer_id=1, seller_id=2, symbol="XAUUSD", timestamp=NOW,
        )

        acc.settle_trade(trade, trader_id=2)

        assert acc.capital == 500.0  # 0 + 100*5
        assert acc.assets["XAUUSD"] == 5.0  # 10 - 5
        assert len(acc.trade_history) == 1

    def test_portfolio_value(self):
        """Portfolio-Wert = Kapital + Assets * Preise."""
        acc = Account(capital=5000.0, assets={"XAUUSD": 10.0, "SP500": 5.0})
        prices = {"XAUUSD": 100.0, "SP500": 200.0}

        value = acc.portfolio_value(prices)
        assert value == 5000.0 + 10*100 + 5*200  # 7000


class TestExchangeIntegration:
    """Integrationstests für Exchange + Market + Trader."""

    def _setup_exchange(self):
        """Erstellt eine Exchange mit einem Markt und zwei Tradern."""
        market = Market("TEST", 100.0)
        exchange = Exchange([market])
        exchange.is_open = True

        buyer = Trader(
            trader_id=1, name="buyer", capital=100000.0,
            assets={"TEST": 0.0}, exchange=exchange,
            strategy=RandomNoise(quantity=1),  # Strategie wird nicht benutzt
        )
        seller = Trader(
            trader_id=2, name="seller", capital=0.0,
            assets={"TEST": 100.0}, exchange=exchange,
            strategy=RandomNoise(quantity=1),
        )
        return exchange, market, buyer, seller

    def test_full_trade_cycle(self):
        """Vollständiger Zyklus: Order → Match → Trade → Settlement."""
        exchange, market, buyer, seller = self._setup_exchange()

        # Seller stellt Limit-Ask
        seller.place_order(Side.SELL, OrderType.LIMIT, "TEST", 5, 100.0, NOW)
        assert market.orderbook.ask_count == 1

        # Buyer stellt Limit-Bid → Match!
        trades = buyer.place_order(Side.BUY, OrderType.LIMIT, "TEST", 5, 100.0, NOW)

        assert len(trades) == 1
        assert trades[0].quantity == 5
        assert trades[0].price == 100.0

        # Settlement prüfen
        assert buyer.account.capital == 100000.0 - 500.0  # 5 * 100
        assert buyer.account.assets["TEST"] == 5.0
        assert seller.account.capital == 500.0
        assert seller.account.assets["TEST"] == 95.0  # 100 - 5

    def test_order_rejected_insufficient_capital(self):
        """Order wird abgelehnt wenn nicht genug Kapital."""
        exchange, market, buyer, seller = self._setup_exchange()
        buyer.account.capital = 100.0  # Nur 100

        trades = buyer.place_order(Side.BUY, OrderType.LIMIT, "TEST", 5, 100.0, NOW)
        # Kosten wären 500, aber nur 100 verfügbar
        assert len(trades) == 0
        assert market.orderbook.bid_count == 0

    def test_order_rejected_insufficient_assets(self):
        """Order wird abgelehnt wenn nicht genug Assets."""
        exchange, market, buyer, seller = self._setup_exchange()

        # Seller hat 100, will aber 200 verkaufen
        trades = seller.place_order(Side.SELL, OrderType.LIMIT, "TEST", 200, 100.0, NOW)
        assert len(trades) == 0

    def test_cancel_releases_reservation(self):
        """Cancel gibt reserviertes Kapital frei."""
        exchange, market, buyer, seller = self._setup_exchange()

        buyer.place_order(Side.BUY, OrderType.LIMIT, "TEST", 5, 100.0, NOW)
        assert buyer.account.available_capital == 100000.0 - 500.0

        # Cancel
        order_id = list(buyer._active_orders.keys())[0]
        buyer.cancel_order("TEST", order_id)

        # Kapital sollte wieder frei sein
        assert buyer.account.available_capital == 100000.0

    def test_exchange_closed_rejects_orders(self):
        """Geschlossene Börse lehnt alle Orders ab."""
        exchange, market, buyer, seller = self._setup_exchange()
        exchange.is_open = False

        seller.place_order(Side.SELL, OrderType.LIMIT, "TEST", 5, 100.0, NOW)
        # Order wird erstellt und Reservierung gemacht, aber Exchange gibt [] zurück
        # Das ist ok – in der Praxis würde der Trader vor dem Senden prüfen
        assert market.orderbook.ask_count == 0

    def test_price_updates_on_trade(self):
        """Marktpreis aktualisiert sich nach einem Trade."""
        exchange, market, buyer, seller = self._setup_exchange()

        seller.place_order(Side.SELL, OrderType.LIMIT, "TEST", 5, 105.0, NOW)
        buyer.place_order(Side.BUY, OrderType.LIMIT, "TEST", 5, 105.0, NOW)

        assert market.price == 105.0  # Preis aktualisiert
