# HFT-BOT Architecture & Implementation Guide

## Complete System Design

### System Overview

The HFT-BOT-MT5 system implements a five-tier institutional-grade AI trading architecture with the following flow:

```
Raw Market Data
      ↓
[Tier 01] Data Engine (Feature Engineering)
      ↓
Market Feature Packets (JSON over ZeroMQ/Redis)
      ↓
[Tier 02] Prediction Engine (Hybrid AI Ensemble)
      ↓
Prediction Packets
      ↓
[Tier 03] Trade Planner (Adaptive Ladders)
      ↓
Trade Plan Packets
      ↓
[Tier 04] MT5 Execution Engine (EA) ←→ Broker Orders
      ↓
Execution State Packets
      ↓
[Tier 05] Ratchet Exit Manager (Profit Protection)
      ↓
Exit Signals → [Tier 04] for Closure
```

## Tier Specifications

### Tier 01: Multi-Modal Data Engine

**Responsibilities:**
- Connect to MT5 via Python API with auto-reconnection
- Ingest real-time tick data (bid, ask, volume)
- Aggregate ticks into 1-minute OHLC candles
- Compute multi-modal features:
  - Volatility: ATR, realized volatility
  - Momentum: price slope, returns
  - Microstructure: bid-ask imbalance, order flow
  - Correlations: cross-asset relationships
- Detect and recover from data gaps
- Publish synchronized `MarketFeaturePacket` periodically

**Key Classes:**
- `MarketConnector` - Abstract connector interface
- `MT5Connector` - MT5-specific implementation
- `StreamIngestion` - Multi-stream buffer management
- `FeatureEngineer` - Feature computation
- `MicrostructureProcessor` - Order-book tensor construction
- `RelationalFeaturesComputer` - Cross-asset analysis
- `DataEngine` - Orchestrator

**Output:** `MarketFeaturePacket` published to `market.features` topic

### Tier 02: Hybrid Prediction Engine

**Responsibilities:**
- Receive `MarketFeaturePacket` from Tier 01
- Run four specialized experts in parallel:
  - **Microstructure Expert**: CNN analyzing order-book imbalance
  - **Macro-Technical Expert**: Boosted trees on momentum/volatility
  - **Sentiment Expert**: Event/news impact analysis
  - **Relational Expert**: Cross-asset regime transmission
- Perform temporal fusion to aggregate expert signals
- Classify market regime (TREND, PULLBACK, MEAN_REVERSION, BREAKOUT, NEUTRAL)
- Apply physics-aware validation to constrain outputs
- Refine predictions iteratively until convergence
- Publish `PredictionPacket` with direction, probability, confidence

**Key Classes:**
- `ExpertModel` - Base expert class
- `MicrostructureExpert`, `MacroTechnicalExpert`, `SentimentExpert`, `RelationalExpert`
- `TemporalFusionLayer` - Attention-based signal aggregation
- `RegimeDetector` - Market regime classification
- `PhysicsGuard` - Feasibility validation
- `PredictionEngine` - Orchestrator

**Output:** `PredictionPacket` published to `predictions` topic

### Tier 03: Adaptive Trade Planner

**Responsibilities:**
- Receive `PredictionPacket` from Tier 02
- Check entry thresholds (probability > 0.55, confidence > 0.60)
- Model predicted price path envelope
- Generate regime-specific limit-order ladder:
  - TREND: Breakout continuation with tight spacing
  - PULLBACK: Pullback entry with medium spacing
  - MEAN_REVERSION: Counter-trend entries
  - BREAKOUT: Aggressive spacing for new highs
  - NEUTRAL: No ladder placement
- Scale order volume by prediction confidence
- Create `TradePlanPacket` with ordered list of prices/volumes
- Publish trade plan for Execution Engine

**Key Classes:**
- `PathModeler` - Predicted trajectory modeling
- `LadderGenerator` - Order ladder construction
- `TradePlanner` - Orchestrator

**Output:** `TradePlanPacket` published to `trade.plans` topic

### Tier 04: MT5 Execution Engine (MQL5 EA)

**Responsibilities:**
- Subscribe to `TradePlanPacket` updates
- For each plan:
  - Cancel orders from old prediction ID
  - Place all new limit orders exactly as specified
  - Tag each order with prediction ID and ladder index
- Tick-by-tick:
  - Detect filled orders
  - Create position tracking
  - Request replacement orders from Trade Planner
  - Keep ladder moving forward with price
