"""
Simulation Runner mit Concurrency für parallele Runs.

DESIGN-ENTSCHEIDUNGEN:

1. SimulationConfig als Dataclass:
   ────────────────────────────────
   Alle Parameter einer Simulation gebündelt in einem unveränderlichen Objekt.
   Ermöglicht: mehrere Configs erstellen → parallel ausführen → Ergebnisse vergleichen.

2. ProcessPoolExecutor für parallele Simulationen:
   ─────────────────────────────────────────────────
   WARUM ProcessPoolExecutor statt ThreadPoolExecutor?
   → Python GIL: Threads sind für CPU-bound Arbeit nutzlos.
     Prozesse umgehen den GIL und nutzen alle CPU-Kerne.
   → Jede Simulation ist unabhängig (kein shared state) → ideal für Prozesse.

   WARUM wird das Orderbuch NICHT parallelisiert?
   → Das Orderbuch ist inherent sequentiell: Price-Time-Priority erfordert
     deterministische Reihenfolge. Parallelisierung würde die Semantik brechen.
   → Parallelisiert werden nur UNABHÄNGIGE Simulationsläufe.

3. SimulationResult als Dataclass:
   ────────────────────────────────
   Serialisierbares Ergebnis einer Simulation. Enthält nur Daten, keine Referenzen
   auf lebende Objekte. Kann zwischen Prozessen übergeben werden.

4. run_single als Top-Level-Funktion statt Methode:
   ──────────────────────────────────────────────────
   ProcessPoolExecutor braucht pickle-bare Funktionen. Methoden von Klassen
   sind schwerer zu picklen. Top-Level-Funktion ist einfacher und robuster.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import random
from typing import Optional

from exchange_sim.models.order import reset_order_id_counter
from exchange_sim.exchange.market import Market
from exchange_sim.exchange.exchange import Exchange
from exchange_sim.strategies.strategies import (
    Trader, Strategy, MarketMaker, Momentum, MeanReversion, RandomNoise,
)


@dataclass
class TraderResult:
    """Ergebnis eines einzelnen Traders nach der Simulation."""
    trader_id: int
    name: str
    strategy_type: str
    start_capital: float
    end_capital: float
    assets: dict[str, float]
    total_trades: int
    portfolio_value: float


@dataclass
class MarketResult:
    """Ergebnis eines Marktes nach der Simulation."""
    symbol: str
    start_price: float
    end_price: float
    total_trades: int
    price_history: list[tuple[str, float]]  # (ISO timestamp, price)


@dataclass
class SimulationResult:
    """Gesamtergebnis einer Simulation. Serialisierbar für Prozess-Kommunikation."""
    run_id: int
    seed: int
    duration_seconds: int
    traders: list[TraderResult]
    markets: list[MarketResult]


@dataclass
class MarketConfig:
    """Konfiguration für einen Markt."""
    symbol: str
    initial_price: float


@dataclass
class TraderConfig:
    """Konfiguration für einen Trader-Typ."""
    name: str
    capital_min: float
    capital_max: float
    capital_step: float
    initial_assets: dict[str, float]
    strategy_factory: str  # Name der Strategie-Klasse
    strategy_params: dict  # Parameter für die Strategie


@dataclass
class SimulationConfig:
    """Vollständige Konfiguration einer Simulation.

    Alle Parameter die eine Simulation definieren. Kann serialisiert
    und an einen Prozess übergeben werden.
    """
    markets: list[MarketConfig]
    trader_configs: list[TraderConfig]
    num_traders: int = 20
    duration_days: int = 1
    tick_interval: int = 1  # Sekunden pro Tick
    seed: Optional[int] = None
    run_id: int = 0


def _create_strategy(name: str, params: dict) -> Strategy:
    """Factory für Strategien basierend auf String-Name.

    WARUM Factory-Funktion statt direkter Konstruktor-Aufruf?
    → SimulationConfig muss zwischen Prozessen serialisierbar sein.
      Strategy-Objekte sind es nicht (enthalten State).
      Deshalb speichern wir Name + Params und erzeugen erst im Prozess.
    """
    factories = {
        "MarketMaker": lambda p: MarketMaker(
            spread=p.get("spread", 1.0),
            quantity=p.get("quantity", 5),
            max_inventory=p.get("max_inventory", 100),
            skew_factor=p.get("skew_factor", 1.0),
        ),
        "Momentum": lambda p: Momentum(
            lookback=p.get("lookback", 300),
            quantity=p.get("quantity", 5),
        ),
        "MeanReversion": lambda p: MeanReversion(
            lookback=p.get("lookback", 300),
            quantity=p.get("quantity", 5),
        ),
        "RandomNoise": lambda p: RandomNoise(
            quantity=p.get("quantity", 5),
        ),
    }
    factory = factories.get(name)
    if factory is None:
        raise ValueError(f"Unbekannte Strategie: {name}")
    return factory(params)


def run_single(config: SimulationConfig) -> SimulationResult:
    """Führt eine einzelne Simulation aus.

    Top-Level-Funktion (nicht Methode), weil ProcessPoolExecutor
    pickle-bare Callables braucht.

    Args:
        config: Vollständige Simulationskonfiguration

    Returns:
        SimulationResult mit allen Ergebnissen
    """
    # Seed setzen für Reproduzierbarkeit
    seed = config.seed if config.seed is not None else random.randint(0, 2**32 - 1)
    rng = random.Random(seed)

    # Order-ID-Zähler zurücksetzen (jeder Prozess hat eigenen Zustand)
    reset_order_id_counter()

    # Märkte erstellen
    markets = [
        Market(mc.symbol, mc.initial_price) for mc in config.markets
    ]
    initial_prices = {mc.symbol: mc.initial_price for mc in config.markets}

    # Exchange erstellen
    exchange = Exchange(markets)
    exchange.is_open = True

    # Trader erstellen
    start_capitals: dict[int, float] = {}
    for i in range(config.num_traders):
        tc = rng.choice(config.trader_configs)
        capital = rng.randrange(
            int(tc.capital_min), int(tc.capital_max), int(tc.capital_step)
        )
        # Strategy mit zufälligen Parametern erstellen
        params = dict(tc.strategy_params)
        # Zufällige Variation der Parameter
        if "spread" in params and isinstance(params["spread"], list):
            params["spread"] = rng.choice(params["spread"])
        if "quantity" in params and isinstance(params["quantity"], list):
            params["quantity"] = rng.choice(params["quantity"])
        if "lookback" in params and isinstance(params["lookback"], list):
            params["lookback"] = rng.choice(params["lookback"])

        strategy = _create_strategy(tc.strategy_factory, params)
        assets = {m.symbol: tc.initial_assets.get(m.symbol, 0.0) for m in markets}

        trader = Trader(i, tc.name, capital, assets, exchange, strategy)
        start_capitals[i] = capital

    # Simulation laufen lassen
    total_ticks = 60 * 60 * 24 * config.duration_days
    current_time = datetime(2026, 1, 1, 9, 0)
    dt = timedelta(seconds=config.tick_interval)

    for _ in range(total_ticks):
        current_time += dt

        for trader in exchange.traders:
            for market in exchange.markets:
                trader.run_strategy(market, current_time)

        exchange.record_prices(current_time)

    # Ergebnisse sammeln
    current_prices = {m.symbol: m.price for m in exchange.markets}

    trader_results = []
    for trader in exchange.traders:
        trader_results.append(TraderResult(
            trader_id=trader.trader_id,
            name=trader.name,
            strategy_type=type(trader.strategy).__name__,
            start_capital=start_capitals[trader.trader_id],
            end_capital=trader.account.capital,
            assets=dict(trader.account.assets),
            total_trades=trader.account.total_trades,
            portfolio_value=trader.account.portfolio_value(current_prices),
        ))

    market_results = []
    for mc, market in zip(config.markets, exchange.markets):
        # Preis-Historie auf max 1000 Punkte reduzieren (für Serialisierung)
        history = list(market.price_history)
        step = max(1, len(history) // 1000)
        sampled = history[::step]
        market_results.append(MarketResult(
            symbol=market.symbol,
            start_price=mc.initial_price,
            end_price=market.price,
            total_trades=len(market.candles),
            price_history=[(t.isoformat(), p) for t, p in sampled],
        ))

    return SimulationResult(
        run_id=config.run_id,
        seed=seed,
        duration_seconds=total_ticks,
        traders=trader_results,
        markets=market_results,
    )


class SimulationRunner:
    """Führt eine oder mehrere Simulationen aus, optional parallel.

    Einzelne Simulation: run_single()
    Mehrere Simulationen: run_parallel() mit ProcessPoolExecutor

    WARUM ProcessPoolExecutor?
    → Jede Simulation ist unabhängig (kein shared state).
    → CPU-bound: GIL blockiert Threads, Prozesse umgehen das.
    → Beispiel: 4 Simulationen auf 4 Kernen → ~4x Speedup.
    """

    @staticmethod
    def run(config: SimulationConfig) -> SimulationResult:
        """Führt eine einzelne Simulation aus."""
        return run_single(config)

    @staticmethod
    def run_parallel(
        configs: list[SimulationConfig],
        max_workers: int | None = None,
    ) -> list[SimulationResult]:
        """Führt mehrere Simulationen parallel aus.

        Args:
            configs: Liste von Simulationskonfigurationen
            max_workers: Maximale Anzahl paralleler Prozesse (default: CPU-Kerne)

        Returns:
            Liste von Ergebnissen, sortiert nach run_id
        """
        results: list[SimulationResult] = []

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(run_single, config): config.run_id
                for config in configs
            }

            for future in as_completed(futures):
                result = future.result()
                results.append(result)

        # Sortiert nach run_id für deterministische Reihenfolge
        results.sort(key=lambda r: r.run_id)
        return results
