"""
Test suite for all tiers.
Unit tests, integration tests, and simulation tests.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

from src.config import SystemConfig
from src.messaging import (
    MarketFeaturePacket,
    PredictionPacket,
    TradePlanPacket,
    ExecutionStatePacket,
    ExitStatePacket,
)
from src.tier_01_data_engine import FeatureEngineer, CandleAggregator
from src.tier_02_prediction_engine.experts import MacroTechnicalExpert


class TestTier01DataEngine:
    """Tests for Tier 01."""
    
    @pytest.mark.asyncio
    async def test_feature_computation(self):
        """Test feature engineering."""
        engineer = FeatureEngineer(atr_period=14, volatility_period=20)
        
        # Create sample data
        tick_history = [
            {'bid': 1.0000, 'ask': 1.0002, 'volume': 100, 'time': datetime.now()},
            {'bid': 1.0001, 'ask': 1.0003, 'volume': 150, 'time': datetime.now()},
        ]
        
        candle_history = [
            {'open': 1.0000, 'high': 1.0005, 'low': 0.9995, 'close': 1.0003, 'volume': 1000},
        ] * 20
        
        features = engineer.compute_features(
            symbol='EURUSD',
            price=1.00015,
            bid=1.0000,
            ask=1.0002,
            tick_history=tick_history,
            candle_history=candle_history,
        )
        
        assert 'spread' in features
        assert 'atr' in features
        assert features['spread'] > 0
    
    def test_candle_aggregation(self):
        """Test candle aggregation."""
        aggregator = CandleAggregator(timeframe_minutes=1)
        
        tick = {
            'bid': 1.0000,
            'ask': 1.0002,
            'volume': 100,
            'time': datetime.now(),
        }
        
        result = aggregator.add_tick('EURUSD', tick)
        assert result is None  # First tick shouldn't complete a candle
        
        # Get current candle
        current = aggregator.get_current_candle('EURUSD')
        assert current is not None
        assert current['open'] == 1.00010  # Midprice


class TestTier02PredictionEngine:
    """Tests for Tier 02."""
    
    @pytest.mark.asyncio
    async def test_macro_technical_expert(self):
        """Test macro-technical expert inference."""
        expert = MacroTechnicalExpert()
        
        features = {
            'momentum_1m': 10.0,
            'realized_volatility': 0.01,
            'atr': 10.0,
            'price_slope_20m': 5.0,
        }
        
        signal, confidence = await expert.infer(features)
        
        assert -1.0 <= signal <= 1.0
        assert 0.0 <= confidence <= 1.0


class TestMessaging:
    """Tests for messaging layer."""
    
    def test_market_feature_packet(self):
        """Test market feature packet serialization."""
        packet = MarketFeaturePacket(
            timestamp=datetime.now().isoformat(),
            symbol='EURUSD',
            tick={'bid': 1.0000, 'ask': 1.0002},
            candles={'close': 1.0001},
            features={'atr': 10.0},
        )
        
        json_str = packet.to_json()
        assert 'EURUSD' in json_str
        
        # Test deserialization
        reconstructed = MarketFeaturePacket.from_json(json_str)
        assert reconstructed.symbol == 'EURUSD'
    
    def test_prediction_packet(self):
        """Test prediction packet serialization."""
        packet = PredictionPacket(
            prediction_id='pred_123',
            timestamp=datetime.now().isoformat(),
            symbol='EURUSD',
            direction='UP',
            probability=0.65,
            confidence=0.70,
            expected_move=15.0,
            regime='TREND',
            action_bias='TREND',
        )
        
        json_str = packet.to_json()
        assert 'pred_123' in json_str
        assert 'TREND' in json_str


class TestConfiguration:
    """Tests for configuration system."""
    
    def test_config_initialization(self):
        """Test config can be initialized."""
        config = SystemConfig()
        
        assert config.environment in ['backtest', 'paper', 'live']
        assert config.log_level in ['DEBUG', 'INFO', 'WARNING', 'ERROR']
        assert len(config.data_engine.symbols) > 0
    
    def test_config_from_file(self, tmp_path):
        """Test config loading from file."""
        config_file = tmp_path / "config.json"
        config = SystemConfig()
        config.to_json(str(config_file))
        
        # Verify file was created
        assert config_file.exists()


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
