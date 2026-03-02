"""
Candle aggregation from tick data.
Converts tick stream into 1-minute OHLC candles with real-time updates.
"""

from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
import structlog


logger = structlog.get_logger(__name__)


class CandleAggregator:
    """
    Real-time OHLC candle aggregation from tick data.
    Maintains current candle in progress and publishes complete candles.
    """
    
    def __init__(self, timeframe_minutes: int = 1):
        """
        Initialize candle aggregator.
        
        Args:
            timeframe_minutes: Timeframe for candles (e.g., 1, 5, 15, 60)
        """
        self.timeframe_minutes = timeframe_minutes
        self.candle_callbacks: list = []
        
        # Current candles being built per symbol
        self.current_candles: Dict[str, Dict[str, Any]] = {}
    
    def add_tick(self, symbol: str, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process a tick and update current candle.
        
        Returns:
            Completed candle if a new timeframe started, else None
        """
        tick_time = tick['time']
        price = (tick['bid'] + tick['ask']) / 2  # Use mid-price
        
        # Initialize candle if needed
        if symbol not in self.current_candles:
            candle_time = self._get_candle_start_time(tick_time)
            self.current_candles[symbol] = {
                'symbol': symbol,
                'time': candle_time,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': tick.get('volume', 0),
                'tick_count': 1,
            }
            return None
        
        candle = self.current_candles[symbol]
        candle_start = candle['time']
        candle_end = candle_start + timedelta(minutes=self.timeframe_minutes)
        
        # Check if we need to start a new candle
        if tick_time >= candle_end:
            # Complete the old candle
            completed = candle.copy()
            
            # Start new candle
            new_candle_time = self._get_candle_start_time(tick_time)
            self.current_candles[symbol] = {
                'symbol': symbol,
                'time': new_candle_time,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': tick.get('volume', 0),
                'tick_count': 1,
            }
            
            # Trigger callbacks for completed candle
            for callback in self.candle_callbacks:
                try:
                    callback(completed)
                except Exception as e:
                    logger.error("candle_callback_error", symbol=symbol, error=str(e))
            
            return completed
        
        # Update current candle
        candle['high'] = max(candle['high'], price)
        candle['low'] = min(candle['low'], price)
        candle['close'] = price
        candle['volume'] += tick.get('volume', 0)
        candle['tick_count'] += 1
        
        return None
    
    def _get_candle_start_time(self, tick_time: datetime) -> datetime:
        """
        Get the starting time of the candle that contains this tick.
        """
        # Round down to nearest multiple of timeframe_minutes
        minute_offset = tick_time.minute % self.timeframe_minutes
        candle_start = tick_time.replace(
            minute=tick_time.minute - minute_offset,
            second=0,
            microsecond=0,
        )
        return candle_start
    
    def register_callback(self, callback: Callable):
        """Register callback for completed candles."""
        self.candle_callbacks.append(callback)
    
    def get_current_candle(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get the current in-progress candle."""
        return self.current_candles.get(symbol)
    
    def reset_candle(self, symbol: str):
        """Reset candle for a symbol."""
        if symbol in self.current_candles:
            del self.current_candles[symbol]
            logger.info("candle_reset", symbol=symbol)