- Track position entry, volume, profit, peak profit
- Reconcile positions with broker
- Apply news lockout (suspend trading during events)
- Publish `ExecutionStatePacket` with current state

**Key Functions:**
- `SynchronizeWithTradePlan()` - Sync orders with new plan
- `PlaceLadderOrder()` - Place single order with retries
- `ManageLadderProgression()` - Handle fills and ladder advance
- `UpdatePositionPNL()` - Real-time profit tracking
- `PublishExecutionState()` - Report state via ZeroMQ

**Output:** `ExecutionStatePacket` published to `execution.state` topic

### Tier 05: Ratchet Exit Manager

**Responsibilities:**
- Receive `ExecutionStatePacket` with open positions
- Receive `PredictionPacket` updates
- For each open position:
  - Track peak profit since entry
  - Calculate adaptive ratchet threshold:
    - HIGH_CONFIDENCE_TREND: 5% from peak
    - MODERATE_CONFIDENCE: 3% from peak
    - LOW_CONFIDENCE: 1.5% from peak
  - Check prediction alignment (direction, regime, confidence)
  - If profit retraces below threshold → request exit
  - If prediction misaligns → request exit
  - Check portfolio safety (daily loss limit, consecutive losses)
- Publish `ExitStatePacket` signaling closure
- Coordinate with Execution Engine to close positions

**Key Classes:**
- `RatchetCalculator` - Threshold computation
- `RatchetExitManager` - Orchestrator

**Output:** `ExitStatePacket` published to `exit.state` topic

## Messaging Contract

All inter-tier communication uses standardized JSON packets.

### MarketFeaturePacket
```json
{
  "timestamp": "ISO8601",
  "symbol": "EURUSD",
  "tick": {"bid": 1.0850, "ask": 1.0852, "last": 1.0851, "volume": 1000},
  "candles": {
    "time": "ISO8601",
    "open": 1.0840, "high": 1.0860, "low": 1.0835, "close": 1.0851,
    "volume": 100000
  },
  "features": {
    "spread": 0.0002, "spread_pips": 2.0, "atr": 12.5,
    "realized_volatility": 0.018, "momentum_1m": 10.0,
    "bid_ask_imbalance": 0.32
  },
  "microstructure": {
    "tensor": [[...], [...]], "imbalance": 0.32,
    "profile": {"bid_total_volume": 1000, ...}
  },
  "relational": {
    "correlation_gbpusd": 0.82, "spread_eurcad": 120.0
  },
  "event_flags": {"news": false, "economic_event": false}
}
```

### PredictionPacket
```json
{
  "prediction_id": "pred_abc123_1709382600",
  "timestamp": "ISO8601",
  "symbol": "EURUSD",
  "direction": "UP",
  "probability": 0.68,
  "confidence": 0.72,
  "expected_move": 25.5,
  "regime": "TREND",
  "action_bias": "TREND",
  "return_distribution": {
    "p10": -12.75, "p25": -6.375, "p50": 0, "p75": 6.375, "p90": 12.75
  },
  "expert_signals": {
    "expert_0": 0.45, "expert_1": 0.63, "expert_2": 0.12, "expert_3": 0.78
  }
}
```

### TradePlanPacket
```json
{
  "prediction_id": "pred_abc123_1709382600",
  "timestamp": "ISO8601",
  "symbol": "EURUSD",
  "ladder_direction": "BUY",
  "ladder_regime": "TREND",
  "spacing": 10.0,
  "ladder_orders": [
    {"price": 0.0, "volume": 0.10, "order_type": "BUY", "ladder_index": 0},
    {"price": 10.0, "volume": 0.08, "order_type": "BUY", "ladder_index": 1},
    {"price": 20.0, "volume": 0.06, "order_type": "BUY", "ladder_index": 2}
  ],
  "predicted_path": {
    "target": 25.5, "envelope_upper": 38.25, "envelope_lower": 12.75
  },
  "regime_duration_ticks": 100
}
```

### ExecutionStatePacket
```json
{
  "prediction_id": "pred_abc123_1709382600",
  "timestamp": "ISO8601",
  "symbol": "EURUSD",
  "open_orders": [
    {"order_id": 123456, "price": 1.0850, "volume": 0.10, "ladder_index": 0}
  ],
  "filled_orders": [
    {"order_id": 123455, "price": 1.0849, "volume": 0.08, "fill_time": "ISO8601", "ladder_index": 1}
  ],
  "open_positions": [
    {"position_id": "pos_1", "entry_price": 1.0849, "volume": 0.08, "entry_time": "ISO8601"}
  ],
  "pnl": 12.50,
  "peak_pnl": 15.75,
  "closed_trades": [],
  "execution_errors": []
}
```

