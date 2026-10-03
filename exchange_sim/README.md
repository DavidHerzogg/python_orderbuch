# Exchange Simulation

Eine professionelle Börsen- und Orderbuch-Simulation in Python mit Fokus auf sauberes OOP, effiziente Datenstrukturen und gutes System Design.

## Architektur

```
exchange_sim/
├── models/            # Domänenmodelle (Order, Trade)
│   ├── order.py       # Order mit Enums, Dataclass, Partial Fill
│   └── trade.py       # Unveränderlicher Trade (frozen dataclass)
├── orderbook/         # Orderbuch-Kern
│   ├── orderbook.py   # SortedDict-basiertes Orderbuch
│   └── matching.py    # Price-Time-Priority MatchingEngine
├── exchange/          # Börsen-Infrastruktur
│   ├── account.py     # Account mit Settlement
│   ├── market.py      # Markt + Candles
│   └── exchange.py    # Exchange-Fassade
├── strategies/        # Handelsstrategien
│   └── strategies.py  # ABC + MarketMaker, Momentum, MeanReversion, Random
├── simulation/        # Simulation
│   └── runner.py      # SimulationRunner mit ProcessPoolExecutor
├── tests/             # pytest-Tests
│   ├── test_orderbook.py
│   ├── test_matching.py
│   └── test_simulation.py
└── main.py            # Einstiegspunkt
```

## Verwendung

### Einzelne Simulation

```bash
cd "oop und objekte"
python -m exchange_sim.main
```

### Mit Parametern

```bash
python -m exchange_sim.main --days 1 --traders 20 --seed 42
```

### Parallele Simulationen

```bash
python -m exchange_sim.main --runs 4
```

### Tests ausführen

```bash
pytest exchange_sim/tests/ -v
```

## Kernkonzepte

### Order-Lebenszyklus

```
Order erstellt → Trader validiert → Exchange empfängt → MatchingEngine matcht
    │                                                          │
    └── LIMIT: ins Buch ←──── nicht vollständig gefüllt ────────┤
                                                               │
    Trade erzeugt ←──── Match gefunden ────────────────────────┘
         │
         └── Account.settle_trade() → Kontobuchung
```

### Orderbuch-Datenstruktur

```
Bids (Kauforders):                  Asks (Verkaufsorders):
SortedDict(-price → PriceLevel)     SortedDict(price → PriceLevel)

Price 101.0: [Order₁, Order₂]       Price 102.0: [Order₅]
Price 100.0: [Order₃]               Price 103.0: [Order₆, Order₇]
Price  99.0: [Order₄]               Price 105.0: [Order₈]

← höchster Bid zuerst               niedrigster Ask zuerst →
```

Jedes PriceLevel enthält eine `deque` (FIFO-Queue) für Time-Priority.

### Strategien (Polymorphie)

Alle Strategien erben von `Strategy` (ABC) und implementieren `execute()`:

| Strategie | Logik |
|-----------|-------|
| **MarketMaker** | Stellt Bid+Ask-Quotes, Inventory-Skew |
| **Momentum** | Kauft bei steigendem Trend, verkauft bei fallendem |
| **MeanReversion** | Kauft unter Durchschnitt, verkauft darüber |
| **RandomNoise** | Zufällige Orders, erzeugt Liquidität |

### Concurrency

```
ProcessPoolExecutor
├── Prozess 1: Simulation(seed=42)  ──→ SimulationResult
├── Prozess 2: Simulation(seed=43)  ──→ SimulationResult
├── Prozess 3: Simulation(seed=44)  ──→ SimulationResult
└── Prozess 4: Simulation(seed=45)  ──→ SimulationResult
```

Jede Simulation ist unabhängig (kein shared state) → ideal für Prozesse.
Das zentrale Orderbuch bleibt deterministisch und single-threaded.

## Abhängigkeiten

- `sortedcontainers` – SortedDict für effizientes Orderbuch
- `pytest` – Tests
