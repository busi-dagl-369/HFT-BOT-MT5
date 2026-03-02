"""
Tier 01 - Multi-Modal Market Data Engine

A production-grade real-time market data engine that ingests synchronized
tick, order-book, candle, relational, and event data; computes enriched
features and tensors; and streams unified market feature packets in
real-time for downstream tiers.
"""

from .market_connectors import MarketConnector, MT5Connector
from .stream_ingestion import StreamIngestion
from .candle_aggregator import CandleAggregator
from .feature_engineering import FeatureEngineer
from .microstructure_processor import MicrostructureProcessor
from .relational_features import RelationalFeaturesComputer
from .data_engine import DataEngine

__all__ = [
    "MarketConnector",
    "MT5Connector",
    "StreamIngestion",
    "CandleAggregator",
    "FeatureEngineer",
    "MicrostructureProcessor",
    "RelationalFeaturesComputer",
    "DataEngine",
]