### ExitStatePacket
```json
{
  "position_id": "pos_1",
  "prediction_id": "pred_abc123_1709382600",
  "timestamp": "ISO8601",
  "symbol": "EURUSD",
  "ladder_index": 1,
  "current_profit": 14.20,
  "peak_profit": 15.75,
  "ratchet_threshold": 15.29,
  "exit_triggered": true,
  "ratchet_reason": "RATCHET_BREACH_3pct",
  "closed_positions": [
    {"position_id": "pos_1", "close_price": 1.0854, "close_time": "ISO8601", "profit": 14.20}
  ]
}
```

## Implementation Notes

### Tier 01 (Data Engine)

- Uses MT5 Python API with polling (MT5 doesn't support true async)
- Maintains rolling buffers to conserve memory
- Detects gaps in tick data and logs anomalies
- Computes features every 1 second (configurable)
- All timestamps in UTC ISO8601 format

### Tier 02 (Prediction Engine)

- Expert outputs are normalized to [-1, 1] signal space
- Temporal fusion uses exponential weighting (recent = higher weight)
- Iterative refinement converges when confidence changes < 1%
- Physics guard constrains moves to ±3σ of volatility
- Predictions are deterministic given identical inputs

### Tier 03 (Trade Planner)

- Ladder spacing adjusted by volatility and confidence
- Volume decreases with each ladder step (pyramid structure)
- No ladder placement if probability < 0.55 or confidence < 0.60
- Supports independent ladder generation per symbol

### Tier 04 (MT5 EA)

- Written in MQL5 for MT5 compatibility
- Uses broker order types: ORDER_TYPE_BUY_LIMIT, ORDER_TYPE_SELL_LIMIT
- Implements magic number (20250302) for order identification
- Has critical safety flags (EnableTradingMode off by default)
- Reconciles state every 100 ticks

### Tier 05 (Exit Manager)

- Ratchet thresholds are static per confidence level
- Checks alignment on every prediction update
- Safety limits are portfolio-wide, not per-position
- Logs all exit decisions for performance analysis

## Configuration System

See `src/config/config.py` for all configurable parameters:

- `SystemConfig.environment`: backtest, paper, live
- `DataEngineConfig`: symbols, timeframes, buffer sizes
- `PredictionEngineConfig`: expert weights, model types
- `TradePlannerConfig`: ladder parameters per regime
- `ExecutionEngineConfig`: order placement, risk limits
- `ExitManagerConfig`: ratchet thresholds, safety limits

Load config from environment variables or JSON file:

```python
from src.config import get_config, SystemConfig

# From environment
config = get_config()

# From file
config = SystemConfig.from_file("config.json")

# Save to file
config.to_json("config.json")
```

## Logging & Monitoring

All components use structlog for structured JSON logging:

```python
import structlog
logger = structlog.get_logger(__name__)

logger.info("order_placed", order_id=123, price=1.0850, volume=0.1)
logger.warning("gap_detected", symbol="EURUSD", gap_seconds=5.2)
logger.error("order_rejection", order_id=123, error_code=10013)
```

Logs written to:
- `logs/hft_bot_trading_system.log` (main log)
- `logs/` (daily rotation)

## Testing Strategy

1. **Unit Tests**: Test individual components in isolation
2. **Integration Tests**: Test tier communication
3. **Backtesting**: Test on historical data without order placement
4. **Paper Trading**: Test with live data but no real orders
5. **Live Trading**: Production deployment with real capital

## Performance Characteristics

- **Data Ingestion**: 1000+ ticks/second per symbol
- **Latency**: <10ms from tick to prediction
- **Memory**: ~100MB per symbol for full history
- **CPU**: Single core sufficient for 1-2 symbols
- **Network**: ZeroMQ ~1ms latency on localhost

## Deployment Checklist

- [ ] Configure trading symbol and timeframe
- [ ] Set min probability and confidence thresholds
- [ ] Configure ladder spacing and max orders
- [ ] Set position limits and risk parameters
- [ ] Enable paper trading mode first
- [ ] Run backtests on historical data
- [ ] Load MT5 EA and verify messaging
- [ ] Monitor logs for 24 hours in paper mode
- [ ] Verify all P&L calculations
- [ ] Enable trading mode only after validation
