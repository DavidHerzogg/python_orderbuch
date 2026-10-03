# Design-Entscheidungen

Dieses Dokument erklärt die wichtigsten Architektur- und Datenstrukturentscheidungen.

---

## 1. Orderbuch: `SortedDict[float, deque[Order]]`

### Problem (vorheriger Code)

```python
# O(n log n) bei jedem Insert!
self.bids.append(order)
self.bids.sort(key=lambda order: (-order.preis, order.zeit))
```

Bei jeder neuen Order wird die gesamte Liste neu sortiert. Python's `sort()` nutzt Timsort mit O(n log n) worst-case. Bei 10.000 Orders im Buch: ~130.000 Vergleiche pro Insert.

### Lösung

```
SortedDict[float, PriceLevel]
     └── PriceLevel = (price, deque[Order], total_qty)
```

| Operation | Vorher (list + sort) | Nachher (SortedDict + deque) |
|-----------|---------------------|------------------------------|
| Insert | O(n log n) | O(log P) |
| Best Price | O(1)* | O(log P) |
| Cancel | O(n) | O(1) lookup + O(k) remove |
| Iteration | O(n) | O(P) |

*P = Anzahl verschiedener Preise, k = Orders pro Level (typisch < 10)*

### Warum SortedDict statt Alternativen?

| Alternative | Problem |
|-------------|---------|
| `heapq` | Kein effizientes Cancel (lazy-delete nötig), keine Iteration über Levels |
| `bisect.insort` | O(n) für Insert in Liste (Verschiebung), O(n) Cancel |
| `dict + sorted()` | Sortierung on-demand O(P log P), kein inkrementeller Insert |

`SortedDict` (B-Tree intern) bietet O(log P) für alle Operationen und erlaubt Iteration über Levels für Markttiefe-Anzeige.

### Warum `deque` statt `list` pro Level?

```python
# deque.popleft() = O(1)  ← FIFO: älteste Order zuerst matchen
# list.pop(0) = O(n)      ← Verschiebung aller Elemente
```

Time-Priority erfordert FIFO. `deque` ist dafür optimiert.

### Warum negierter Key für Bids?

```python
self._bids: SortedDict[float, PriceLevel]  # key = -price
```

`SortedDict` sortiert aufsteigend. Bids brauchen absteigend (höchster Preis zuerst). Negierung dreht die Sortierung um. `peekitem(0)` gibt immer den besten Preis. Alternative wäre ein custom Comparator, aber Negierung ist einfacher und hat keinen Overhead.

---

## 2. Trennung OrderBook / MatchingEngine

### Vorher

```python
class Orderbuch:
    def add_order(self, order): ...
    def cancel_order(self, order, händler): ...
    def match(self, order): ...  # Matching + Settlement vermischt!
```

`match()` war eine Methode des Orderbuchs und hat direkt `trade.execute()` aufgerufen, was Account-Felder manipuliert hat. Drei Verantwortlichkeiten in einer Klasse.

### Nachher

```
OrderBook      → Datenstruktur (add, remove, peek, cancel)
MatchingEngine → Algorithmus (match orders, erzeugt Trades)
Account        → Settlement (settle_trade ändert Kapital/Assets)
```

**Warum?**
- **Testbarkeit:** OrderBook-Tests brauchen keine MatchingEngine
- **Austauschbarkeit:** Matching-Algorithmus ändern (z.B. Pro-Rata) ohne OrderBook zu ändern
- **Single Responsibility:** Jede Klasse hat genau eine Aufgabe

---

## 3. `Trade` als `frozen=True` Dataclass

### Vorher

```python
class Trade:
    def execute(self):
        käufer.kapital -= wert
        käufer.assets[...] += self.menge
        verkäufer.kapital += wert
```

Trade war gleichzeitig Datum UND Aktor. Es manipulierte direkt fremde Objekte.

### Nachher

```python
@dataclass(frozen=True)
class Trade:
    price: float
    quantity: float
    buyer_id: int
    seller_id: int
    ...
```

**Trade ist ein historisches Faktum.** Es passiert, wird aufgezeichnet, und ändert sich nie.
Settlement ist Aufgabe des Accounts, nicht des Trades.

**Vorteile von `frozen=True`:**
- Immutability → kann nicht versehentlich verändert werden
- Hashable → kann in Sets/Dicts gespeichert werden
- Serialisierbar → kann zwischen Prozessen übergeben werden

---

## 4. Market-Order Full Fill

### Vorher (Bug)

```python
# Market-Buy matcht nur gegen EINE Ask-Order, dann return!
if order.side == "BUY":
    if self.asks:
        best_ask = self.asks[0]
        menge = min(order.menge, best_ask.menge)
        # ... nur EIN Trade
        return trades  # ← vorzeitiger Return!
```

