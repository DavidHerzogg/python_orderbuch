from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import random
from id_generator import IDGenerator

id_generator = IDGenerator()


class Event:
    pass


class TradeExecuted(Event):
    def __init__(self, trade, time):
        self.trade = trade
        self.time = time


# class OrderCancelled(Event):
#     def __init__(self, order, händler, time):
#         self.order = order
#         self.händler = händler
#         self.time = time


class EventBus:
    def __init__(self):
        self.listeners = {}

    def subscribe(self, event_typ, function):
        if event_typ not in self.listeners:
            self.listeners[event_typ] = []

        self.listeners[event_typ].append(function)

    def publish(self, event):
        event_type = type(event)

        if event_type not in self.listeners:
            return

        for function in self.listeners[event_type]:
            function(event)


class Statistik:

    def __init__(self):
        self.trade_count = 0
        self.volume = 0
        self.trades_pro_markt = {}
        self.volume_pro_markt = {}

    def trade_ausgeführt(self, event):

        trade = event.trade

        self.trade_count += 1
        self.volume += trade.menge

        market_name = trade.buy_order.market_name

        self.trades_pro_markt[market_name] = (
            self.trades_pro_markt.get(market_name, 0) + 1
        )

        self.volume_pro_markt[market_name] = (
            self.volume_pro_markt.get(market_name, 0) + trade.menge
        )


class Clock:
    def __init__(self, start_time, dt):
        self.time = start_time
        self.dt = dt

    def tick(self):
        self.time += timedelta(seconds=self.dt)


class Order:
    def __init__(self, side, preis, menge, id, zeit, händler, market_name, order_type):
        self.side = side
        self.preis = preis
        self.menge = menge
        self.originale_menge = menge
        self.id = id
        self.zeit = zeit
        self.händler = händler
        self.market_name = market_name
        self.order_type = order_type

        self.reservierte_kosten = 0
        self.reservierte_assets = 0

    def __str__(self):
        return (
            f"{{\n"
            f"    Side: {self.side}\n"
            f"    Preis: {self.preis}\n"
            f"    Menge: {self.menge}\n"
            f"    ID: {self.id}\n"
            f"    Zeit: {self.zeit}\n"
            f"    Händler: {self.händler}\n"
            f"    Markt: {self.market_name}\n"
            f"    Typ: {self.order_type}\n"
            f"}}"
        )

    def __repr__(self):
        return (
            f"{{ Side: {self.side}, Preis: {self.preis}, Menge: {self.menge}, "
            f"ID: {self.id}, Zeit: {self.zeit}, Händler: {self.händler}, "
            f"Markt: {self.market_name}}}"
        )


class Trade:
    def __init__(self, preis, menge, buy_order, sell_order):
        self.preis = preis
        self.menge = menge
        self.buy_order = buy_order
        self.sell_order = sell_order

    def __str__(self):
        return (
            f"Trade("
            f"Preis={self.preis}, "
            f"Menge={self.menge}, "
            f"Buy-ID={self.buy_order.id}, "
            f"Sell-ID={self.sell_order.id}"
            f")"
        )

    def __repr__(self):
        return (
            f"Trade(Preis={self.preis}, Menge={self.menge}, "
            f"Buy-ID={self.buy_order.id}, Sell-ID={self.sell_order.id})"
        )

    def execute(self):
        käufer = self.buy_order.händler.account
        verkäufer = self.sell_order.händler.account

        wert = self.preis * self.menge

        käufer.kapital -= wert
        käufer.assets[self.buy_order.market_name] += self.menge

        verkäufer.kapital += wert
        verkäufer.assets[self.sell_order.market_name] -= self.menge

        if self.buy_order.order_type == "LIMIT":

            reserviert = self.buy_order.preis * self.menge

            käufer.reserved_kapital -= reserviert
            self.buy_order.reservierte_kosten -= reserviert

            überschuss = reserviert - wert

            käufer.kapital += überschuss

        elif self.buy_order.order_type == "MARKET":

            käufer.reserved_kapital -= wert
            self.buy_order.reservierte_kosten -= wert

        if self.sell_order.order_type == "LIMIT":

            verkäufer.reserved_assets[self.sell_order.market_name] -= self.menge
            self.sell_order.reservierte_assets -= self.menge

        elif self.sell_order.order_type == "MARKET":

            verkäufer.reserved_assets[self.sell_order.market_name] -= self.menge
            self.sell_order.reservierte_assets -= self.menge


