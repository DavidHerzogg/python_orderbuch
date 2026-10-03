"""
main.py – Einstiegspunkt für die Simulation.

Führt eine Simulation mit der gleichen Konfiguration wie dein
ursprünglicher Code aus (3 Märkte, 20 Trader, 4 Strategietypen).
"""

import sys
import os

# Projektverzeichnis zum Suchpfad hinzufügen
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from exchange_sim.simulation.runner import (
    SimulationRunner, SimulationConfig, MarketConfig, TraderConfig,
)


def create_default_config(run_id: int = 0, seed: int | None = None) -> SimulationConfig:
    """Erstellt die Standard-Konfiguration (entspricht deinem ursprünglichen Setup).

    3 Märkte: XAUUSD, S&P500, XAGUSD
    20 Trader mit zufälliger Strategie aus 4 Typen
    1 Tag Simulation bei 1-Sekunden-Ticks
    """
    markets = [
        MarketConfig("XAUUSD", 3500.00),
        MarketConfig("SP500", 5600.00),
        MarketConfig("XAGUSD", 61.00),
    ]

    initial_assets = {m.symbol: 10.0 for m in markets}

    trader_configs = [
        TraderConfig(
            name="marketmaker",
            capital_min=100_000,
            capital_max=1_000_000,
            capital_step=100_000,
            initial_assets=initial_assets,
            strategy_factory="MarketMaker",
            strategy_params={
                "spread": [0.5, 1.0, 1.5],    # zufällige Auswahl
                "quantity": [3, 4, 5, 6, 7, 8, 9],
                "max_inventory": 100,
                "skew_factor": 1.0,
            },
        ),
        TraderConfig(
            name="momentum",
            capital_min=10_000,
            capital_max=100_000,
            capital_step=10_000,
            initial_assets=initial_assets,
            strategy_factory="Momentum",
            strategy_params={
                "lookback": [120, 300, 600, 900, 1800],
                "quantity": [2, 3, 4, 5, 6, 7],
            },
        ),
        TraderConfig(
            name="meanreversion",
            capital_min=10_000,
            capital_max=100_000,
            capital_step=10_000,
            initial_assets=initial_assets,
            strategy_factory="MeanReversion",
            strategy_params={
                "lookback": [120, 300, 600, 900, 1800],
                "quantity": [2, 3, 4, 5, 6, 7],
            },
        ),
        TraderConfig(
            name="random",
            capital_min=10_000,
            capital_max=100_000,
            capital_step=10_000,
            initial_assets=initial_assets,
            strategy_factory="RandomNoise",
            strategy_params={
                "quantity": [2, 3, 4, 5, 6, 7],
            },
        ),
    ]

    return SimulationConfig(
        markets=markets,
        trader_configs=trader_configs,
        num_traders=20,
        duration_days=1,
        tick_interval=1,
        seed=seed,
        run_id=run_id,
    )


def print_results(result) -> None:
    """Gibt die Simulationsergebnisse formatiert aus."""
    print(f"\n{'='*60}")
    print(f"  Simulation #{result.run_id} | Seed: {result.seed}")
    print(f"  Dauer: {result.duration_seconds:,} Ticks")
    print(f"{'='*60}")

    # Markt-Ergebnisse
    print(f"\n{'─'*40}")
    print("  MÄRKTE")
    print(f"{'─'*40}")
    for m in result.markets:
        change = ((m.end_price - m.start_price) / m.start_price) * 100
        arrow = "▲" if change >= 0 else "▼"
        print(f"  {m.symbol:10s}  {m.start_price:>10.2f} → {m.end_price:>10.2f}  "
              f"{arrow} {change:+.2f}%  ({m.total_trades} candles)")

    # Trader-Ergebnisse
    print(f"\n{'─'*40}")
    print("  TRADER")
    print(f"{'─'*40}")
    print(f"  {'ID':>3s} {'Name':12s} {'Strategie':14s} {'Start':>10s} "
          f"{'Portfolio':>10s} {'Trades':>6s}")
    print(f"  {'─'*3} {'─'*12} {'─'*14} {'─'*10} {'─'*10} {'─'*6}")

    for t in sorted(result.traders, key=lambda x: x.portfolio_value, reverse=True):
        print(f"  {t.trader_id:>3d} {t.name:12s} {t.strategy_type:14s} "
              f"{t.start_capital:>10,.0f} {t.portfolio_value:>10,.0f} "
              f"{t.total_trades:>6d}")


def main() -> None:
    """Hauptprogramm: Einzelne Simulation oder parallele Vergleiche."""
    import argparse

    parser = argparse.ArgumentParser(description="Börsen-Simulation")
    parser.add_argument("--runs", type=int, default=1,
                        help="Anzahl paralleler Simulationen (default: 1)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random Seed (für Reproduzierbarkeit)")
    parser.add_argument("--days", type=int, default=1,
                        help="Simulationsdauer in Tagen (default: 1)")
    parser.add_argument("--traders", type=int, default=20,
                        help="Anzahl Trader (default: 20)")
    args = parser.parse_args()

    if args.runs == 1:
        # Einzelne Simulation
        print("Starte Simulation...")
        config = create_default_config(run_id=0, seed=args.seed)
        config.duration_days = args.days
        config.num_traders = args.traders
        result = SimulationRunner.run(config)
        print_results(result)
    else:
        # Parallele Simulationen
        print(f"Starte {args.runs} parallele Simulationen...")
        configs = []
        for i in range(args.runs):
            config = create_default_config(run_id=i)
            config.duration_days = args.days
            config.num_traders = args.traders
            configs.append(config)

        results = SimulationRunner.run_parallel(configs)
        for result in results:
            print_results(result)


if __name__ == "__main__":
    main()
