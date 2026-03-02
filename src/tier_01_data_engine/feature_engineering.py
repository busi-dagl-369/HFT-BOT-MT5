"""
Feature engineering for market data.
Computes derived market features: volatility, momentum, spread, liquidity, etc.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import numpy as np
import structlog


logger = structlog.get_logger(__name__)


class FeatureEngineer:
    """
    Real-time feature engineering from market data.
    Computes volatility, momentum, spread, volume flow, and other indicators.
    """
    
    def __init__(self, atr_period: int = 14, volatility_period: int = 20):
        """
        Initialize feature engineer.
        
        Args:
            atr_period: Period for ATR calculation
            volatility_period: Period for volatility calculation
        """
        self.atr_period = atr_period
        self.volatility_period = volatility_period
    
    def compute_features(
        self,
        symbol: str,
        price: float,
        bid: float,
        ask: float,
        tick_history: List[Dict[str, Any]],
        candle_history: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """
        Compute all features for a symbol at the current moment.
        
        Args:
            symbol: Symbol
            price: Current price (mid)
            bid: Current bid
            ask: Current ask
            tick_history: List of recent ticks
            candle_history: List of recent candles
            
        Returns:
            Dictionary of computed features
        """
        features = {}
        
        try:
            # Spread
            spread = ask - bid
            spread_pips = spread * 10000  # Convert to pips (for most pairs)
            features['spread'] = spread
            features['spread_pips'] = spread_pips
            spread_percent = (spread / price) * 100
            features['spread_percent'] = spread_percent
            
            # Volume and flow features
            if len(tick_history) > 0:
                volumes = [t.get('volume', 0) for t in tick_history]
                features['volume_mean'] = np.mean(volumes) if volumes else 0
                features['volume_max'] = np.max(volumes) if volumes else 0
                features['volume_total'] = np.sum(volumes) if volumes else 0
            
            # Volatility metrics
            if len(candle_history) >= self.volatility_period:
                closes = np.array([c['close'] for c in candle_history[-self.volatility_period:]])
                returns = np.diff(np.log(closes))
                realized_vol = np.std(returns)
                features['realized_volatility'] = realized_vol
                features['volatility_annualized'] = realized_vol * np.sqrt(252 * 1440)  # Annualized
            else:
                features['realized_volatility'] = 0.0
                features['volatility_annualized'] = 0.0
            
            # ATR (Average True Range)
            if len(candle_history) >= self.atr_period:
                atr_value = self._compute_atr(candle_history[-self.atr_period:])
                features['atr'] = atr_value
                features['atr_percent'] = (atr_value / price) * 100
            else:
                features['atr'] = 0.0
                features['atr_percent'] = 0.0
            
            # Momentum features
            if len(candle_history) >= 2:
                recent_close = candle_history[-1]['close']
                prev_close = candle_history[-2]['close']
                momentum = recent_close - prev_close
                features['momentum_1m'] = momentum
                features['momentum_return_1m'] = (momentum / prev_close) * 100  # Percent
            
            # Trend slope (simple linear regression)
            if len(candle_history) >= 5:
                closes = np.array([c['close'] for c in candle_history[-20:]])
                x = np.arange(len(closes))
                slope = np.polyfit(x, closes, 1)[0]
                features['price_slope_20m'] = slope
            else:
                features['price_slope_20m'] = 0.0
            
            # Bid-ask imbalance
            if len(tick_history) > 0:
                imbalance = self._compute_imbalance(tick_history[-100:])
                features['bid_ask_imbalance'] = imbalance
            else:
                features['bid_ask_imbalance'] = 0.0
            
            logger.debug("features_computed", symbol=symbol, count=len(features))
            return features
        
        except Exception as e:
            logger.error("feature_computation_error", symbol=symbol, error=str(e))
            return {}
    
    def _compute_atr(self, candles: List[Dict[str, float]]) -> float:
        """Compute Average True Range."""
        tr_values = []
        prev_close = None
        
        for candle in candles:
            high = candle['high']
            low = candle['low']
            close = candle['close']
            
            tr = high - low
            
            if prev_close is not None:
                tr = max(tr, abs(high - prev_close), abs(low - prev_close))
            
            tr_values.append(tr)
            prev_close = close
        
        return np.mean(tr_values) if tr_values else 0.0
    
    def _compute_imbalance(self, ticks: List[Dict[str, Any]]) -> float:
        """
        Compute bid-ask imbalance (order flow pressure).
        Positive = more buying, Negative = more selling
        """
        if len(ticks) < 2:
            return 0.0
        
        buy_volume = 0
        sell_volume = 0
        
        for i, tick in enumerate(ticks):
            price = (tick.get('bid', 0) + tick.get('ask', 0)) / 2
            volume = tick.get('volume', 0)
            
            if i > 0:
                prev_price = (ticks[i-1].get('bid', 0) + ticks[i-1].get('ask', 0)) / 2
                
                if price > prev_price:
                    buy_volume += volume
                elif price < prev_price:
                    sell_volume += volume
        
        total_volume = buy_volume + sell_volume
        
        if total_volume == 0:
            return 0.0
        
        imbalance = (buy_volume - sell_volume) / (total_volume + 1e-8)
        return imbalance