class Candle:
    def __init__(self, start_time, preis):
        self.time = start_time
        self.open = preis
        self.high = preis
        self.low = preis
        self.close = preis
        self.volume = 0

    def update(self, preis, menge):
        self.high = max(self.high, preis)
        self.low = min(self.low, preis)
        self.close = preis
        self.volume += menge


class Orderbuch:
    def __init__(self):
        self.bids = []
        self.asks = []
        self.trades = []

    def add_order(self, order):

        if order.order_type == "MARKET":
            return

        if order.side == "BUY":
            self.bids.append(order)

            self.bids.sort(
                key=lambda order: (-order.preis, order.zeit)
            )

        elif order.side == "SELL":
            self.asks.append(order)

            self.asks.sort(
                key=lambda order: (order.preis, order.zeit)
            )

    def cancel_order(self, order, händler):

        if order.order_type == "MARKET":
            return

        for ord in self.bids:

            if ord.id == order.id:

                if ord.händler != händler:
                    return False

                händler.account.reserved_kapital -= (
                    ord.preis * ord.menge
                )

                ord.reservierte_kosten = 0

                self.bids.remove(ord)

                return True

        for ord in self.asks:

            if ord.id == order.id:

                if ord.händler != händler:
                    return False

                händler.account.reserved_assets[ord.market_name] = (
                    händler.account.reserved_assets.get(
                        ord.market_name,
                        0
                    ) - ord.menge
                )

                ord.reservierte_assets = 0

                self.asks.remove(ord)

                return True

        return False

    def get_estimated_value(self, order):

        remaining = order.menge
        estimated_value = 0

        if order.side == "BUY":

            for ask in self.asks:

                menge = min(
                    remaining,
                    ask.menge
                )

                estimated_value += menge * ask.preis

                remaining -= menge

                if remaining <= 0:
                    break

        elif order.side == "SELL":

            for bid in self.bids:

                menge = min(
                    remaining,
                    bid.menge
                )

                estimated_value += menge * bid.preis

                remaining -= menge

                if remaining <= 0:
                    break

        if remaining > 0:
            return False

        return estimated_value

    def match(self, order):

        trades = []

        if order.order_type == "MARKET":

            while order.menge > 0:

                if order.side == "BUY":

                    if not self.asks:
                        break

                    best_ask = self.asks[0]

                    menge = min(
                        order.menge,
                        best_ask.menge
                    )

                    trade = Trade(
                        best_ask.preis,
                        menge,
                        order,
                        best_ask
                    )

                    self.trades.append(trade)
                    trades.append(trade)

                    trade.execute()

                    order.menge -= menge
                    best_ask.menge -= menge

                    if best_ask.menge == 0:
                        self.asks.pop(0)

                elif order.side == "SELL":

                    if not self.bids:
                        break

                    best_bid = self.bids[0]

                    menge = min(
                        order.menge,
                        best_bid.menge
                    )

                    trade = Trade(
                        best_bid.preis,
                        menge,
                        best_bid,
                        order
                    )

                    self.trades.append(trade)
                    trades.append(trade)

                    trade.execute()

                    order.menge -= menge
                    best_bid.menge -= menge

                    if best_bid.menge == 0:
                        self.bids.pop(0)

            return trades

        while self.bids and self.asks:

            best_bid = self.bids[0]
            best_ask = self.asks[0]

            if best_bid.preis < best_ask.preis:
                break

            menge = min(
                best_bid.menge,
                best_ask.menge
            )

            trade = Trade(
                best_ask.preis,
                menge,
                best_bid,
                best_ask
            )

            self.trades.append(trade)
            trades.append(trade)

            trade.execute()

            best_bid.menge -= menge
            best_ask.menge -= menge

            if best_bid.menge == 0:
                self.bids.pop(0)

            if best_ask.menge == 0:
                self.asks.pop(0)

        return trades


class Account:
    def __init__(self, kapital, assets):
        self.kapital = kapital
        self.assets = assets

        self.reserved_kapital = 0
        self.reserved_assets = {}

        self.trades = []


class Strategie:
    def ausführen(self, händler, market, time):
        pass


