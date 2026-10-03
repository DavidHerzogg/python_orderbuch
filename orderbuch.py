from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import random
from id_generator import IDGenerator

id_generator = IDGenerator()

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
        self.id = id
        self.zeit = zeit
        self.händler = händler
        self.market_name = market_name
        self.order_type = order_type

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
            f"    Typ: {self.order_typ}\n"
            f"}}"
        )
    
    def __repr__(self):
        return (
            f"{{ Side: {self.side}, Preis: {self.preis}, Menge: {self.menge}, ID: {self.id}, Zeit: {self.zeit}, Händler: {self.händler}, Markt: {self.market_name}}}"
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
        return (f"Trade(Preis={self.preis}, Menge={self.menge}, Buy-ID={self.buy_order.id}, Sell-ID={self.sell_order.id})")

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

        if self.sell_order.order_type == "LIMIT":
            verkäufer.reserved_assets[self.sell_order.market_name] -= self.menge

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
            self.bids.sort(key=lambda order: (-order.preis, order.zeit))

        elif order.side == "SELL":
            self.asks.append(order)
            self.asks.sort(key=lambda order: (order.preis, order.zeit))

    def cancel_order(self, order, händler):
        if order.order_type == "MARKET":
            return
        for ord in self.bids:
            if ord.id == order.id:
                if ord.händler != händler:
                    return False
                händler.account.reserved_kapital -= ord.preis * ord.menge
                self.bids.remove(ord)
                return True

        for ord in self.asks:
            if ord.id == order.id:
                if ord.händler != händler:
                    return False
                
                händler.account.reserved_assets[order.market_name] = (
                    händler.account.reserved_assets.get(order.market_name, 0) - ord.menge
                )
                self.asks.remove(ord)
                return True

        return False
    
    def get_estimated_value(self, order):
        remaining = order.menge
        estimated_value = 0
        if order.side == "BUY":
            for ask in self.asks:
                menge = min(remaining, ask.menge)
                estimated_value += menge * ask.preis
                remaining -= menge
                if remaining <= 0:
                    break
        elif order.side == "SELL":
            for bid in self.bids:
                menge = min(remaining, bid.menge)
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
            if order.side == "BUY":
                if self.asks:
                    best_ask = self.asks[0]
                    menge = min(order.menge, best_ask.menge)
                    trade = Trade(
                        best_ask.preis,
                        menge,
                        order,
                        best_ask
                    )
                    self.trades.append(trade)
                    trades.append(trade)
                    trade.execute()
                    best_ask.menge -= menge
                    if best_ask.menge == 0:
                        self.asks.pop(0)
                    return trades
            elif order.side == "SELL":
                if self.bids:
                    best_bid = self.bids[0]
                    menge = min(best_bid.menge, order.menge)
                    trade = Trade(
                        best_bid.preis,
                        menge,
                        best_bid,
                        order
                    )
                    self.trades.append(trade)
                    trades.append(trade)
                    trade.execute()
                    best_bid.menge -= menge
                    if best_bid.menge == 0:
                        self.bids.pop(0)
                    return trades
            else: return
        
        while self.bids and self.asks:

            best_bid = self.bids[0]
            best_ask = self.asks[0]

            if best_bid.preis < best_ask.preis:
                break

            if best_bid.preis >= best_ask.preis :
                menge = min(best_bid.menge, best_ask.menge)

                trade = Trade(
                    best_ask.preis,
                    menge,
                    best_bid,
                    best_ask,
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
        self.assets = assets #{}

        self.reserved_kapital = 0
        self.reserved_assets = {}

        self.trades = []

class Strategie:
    def ausführen(self, händler, market, time):
        pass
    
class MarketMaker(Strategie):
    def __init__(self, spread, menge, max_inventory, inventory_skew):
        self.spread = spread
        self.menge = menge
        self.max_inventory = max_inventory
        self.inventory_skew = inventory_skew

    def ausführen(self, händler, market, time):

        händler.cancel_all_orders(market)

        inventory = händler.account.assets[market.name]

        inventory_ratio = inventory / self.max_inventory

        skew = inventory_ratio * self.inventory_skew

        mid = market.preis - skew

        bid = mid - self.spread / 2
        ask = mid + self.spread / 2

        if inventory >= self.max_inventory:
            bid = None

        if inventory <= 0:
            ask = None

        if bid is not None:
            buy_order = Order(
                "BUY",
                bid,
                self.menge,
                id_generator.generate(),
                time,
                händler,
                market.name,
                "LIMIT"
            )

            händler.send_order(buy_order, time)

        if ask is not None:
            sell_order = Order(
                "SELL",
                ask,
                self.menge,
                id_generator.generate(),
                time,
                händler,
                market.name,
                "LIMIT"
            )

            händler.send_order(sell_order, time)
        
    
class Momentum(Strategie):
    def __init__(self, periode, menge):
        self.periode = periode
        self.menge = menge
        self.letztes_signal = {}
        
    def ausführen(self, händler, market, time):
        if len(market.preis_historie) < self.periode:
            return
        alter_preis = market.preis_historie[-self.periode][1]
        aktueller_preis = market.preis
        
        if aktueller_preis > alter_preis:
            signal = "BUY"
        elif aktueller_preis < alter_preis:
            signal = "SELL"
        else:
            return
        
        if signal == self.letztes_signal.get(market.name, None):
            return
        
        if (signal == "BUY"):
            order = Order("BUY", aktueller_preis, self.menge, id_generator.generate(), time, händler, market.name, "MARKET")
            self.letztes_signal[market.name] = signal
            händler.send_order(order, time)
        elif (signal == "SELL"):
            order = Order("SELL", aktueller_preis, self.menge, id_generator.generate(), time, händler, market.name, "MARKET")
            self.letztes_signal[market.name] = signal
            händler.send_order(order, time)

class MeanReversion(Strategie):
    def __init__(self, periode, menge):
        self.periode = periode
        self.menge = menge
        self.letztes_signal = {}
        
    def ausführen(self, händler, market, time):
        if len(market.preis_historie) < self.periode:
            return
        lookback_window = market.preis_historie[-self.periode:]
        preise = [i[1] for i in lookback_window]
        mean = sum(preise) / len(preise)
        aktueller_preis = market.preis
        
        if aktueller_preis < mean:
            signal = "BUY"
        elif aktueller_preis > mean:
            signal = "SELL"
        else:
            return
        
        if signal == self.letztes_signal.get(market.name, None):
            return
        
        if signal == "BUY":
            order = Order("BUY", aktueller_preis, self.menge, id_generator.generate(), time, händler, market.name, "MARKET")
        if signal == "SELL":
            order = Order("SELL", aktueller_preis, self.menge, id_generator.generate(), time, händler, market.name, "MARKET")
            
        self.letztes_signal[market.name] = signal
        händler.send_order(order, time)
      
class RandomNoise(Strategie):
    def __init__(self, menge):
        self.menge = menge
        
    def ausführen(self, händler, market, time):
        signal = random.choice(["BUY", "SELL"])
        
        order = Order(signal, market.preis, self.menge, id_generator.generate(), time, händler, market.name, "MARKET")
        händler.send_order(order, time)

class Händler:
    def __init__(self, id, name, kapital, assets, börse, strategie):
        self.id = id
        self.name = name
        self.account = Account(kapital, assets)
        self.strategie = strategie
        self.trades = []
        self.orders = []
        börse.add_händler(self)
        self.börse = börse

    def __repr__(self):
            return (f"Händler(Name={self.name}, ID={self.id}, Kapital={self.account.kapital}, asset={self.account.assets})")

    def run_strategy(self, market, time):
        self.strategie.ausführen(self, market, time)

    def send_order(self, order, time):
        MARKET_RESERVE_FACTOR = 1.05
        if order.order_type == "LIMIT":
            kosten = order.preis * order.menge
        if order.order_type == "MARKET":
            kosten = self.börse.get_order_price(order) * MARKET_RESERVE_FACTOR
        if (kosten <= self.account.kapital - self.account.reserved_kapital) and (order.side == "BUY"):
            self.account.reserved_kapital += kosten
            self.orders.append(order)
            self.börse.send_order(order, time)
            return True
        elif (self.account.assets[order.market_name] - self.account.reserved_assets.get(order.market_name, 0) >= order.menge) and (order.side == "SELL"):
            self.account.reserved_assets[order.market_name] = (
                self.account.reserved_assets.get(order.market_name, 0) + order.menge
            )
            self.orders.append(order)
            trades = self.börse.send_order(order, time)
            for trade in trades:
                if (trade.buy_order.händler == self) or (trade.sell_order.händler == self):
                    self.trades.append(trade)
            return True
        return False

    def cancel_order(self, order):
        self.börse.cancel_order(order, self)
        if order in self.orders:
            self.orders.remove(order)
            
    def cancel_all_orders(self, market):
        for order in self.orders.copy():
            if order.market_name == market.name:
                self.cancel_order(order)

class Market:
    def __init__(self, name, ipo_preis):
        self.name = name
        self.preis = ipo_preis
        self.preis_historie = []
        self.orderbuch = Orderbuch()
        self.candles = []
        self.last_time = 0
        
    def __repr__(self):
        return f"{self.name}: {self.preis}"
    
    def get_ohlcv(self, n):
        return self.candles[-n:]
    
    def new_candle(self, time, preis):
        candle_time = time.replace(second=0, microsecond=0)
        
        candle = Candle(
            candle_time,
            preis
        )
        
        self.candles.append(candle)
    
    def update_price_history(self, time):
        self.preis_historie.append((time, self.preis))
    
    def process_trade(self, trade, time):
        candle_time = time.replace(second=0, microsecond=0)
        
        if not self.candles:
            self.new_candle(time, trade.preis)
            self.preis = trade.preis
            self.preis_historie.append((time, trade.preis))
            return
        
        current_candle = self.candles[-1]
        
        if current_candle.time != candle_time:
            self.new_candle(time, trade.preis)
        else:
            current_candle.update(trade.preis, trade.menge)
        
        self.preis = trade.preis

class Börse:
    def __init__(self, markets: list[Market]):
        self.markets = markets
        self.händler = []
        self.is_open = True

    def __repr__(self):
        return f"Börse(Markets: {self.markets}, Händler: {self.händler}, isOpen: {self.is_open})"

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
                market.orderbuch.add_order(order)
                trades = market.orderbuch.match(order)
                for trade in trades:
                    market.process_trade(trade, time)
                return trades
        return False

    def cancel_order(self, order, händler):
        for m in self.markets:
            if order.market_name == m.name:
                m.orderbuch.cancel_order(order, händler)
                
    def get_order_price(self, order):
        for market in self.markets:
            if market.name == order.market_name:
                return market.orderbuch.get_estimated_value(order)
                        

class Simulation:
    def __init__(self, börse):
        self.clock = Clock(datetime(2026, 1, 1, 9, 0),1)
        self.börse = börse

    def step(self):
        self.clock.tick()

        for trader in self.börse.händler:
            for market in self.börse.markets:
                trader.run_strategy(market,self.clock.time)
        
        for market in self.börse.markets:
            market.update_price_history(self.clock.time)
        
    def start(self, days):
        for _ in range(60*60*24*days):
            self.step()


markets = [Market("XAUUSD", 3500.00), Market("S&P500", 5600.00), Market("XAGUSD", 61.00)]
börse1 = Börse(markets)
börse1.is_open = True

for i in range(20):
    traders = [
        ("marketmaker", 100000, 1000000, 100000, {market.name: 10 for market in markets}, MarketMaker(random.randrange(1, 4)*0.5, random.randrange(3, 10), 100, 1)),
        ("momentum", 10000, 100000, 10000, {market.name: 10 for market in markets}, Momentum(random.randrange(60*2, 60*30), random.randrange(2, 8))),
        ("meanreversion", 10000, 100000, 10000, {market.name: 10 for market in markets}, MeanReversion(random.randrange(60*2, 60*30), random.randrange(2, 8))),
        ("random", 10000, 100000, 10000, {market.name: 10 for market in markets}, RandomNoise(random.randrange(2, 8))),
    ]
    trader = random.choice(traders)
    Händler(i, trader[0], random.randrange(trader[1], trader[2], trader[3]), trader[4], börse1, trader[5])

simulation = Simulation(börse1)
simulation.start(days=1)

print('\n',börse1,'\n')

print(börse1.markets[0].orderbuch.bids)
print(börse1.markets[0].orderbuch.asks)
print(börse1.markets[1].orderbuch.bids)
print(börse1.markets[1].orderbuch.asks)
print(börse1.markets[2].orderbuch.bids)
print(börse1.markets[2].orderbuch.asks)

for market in simulation.börse.markets:
    times = [t for t, _ in market.preis_historie]
    prices = [p for _, p in market.preis_historie]
    plt.plot(times, prices)
    plt.show()


# 1. Strategien ~
# 2. Ausgabe Daten ~

# 20 Händler: Startwert, Endwert, Trades, Strategie, Assets

# Orderbuch Simulation in der console