Market-Buy mit Menge 100 gegen [Ask(50), Ask(50)] erzeugt nur einen Trade mit 50. Die restlichen 50 gehen verloren.

### Nachher

Ein einheitlicher While-Loop für Market UND Limit-Orders:

```python
while aggressor.remaining_qty > 0:
    resting = self._book._peek_best(contra_side)
    if resting is None:
        break
    if aggressor.order_type == OrderType.LIMIT:
        if not self._prices_cross(aggressor, resting):
            break
    # Match + Fill...
```

**Warum ein einheitlicher Loop?**
- Weniger Code-Duplizierung (Market/Limit-Logik war vorher separat)
- Market-Orders sind einfach Limit-Orders ohne Preis-Check
- Partial Fills werden automatisch über den Loop behandelt

---

## 5. `Enum` statt Strings

### Vorher

```python
order.side == "BUY"           # Typo-anfällig: "buy", "Buy", "BUy"
order.order_type == "MARKET"  # Keine IDE-Autovervollständigung
```

### Nachher

```python
class Side(Enum):
    BUY = auto()
    SELL = auto()

# Side.BUY == Side.BUY  ✓
# Side.BUY == "BUY"     ✗ (bewusst, verhindert String-Vergleiche)
```

**Vorteile:**
- Compile-time (Import-time) Fehlererkennung statt Runtime
- IDE-Autovervollständigung und Refactoring-Support
- Exhaustive Pattern Matching möglich

---

## 6. `@dataclass` vs. manuelles `__init__`

### Vorher

```python
class Order:
    def __init__(self, side, preis, menge, id, zeit, händler, market_name, order_type):
        self.side = side
        self.preis = preis
        self.menge = menge
        # ... 8 Zeilen Boilerplate
```

### Nachher

```python
@dataclass
class Order:
    side: Side
    order_type: OrderType
    symbol: str
    quantity: float
    price: float
    timestamp: datetime
    trader_id: int
```

**Vorteile:**
- `__init__`, `__repr__`, `__eq__` automatisch generiert
- Type Hints sind Teil der Deklaration (nicht optional)
- `field(default_factory=...)` für mutable Defaults (statt `None`-Check)

---

## 7. Concurrency: `ProcessPoolExecutor`

### Warum Prozesse statt Threads?

```python
# Python GIL: Nur EIN Thread kann gleichzeitig Python-Code ausführen
# → CPU-bound Code hat KEINEN Speedup mit Threads!

# ProcessPoolExecutor: Jeder Prozess hat eigenen GIL
# → Echter Parallelismus auf mehreren CPU-Kernen
```

### Was wird parallelisiert?

```
✓ Unabhängige Simulationsläufe (verschiedene Seeds/Configs)
✗ Das zentrale Orderbuch (inherent sequentiell: Price-Time-Priority)
```

**Warum nicht das Orderbuch parallelisieren?**
- Price-Time-Priority erfordert deterministische Reihenfolge
- Orders müssen sequentiell verarbeitet werden (Order A kann den Preis ändern, der für Order B relevant ist)
- Locking würde den Vorteil der Parallelisierung auffressen

### Trade-off

| | Single Process | Multi Process |
|--|----------------|---------------|
| **Overhead** | Keiner | Prozess-Start + Serialisierung |
| **Speedup** | 1x | ~Nx (N = Kerne) |
| **Komplexität** | Einfach | Config/Result müssen serialisierbar sein |
| **Wann nutzen** | 1 Simulation | Vergleich mehrerer Configs |

---

## 8. Reservierungssystem (übernommen und verbessert)

Dein Reservierungssystem war eine gute Idee! Es verhindert "Double Spending":

```
Kapital: 10.000
Order A: Reserve 5.000 → Verfügbar: 5.000
Order B: Reserve 5.000 → Verfügbar: 0
Order C: Reserve 1.000 → ABGELEHNT (0 < 1.000)
```

**Verbesserungen:**
- `available_capital` als Property (berechnet immer aktuellen Wert)
- `reserve_capital()` gibt `bool` zurück (statt silent fail)
- `release_capital()` in Account gekapselt (statt verstreut über Orderbuch und Händler)

---

## 9. Exchange als Fassade

### Vorher

```python
class Börse:
    def send_order(self, order, time):
        for market in self.markets:           # O(n) linearer Scan
            if order.market_name == market.name:
                ...
```

### Nachher

```python
class Exchange:
    def __init__(self, markets):
        self._markets = {m.symbol: m for m in markets}  # O(1) Lookup

    def submit_order(self, order, timestamp):
        market = self._markets.get(order.symbol)        # O(1)
```

**Bei 3 Märkten: irrelevant. Bei 100+ Märkten: signifikant.**
Dict-Lookup ist O(1) amortisiert vs. O(n) linearer Scan.