class MarketMaker(Strategie):

    def __init__(
        self,
        spread,
        menge,
        max_inventory,
        inventory_skew
    ):
        self.spread = spread
        self.menge = menge
        self.max_inventory = max_inventory
        self.inventory_skew = inventory_skew

        self.market_parameter = {}

    def ausführen(self, händler, market, time):

        händler.cancel_all_orders(market)

        if market.name not in self.market_parameter:

            self.market_parameter[market.name] = {
                "spread_faktor": random.uniform(
                    0.8,
                    1.2
                ),
                "menge_faktor": random.uniform(
                    0.7,
                    1.3
                )
            }

        parameter = self.market_parameter[market.name]

        spread = (
            self.spread
            * parameter["spread_faktor"]
            * market.mm_spread_faktor
        )

        menge = round(
            self.menge
            * parameter["menge_faktor"]
            * market.mm_menge_faktor
        )

        menge = max(1, menge)

        inventory = händler.account.assets[market.name]

        ziel_inventory = self.max_inventory / 2

        inventory_deviation = (
            inventory - ziel_inventory
        ) / ziel_inventory

        skew = (
            inventory_deviation
            * self.inventory_skew
        )

        referenz_abweichung = (
            market.referenzpreis
            - market.preis
        )

        stabilisierung = (
            referenz_abweichung
            * market.reversion
        )

        mid = (
            market.preis
            + stabilisierung
            - skew
        )

        bid = mid - spread / 2
        ask = mid + spread / 2

        bid = max(
            market.tick_size,
            bid
        )

        ask = max(
            market.tick_size,
            ask
        )

        bid = round(
            bid / market.tick_size
        ) * market.tick_size

        ask = round(
            ask / market.tick_size
        ) * market.tick_size

        if inventory >= self.max_inventory:
            bid = None

        if inventory <= 0:
            ask = None

        if bid is not None:

            buy_order = Order(
                "BUY",
                bid,
                menge,
                id_generator.generate(),
                time,
                händler,
                market.name,
                "LIMIT"
            )

            händler.send_order(
                buy_order,
                time
            )

        if ask is not None:

            sell_order = Order(
                "SELL",
                ask,
                menge,
                id_generator.generate(),
                time,
                händler,
                market.name,
                "LIMIT"
            )

            händler.send_order(
                sell_order,
                time
            )


class Momentum(Strategie):

    def __init__(self, periode, menge):
        self.periode = periode
        self.menge = menge
        self.letztes_signal = {}

    def ausführen(self, händler, market, time):

        if len(market.preis_historie) < self.periode:
            return

        alter_preis = market.preis_historie[
            -self.periode
        ][1]

        aktueller_preis = market.preis

        if aktueller_preis > alter_preis:
            signal = "BUY"

        elif aktueller_preis < alter_preis:
            signal = "SELL"

        else:
            return

        if signal == self.letztes_signal.get(
            market.name,
            None
        ):
            return

        order = Order(
            signal,
            aktueller_preis,
            self.menge,
            id_generator.generate(),
            time,
            händler,
            market.name,
            "MARKET"
        )

        self.letztes_signal[
            market.name
        ] = signal

        händler.send_order(
            order,
            time
        )


class MeanReversion(Strategie):

    def __init__(self, periode, menge):
        self.periode = periode
        self.menge = menge
        self.letztes_signal = {}

    def ausführen(self, händler, market, time):

        if len(market.preis_historie) < self.periode:
            return

        lookback_window = market.preis_historie[
            -self.periode:
        ]

        preise = [
            i[1]
            for i in lookback_window
        ]

        mean = sum(preise) / len(preise)

        aktueller_preis = market.preis

        if aktueller_preis < mean:
            signal = "BUY"

        elif aktueller_preis > mean:
            signal = "SELL"

        else:
            return

        if signal == self.letztes_signal.get(
            market.name,
            None
        ):
            return

        order = Order(
            signal,
            aktueller_preis,
            self.menge,
            id_generator.generate(),
            time,
            händler,
            market.name,
            "MARKET"
        )

        self.letztes_signal[
            market.name
        ] = signal

        händler.send_order(
            order,
            time
        )


