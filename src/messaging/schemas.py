"""
Structured messaging schemas for inter-tier communication.
All packets are serialized as JSON per the communication contract.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime
import json


@dataclass
class MarketFeaturePacket:
    """
    Market feature packet from Data Engine to Prediction Engine.
    
    Contains synchronized multi-modal market data:
    - Tick state (bid, ask, last)
    - OHLC candle data
    - Computed features (volatility, momentum, spread)
    - Microstructure tensors
    - Relational features (cross-asset)
    - Event flags (news, economic events)
    """
    timestamp: str  # ISO8601
    symbol: str
    tick: Dict[str, float]  # {bid, ask, last, volume}
    candles: Dict[str, Any]  # {open, high, low, close, volume, time}
    features: Dict[str, float]  # {atr, volatility, momentum, spread, imbalance, etc}
    microstructure: Optional[Dict[str, Any]] = None  # Order book tensor
    relational: Optional[Dict[str, float]] = None  # Cross-asset correlations
    event_flags: Dict[str, Any] = field(default_factory=dict)  # News, economic events
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> "MarketFeaturePacket":
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class PredictionPacket:
    """
    Prediction packet from Prediction Engine to Trade Planner.
    
    Contains probabilistic directional forecast and market regime inference.
    """
    prediction_id: str  # Unique prediction cycle ID
    timestamp: str  # ISO8601
    symbol: str
    direction: str  # "UP", "DOWN", "FLAT"
    probability: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0 (prediction quality)
    expected_move: float  # Expected magnitude in pips
    regime: str  # "TREND", "PULLBACK", "MEAN_REVERSION", "BREAKOUT", "NEUTRAL"
    action_bias: str  # "TREND", "MEAN_REVERSION", "NEUTRAL"
    return_distribution: Optional[Dict[str, float]] = None  # {percentile: value}
    expert_signals: Optional[Dict[str, float]] = None  # Individual expert confidences
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> "PredictionPacket":
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class LadderOrder:
    """Single order in a ladder."""
    price: float
    volume: float
    order_type: str  # "BUY" or "SELL"
    ladder_index: int  # Position in ladder sequence


@dataclass
class TradePlanPacket:
    """
    Trade plan packet from Trade Planner to Execution Engine.
    
    Contains adaptive limit-order ladder for execution.
    """
    prediction_id: str  # Reference to source prediction
    timestamp: str  # ISO8601
    symbol: str
    ladder_direction: str  # "BUY" or "SELL"
    ladder_regime: str  # Regime type
    spacing: float  # Spacing between ladder orders
    ladder_orders: List[Dict[str, Any]]  # List of {price, volume, order_type, ladder_index}
    predicted_path: Optional[Dict[str, float]] = None  # Target prices, envelope bounds
    regime_duration_ticks: int = 0  # Expected regime persistence
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> "TradePlanPacket":
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class ExecutionStatePacket:
    """
    Execution state packet from Execution Engine to Python brain.
    
    Tracks current trading state, filled orders, positions, and P&L.
    """
    prediction_id: str
    timestamp: str  # ISO8601
    symbol: str
    open_orders: List[Dict[str, Any]]  # {order_id, price, volume, ladder_index}
    filled_orders: List[Dict[str, Any]]  # {order_id, price, volume, fill_time, ladder_index}
    open_positions: List[Dict[str, Any]]  # {position_id, entry_price, volume, entry_time}
    pnl: float  # Current unrealized P&L
    peak_pnl: float  # Peak unrealized P&L
    closed_trades: List[Dict[str, Any]] = field(default_factory=list)  # Closed positions
    execution_errors: List[str] = field(default_factory=list)  # Any errors
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> "ExecutionStatePacket":
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class ExitStatePacket:
    """
    Exit state packet from Ratchet Exit Manager to Python brain.
    
    Tracks position profitability, ratchet thresholds, and exit signals.
    """
    position_id: str
    prediction_id: str
    timestamp: str  # ISO8601
    symbol: str
    ladder_index: int
    current_profit: float
    peak_profit: float
    ratchet_threshold: float  # Max allowed drawdown from peak
    exit_triggered: bool
    closed_positions: List[Dict[str, Any]] = field(default_factory=list)
    ratchet_reason: Optional[str] = None  # Reason for exit if triggered
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> "ExitStatePacket":
        data = json.loads(json_str)
        return cls(**data)
