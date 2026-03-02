"""
Centralized configuration management for the trading system.
Supports environment-based configuration with defaults.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any
import json
from pathlib import Path
import structlog


logger = structlog.get_logger(__name__)


@dataclass
class MT5Config:
    """MetaTrader5 connection configuration."""
    account: int = 0
    password: str = ""
    server: str = ""
    timeout: int = 60000  # milliseconds


@dataclass
class MessagingConfig:
    """Messaging broker configuration."""
    backend: str = "zeromq"  # "zeromq" or "redis"
    zmq_host: str = "127.0.0.1"
    zmq_port: int = 5555
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    
    # Tier-specific topic mappings
    market_features_topic: str = "market.features"
    predictions_topic: str = "predictions"
    trade_plans_topic: str = "trade.plans"
    execution_states_topic: str = "execution.state"
    exit_states_topic: str = "exit.state"


@dataclass
class DataEngineConfig:
    """Tier 01 Data Engine configuration."""
    symbols: list = field(default_factory=lambda: ["EURUSD"])
    timeframe: int = 1  # Minutes
    tick_buffer_size: int = 10000
    candle_buffer_size: int = 1440  # 1 day of 1-min candles
    feature_update_interval: float = 1.0  # seconds
    microstructure_depth: int = 20  # Order book depth levels
    correlation_lookback: int = 100  # Ticks for cross-asset correlation
    atr_period: int = 14
    volatility_period: int = 20
    reconnect_max_retries: int = 5
    reconnect_delay: float = 2.0


@dataclass
class PredictionEngineConfig:
    """Tier 02 Prediction Engine configuration."""
    model_type: str = "hybrid_ensemble"  # "hybrid_ensemble", "lstm", "transformer"
    inference_frequency: float = 1.0  # seconds
    
    # Expert weights
    microstructure_weight: float = 0.25
    macro_technical_weight: float = 0.30
    sentiment_weight: float = 0.15
    relational_weight: float = 0.30
    
    # Fusion and iterative refinement
    temporal_fusion_type: str = "attention"  # "attention", "lstm", "gru"
    max_refinement_iterations: int = 3
    refinement_convergence_threshold: float = 0.01
    
    # Confidence and probability calibration
    min_confidence_threshold: float = 0.55
    confidence_percentile_adjustment: bool = True
    
    # Physics-aware validation
    enable_physics_guard: bool = True
    max_feasible_move_std: float = 3.0  # StdDev of volatility
    
    # Regime detection
    regime_classes: list = field(default_factory=lambda: [
        "TREND", "PULLBACK", "MEAN_REVERSION", "BREAKOUT", "NEUTRAL"
    ])
    
    # Model paths
    model_checkpoint_dir: str = "./checkpoints/prediction_engine"


@dataclass
class TradePlannerConfig:
    """Tier 03 Trade Planner configuration."""
    # Entry thresholds
    min_probability: float = 0.55
    min_confidence: float = 0.60
    
    # Ladder configuration
    ladder_max_orders: int = 20
    ladder_base_spacing: float = 10.0  # pips
    ladder_spacing_multiplier_volatility: float = 1.5  # Adjust spacing by volatility
    
    # Regime-specific behavior
    regime_configs: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        "TREND": {
            "ladder_direction_align": True,
            "spacing_adjustment": 1.0,
            "max_forward_distance": 100.0,
        },
        "PULLBACK": {
            "ladder_direction_align": True,
            "spacing_adjustment": 1.2,
            "max_forward_distance": 50.0,
        },
        "MEAN_REVERSION": {
            "ladder_direction_align": False,
            "spacing_adjustment": 0.8,
            "max_forward_distance": 25.0,
        },
        "BREAKOUT": {
            "ladder_direction_align": True,
            "spacing_adjustment": 1.3,
            "max_forward_distance": 150.0,
        },
    })
    
    # Position sizing
    base_contract_size: float = 0.1  # Lots
    confidence_volume_scaling: bool = True
    
    # Order lifecycle
    order_cancellation_on_prediction_flip: bool = True
    order_cancellation_on_regime_change: bool = True


@dataclass
class ExecutionEngineConfig:
    """Tier 04 (MT5 EA) configuration."""
    # General EA behavior
    enable_trading: bool = False  # Safety flag
    enable_paper_trading: bool = True
    
    # Order placement
    slippage_tolerance_pips: float = 2.0
    max_retries_on_rejection: int = 3
    retry_delay_ms: int = 100
    
    # Synchronization
    strict_plan_sync: bool = True
    position_reconciliation_interval_ticks: int = 100
    
    # News lockout
    enable_news_lockout: bool = True
    news_lockout_minutes_before: int = 15
    news_lockout_minutes_after: int = 5
    
    # Risk limits
    max_open_positions: int = 5
    max_total_volume: float = 1.0  # Lots
    max_spread_pips: float = 3.0  # Don't trade if spread > this


@dataclass
class ExitManagerConfig:
    """Tier 05 Ratchet Exit Manager configuration."""
    # Ratchet threshold configuration
    ratchet_configs: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        "HIGH_CONFIDENCE_TREND": {
            "retracement_percent": 5.0,
            "min_hold_ticks": 50,
        },
        "MODERATE_CONFIDENCE": {
            "retracement_percent": 3.0,
            "min_hold_ticks": 30,
        },
        "LOW_CONFIDENCE": {
            "retracement_percent": 1.5,
            "min_hold_ticks": 15,
        },
    })
    
    # Smoothing
    profit_smoothing_window_ticks: int = 5
    
    # Portfolio-level safety
    daily_loss_limit_pips: float = 1000.0
    max_consecutive_losses: int = 5
    max_volatility_spike_factor: float = 2.5  # vs historical vol
    
    # Exit timing
    early_ladder_fill_hold_ticks: int = 50
    late_ladder_fill_hold_ticks: int = 20


@dataclass
class SystemConfig:
    """Top-level system configuration."""
    environment: str = "backtest"  # "backtest", "paper", "live"
    
    # Component configurations
    mt5: MT5Config = field(default_factory=MT5Config)
    messaging: MessagingConfig = field(default_factory=MessagingConfig)
    data_engine: DataEngineConfig = field(default_factory=DataEngineConfig)
    prediction_engine: PredictionEngineConfig = field(default_factory=PredictionEngineConfig)
    trade_planner: TradePlannerConfig = field(default_factory=TradePlannerConfig)
    execution_engine: ExecutionEngineConfig = field(default_factory=ExecutionEngineConfig)
    exit_manager: ExitManagerConfig = field(default_factory=ExitManagerConfig)
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "console"
    structured_logs_dir: str = "./logs"
    
    # System-wide
    clock_tick_interval_ms: int = 10  # System clock tick
    
    @classmethod
    def from_env(cls) -> "SystemConfig":
        """Load configuration from environment variables."""
        cfg = cls()
        
        # Environment
        cfg.environment = os.getenv("TRADING_ENV", "backtest")
        cfg.log_level = os.getenv("LOG_LEVEL", "INFO")
        
        # MT5
        if mt5_account := os.getenv("MT5_ACCOUNT"):
            cfg.mt5.account = int(mt5_account)
        if mt5_password := os.getenv("MT5_PASSWORD"):
            cfg.mt5.password = mt5_password
        if mt5_server := os.getenv("MT5_SERVER"):
            cfg.mt5.server = mt5_server
        
        # Messaging
        cfg.messaging.backend = os.getenv("MESSAGING_BACKEND", "zeromq")
        cfg.messaging.zmq_host = os.getenv("ZMQ_HOST", "127.0.0.1")
        if zmq_port := os.getenv("ZMQ_PORT"):
            cfg.messaging.zmq_port = int(zmq_port)
        
        # Data Engine
        if symbols := os.getenv("TRADING_SYMBOLS"):
            cfg.data_engine.symbols = symbols.split(",")
        
        logger.info("configuration_loaded", environment=cfg.environment)
        return cfg
    
    @classmethod
    def from_file(cls, path: str) -> "SystemConfig":
        """Load configuration from JSON file."""
        with open(path, "r") as f:
            data = json.load(f)
        
        # Reconstruct nested configs
        cfg = cls()
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        
        logger.info("configuration_loaded_from_file", path=path)
        return cfg
    
    def to_json(self, path: str):
        """Save configuration to JSON file."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        data = {
            "environment": self.environment,
            "log_level": self.log_level,
            "mt5": self.mt5.__dict__,
            "messaging": self.messaging.__dict__,
            "data_engine": self.data_engine.__dict__,
            "prediction_engine": self.prediction_engine.__dict__,
            "trade_planner": self.trade_planner.__dict__,
            "execution_engine": self.execution_engine.__dict__,
            "exit_manager": self.exit_manager.__dict__,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("configuration_saved", path=path)


# Global config instance
_config: SystemConfig = None


def get_config() -> SystemConfig:
    """Get the current system configuration."""
    global _config
    if _config is None:
        _config = SystemConfig.from_env()
    return _config


def set_config(config: SystemConfig):
    """Set the system configuration."""
    global _config
    _config = config