class RandomNoise(Strategie):

    def __init__(self, menge):
        self.menge = menge
        self.market_parameter = {}

    def ausführen(self, händler, market, time):

        if market.name not in self.market_parameter:

            self.market_parameter[market.name] = {
                "wahrscheinlichkeit": random.uniform(
                    market.noise_wahrscheinlichkeit * 0.7,
                    market.noise_wahrscheinlichkeit * 1.3
                ),
                "menge_faktor": random.uniform(
                    0.7,
                    1.3
                )
            }

        parameter = self.market_parameter[
            market.name
        ]

        if random.random() > parameter["wahrscheinlichkeit"]:
            return

        menge = random.randint(
            market.noise_menge_min,
            market.noise_menge_max
        )

        menge = round(
            menge
            * self.menge
            * parameter["menge_faktor"]
        )

        menge = max(1, menge)

        verfügbare_assets = (
            händler.account.assets[market.name]
            - händler.account.reserved_assets.get(
                market.name,
                0
            )
        )

        verfügbares_kapital = (
            händler.account.kapital
            - händler.account.reserved_kapital
        )

        order = Order(
            "BUY",
            market.preis,
            menge,
            id_generator.generate(),
            time,
            händler,
            market.name,
            "MARKET"
        )

        kaufkosten = händler.börse.get_order_price(
            order
        )

        buy_möglich = (
            kaufkosten is not False
            and verfügbares_kapital >= kaufkosten * 1.05
        )

        sell_möglich = (
            verfügbare_assets >= menge
        )

        if buy_möglich and sell_möglich:

            signal = random.choice([
                "BUY",
                "SELL"
            ])

        elif buy_möglich:

            signal = "BUY"

        elif sell_möglich:

            signal = "SELL"

        else:

            return

        order.side = signal

        händler.send_order(
            order,
            time
        )


class Händler:

    def __init__(
        self,
        id,
        name,
        kapital,
        assets,
        börse,
        strategie
    ):
        self.id = id
        self.name = name

        self.account = Account(
            kapital,
            assets
        )

        self.strategie = strategie
        self.trades = []
        self.orders = []

        börse.add_händler(self)

        self.börse = börse

    def __repr__(self):
        return (
            f"Händler("
            f"Name={self.name}, "
            f"ID={self.id}, "
            f"Kapital={self.account.kapital}, "
            f"asset={self.account.assets}"
            f")"
        )

    def run_strategy(self, market, time):
        self.strategie.ausführen(
            self,
            market,
            time
        )

    def send_order(self, order, time):

        MARKET_RESERVE_FACTOR = 1.05

        if order.order_type == "LIMIT":

            kosten = (
                order.preis
                * order.menge
            )

        elif order.order_type == "MARKET":

            kosten = self.börse.get_order_price(
                order
            )

            if kosten is False:
                return False

            kosten *= MARKET_RESERVE_FACTOR

        else:
            return False

        if order.side == "BUY":

            if (
                kosten
                <= self.account.kapital
                - self.account.reserved_kapital
            ):

                self.account.reserved_kapital += kosten

                order.reservierte_kosten = kosten

                self.orders.append(order)

                trades = self.börse.send_order(
                    order,
                    time
                )

                for trade in trades:

                    if (
                        trade.buy_order.händler == self
                        or
                        trade.sell_order.händler == self
                    ):
                        self.trades.append(trade)

                if order.order_type == "MARKET":

                    self.account.reserved_kapital -= (
                        order.reservierte_kosten
                    )

                    order.reservierte_kosten = 0

                    if order in self.orders:
                        self.orders.remove(order)

                elif order.menge == 0:

                    if order in self.orders:
                        self.orders.remove(order)

                return True

        elif order.side == "SELL":

            if (
                self.account.assets[
                    order.market_name
                ]
                -
                self.account.reserved_assets.get(
                    order.market_name,
                    0
                )
                >= order.menge
            ):

                self.account.reserved_assets[
                    order.market_name
                ] = (
                    self.account.reserved_assets.get(
                        order.market_name,
                        0
                    )
                    + order.menge
                )

                order.reservierte_assets = order.menge

                self.orders.append(order)

                trades = self.börse.send_order(
                    order,
                    time
                )

                for trade in trades:

                    if (
                        trade.buy_order.händler == self
                        or
                        trade.sell_order.händler == self
                    ):
                        self.trades.append(trade)

                if order.order_type == "MARKET":

                    self.account.reserved_assets[
                        order.market_name
                    ] -= order.reservierte_assets

                    order.reservierte_assets = 0

                    if order in self.orders:
                        self.orders.remove(order)

                elif order.menge == 0:

                    if order in self.orders:
                        self.orders.remove(order)

                return True

        return False

    def cancel_order(self, order):

        self.börse.cancel_order(
            order,
            self
        )

        if order in self.orders:
            self.orders.remove(order)

    def cancel_all_orders(self, market):

        for order in self.orders.copy():

            if order.market_name == market.name:

                self.cancel_order(order)


class Market:

    def __init__(
        self,
        name,
        ipo_preis,
        event_bus,
        tick_size,
        spread,
        reversion,
        mm_spread_faktor,
        mm_menge_faktor,
        noise_wahrscheinlichkeit,
        noise_menge_min,
        noise_menge_max
    ):

        self.name = name

        self.preis = ipo_preis
        self.referenzpreis = ipo_preis

        self.tick_size = tick_size
        self.spread = spread
        self.reversion = reversion

        self.mm_spread_faktor = mm_spread_faktor
        self.mm_menge_faktor = mm_menge_faktor

        self.noise_wahrscheinlichkeit = (
            noise_wahrscheinlichkeit
        )

        self.noise_menge_min = noise_menge_min
        self.noise_menge_max = noise_menge_max

        self.preis_historie = []

        self.orderbuch = Orderbuch()

        self.candles = []

        self.last_time = 0

        event_bus.subscribe(
            TradeExecuted,
            self.process_trade
        )

    def __repr__(self):
        return f"{self.name}: {self.preis}"

    def get_ohlcv(self, n):
        return self.candles[-n:]

    def new_candle(self, time, preis):

        candle_time = time.replace(
            second=0,
            microsecond=0
        )

        candle = Candle(
            candle_time,
            preis
        )

        self.candles.append(candle)

    def update_price_history(self, time):

        self.preis_historie.append(
            (
                time,
                self.preis
            )
        )

    def process_trade(self, e):

        if (
            e.trade.buy_order.market_name
            != self.name
            or
            e.trade.sell_order.market_name
            != self.name
        ):
            return

        candle_time = e.time.replace(
            second=0,
            microsecond=0
        )

        if not self.candles:

            self.new_candle(
                e.time,
                e.trade.preis
            )

            self.candles[-1].volume += (
                e.trade.menge
            )

            self.preis = e.trade.preis

            self.preis_historie.append(
                (
                    e.time,
                    e.trade.preis
                )
            )

            return

        current_candle = self.candles[-1]

        if current_candle.time != candle_time:

            self.new_candle(
                e.time,
                e.trade.preis
            )

            self.candles[-1].volume += (
                e.trade.menge
            )

        else:

            current_candle.update(
                e.trade.preis,
                e.trade.menge
            )

        self.preis = e.trade.preis


class Börse:

    def __init__(
        self,
        markets: list[Market],
        event_bus: EventBus
    ):
        self.markets = markets
        self.händler = []
        self.is_open = True
        self.event_bus = event_bus

    def __repr__(self):
        return (
            f"Börse("
            f"Markets: {self.markets}, "
            f"Händler: {self.händler}, "
            f"isOpen: {self.is_open}"
            f")"
        )

    def add_händler(self, händler):
        self.händler.append(händler)

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def send_order(self, order, time):

        if not self.is_open:
            return False

        for market in self.markets:

            if order.market_name == market.name:

                market.orderbuch.add_order(
                    order
                )

                trades = market.orderbuch.match(
                    order
                )

                for trade in trades:

                    event = TradeExecuted(
                        trade,
                        time
                    )

                    self.event_bus.publish(
                        event
                    )

                return trades

        return False

    def cancel_order(self, order, händler):

        for m in self.markets:

            if order.market_name == m.name:

                m.orderbuch.cancel_order(
                    order,
                    händler
                )

    def get_order_price(self, order):

        for market in self.markets:

            if market.name == order.market_name:

                return market.orderbuch.get_estimated_value(
                    order
                )

        return False


class Simulation:

    def __init__(self, börse):

        self.clock = Clock(
            datetime(2026, 1, 1, 9, 0),
            1
        )

        self.börse = börse

    def step(self):

        self.clock.tick()

        market_maker = []
        andere_händler = []

        for trader in self.börse.händler.copy():

            if isinstance(
                trader.strategie,
                MarketMaker
            ):

                market_maker.append(
                    trader
                )

            else:

                andere_händler.append(
                    trader
                )

        random.shuffle(
            market_maker
        )

        random.shuffle(
            andere_händler
        )

        for trader in market_maker:

            for market in self.börse.markets:

                trader.run_strategy(
                    market,
                    self.clock.time
                )

        for trader in andere_händler:

            for market in self.börse.markets:

                trader.run_strategy(
                    market,
                    self.clock.time
                )

        for market in self.börse.markets:

            market.update_price_history(
                self.clock.time
            )

    def start(self, days):

        for _ in range(
            60 * 60 * 24 * days
        ):

            self.step()


event_bus = EventBus()


markets = [

    Market(
        "XAUUSD",
        3500.00,
        event_bus,
        tick_size=0.01,
        spread=1.0,
        reversion=0.005,
        mm_spread_faktor=1.0,
        mm_menge_faktor=1.0,
        noise_wahrscheinlichkeit=0.0015,
        noise_menge_min=1,
        noise_menge_max=3
    ),

    Market(
        "S&P500",
        5600.00,
        event_bus,
        tick_size=0.25,
        spread=1.5,
        reversion=0.005,
        mm_spread_faktor=1.4,
        mm_menge_faktor=0.7,
        noise_wahrscheinlichkeit=0.0015,
        noise_menge_min=1,
        noise_menge_max=3
    ),

    Market(
        "XAGUSD",
        61.00,
        event_bus,
        tick_size=0.01,
        spread=0.15,
        reversion=0.02,
        mm_spread_faktor=0.2,
        mm_menge_faktor=1.2,
        noise_wahrscheinlichkeit=0.0025,
        noise_menge_min=2,
        noise_menge_max=6
    )
]


börse1 = Börse(
    markets,
    event_bus
)

börse1.is_open = True


statistik = Statistik()


börse1.event_bus.subscribe(
    TradeExecuted,
    statistik.trade_ausgeführt
)


for i in range(20):

    traders = [

        (
            "marketmaker",
            1000000,
            10000000,
            1000000,
            {
                market.name: 50
                for market in markets
            },
            MarketMaker(
                random.uniform(0.5, 1.5),
                random.randrange(3, 8),
                100,
                1
            )
        ),

        # (
        #     "momentum",
        #     10000,
        #     100000,
        #     10000,
        #     {
        #         market.name: 10
        #         for market in markets
        #     },
        #     Momentum(
        #         random.randrange(60 * 2, 60 * 30),
        #         random.randrange(2, 8)
        #     )
        # ),

        # (
        #     "meanreversion",
        #     10000,
        #     100000,
        #     10000,
        #     {
        #         market.name: 10
        #         for market in markets
        #     },
        #     MeanReversion(
        #         random.randrange(60 * 2, 60 * 30),
        #         random.randrange(2, 8)
        #     )
        # ),

        (
            "random",
            10000,
            100000,
            10000,
            {
                market.name: 10
                for market in markets
            },
            RandomNoise(
                1
            )
        ),
    ]

    trader = random.choice(
        traders
    )

    Händler(
        i,
        trader[0],
        random.randrange(
            trader[1],
            trader[2],
            trader[3]
        ),
        trader[4].copy(),
        börse1,
        trader[5]
    )

    Händler(
        i * i,
        "random",
        random.randrange(
            10000,
            100000,
            10000
        ),
        {
            market.name: 10
            for market in markets
        },
        börse1,
        RandomNoise(
            1
        )
    )

simulation = Simulation(börse1)

simulation.start(days=1)

print('\n',börse1,'\n')
print("Trades gesamt:",statistik.trade_count)
print("Volumen gesamt:",statistik.volume)
print("Trades pro Markt:",statistik.trades_pro_markt)
print("Volumen pro Markt:",statistik.volume_pro_markt)
print(börse1.markets[0].orderbuch.bids)
print(börse1.markets[0].orderbuch.asks)
print(börse1.markets[1].orderbuch.bids)
print(börse1.markets[1].orderbuch.asks)
print(börse1.markets[2].orderbuch.bids)
print(börse1.markets[2].orderbuch.asks)


for market in simulation.börse.markets:
    times = [t for t, _ in market.preis_historie]
    prices = [p for _, p in market.preis_historie]
    
    plt.figure(figsize=(14,7))
    plt.plot(times,prices)
    plt.title(market.name)
    plt.ylabel("Preis")
    plt.xlabel("Zeit")
    plt.grid()
    plt.show()