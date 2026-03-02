"""
Multi-stream market data ingestion with synchronized buffering.
Handles concurrent tick, order-book, candle, and event streams.
"""

import asyncio
from typing import Dict, List, Any, Optional, Callable
from collections import deque
from datetime import datetime
import structlog


logger = structlog.get_logger(__name__)


class StreamIngestion:
    """
    Multi-stream ingestion buffer with timestamp alignment.
    Maintains rolling windows of synchronized market data.
    """
    
    def __init__(
        self,
        symbols: List[str],
        tick_buffer_size: int = 10000,
        candle_buffer_size: int = 1440,
        gap_detection_threshold: float = 5.0,  # seconds
    ):
        """
        Initialize stream ingestion.
        
        Args:
            symbols: List of symbols to ingest
            tick_buffer_size: Rolling buffer size for ticks
            candle_buffer_size: Rolling buffer size for candles
            gap_detection_threshold: Gap detection threshold in seconds
        """
        self.symbols = symbols
        self.tick_buffer_size = tick_buffer_size
        self.candle_buffer_size = candle_buffer_size
        self.gap_detection_threshold = gap_detection_threshold
        
        # Rolling buffers for each stream
        self.tick_buffer: Dict[str, deque] = {sym: deque(maxlen=tick_buffer_size) for sym in symbols}
        self.candle_buffer: Dict[str, deque] = {sym: deque(maxlen=candle_buffer_size) for sym in symbols}
        self.event_buffer: Dict[str, deque] = {sym: deque(maxlen=1000) for sym in symbols}
        
        # Gap detection state
        self.last_tick_time: Dict[str, datetime] = {sym: None for sym in symbols}
        self.gap_detected: Dict[str, bool] = {sym: False for sym in symbols}
        self.missed_ticks: Dict[str, int] = {sym: 0 for sym in symbols}
        
        # Callbacks for new data
        self.tick_callbacks: List[Callable] = []
        self.candle_callbacks: List[Callable] = []
        self.event_callbacks: List[Callable] = []
    
    async def ingest_tick(self, symbol: str, tick: Dict[str, Any]) -> bool:
        """
        Ingest a tick into the buffer.
        
        Args:
            symbol: Symbol
            tick: Tick data {bid, ask, last, volume, time}
            
        Returns:
            True if tick was accepted, False if gap detected
        """
        try:
            # Gap detection
            if self.last_tick_time[symbol] is not None:
                time_diff = (tick['time'] - self.last_tick_time[symbol]).total_seconds()
                
                if time_diff > self.gap_detection_threshold:
                    self.gap_detected[symbol] = True
                    self.missed_ticks[symbol] += 1
                    logger.warning(
                        "tick_gap_detected",
                        symbol=symbol,
                        gap_seconds=time_diff,
                    )
                    return False
            
            # Add to buffer
            self.tick_buffer[symbol].append(tick)
            self.last_tick_time[symbol] = tick['time']
            
            # Clear gap flag if we receive consecutive ticks
            if self.gap_detected[symbol] and self.last_tick_time[symbol] is not None:
                self.gap_detected[symbol] = False
            
            # Trigger callbacks
            for callback in self.tick_callbacks:
                try:
                    await callback(symbol, tick)
                except Exception as e:
                    logger.error("tick_callback_error", symbol=symbol, error=str(e))
            
            return True
        except Exception as e:
            logger.error("ingest_tick_error", symbol=symbol, error=str(e))
            return False
    
    async def ingest_candle(self, symbol: str, candle: Dict[str, Any]) -> bool:
        """
        Ingest a candle into the buffer.
        
        Args:
            symbol: Symbol
            candle: Candle data {time, open, high, low, close, volume}
            
        Returns:
            True if candle was accepted
        """
        try:
            self.candle_buffer[symbol].append(candle)
            
            # Trigger callbacks
            for callback in self.candle_callbacks:
                try:
                    await callback(symbol, candle)
                except Exception as e:
                    logger.error("candle_callback_error", symbol=symbol, error=str(e))
            
            return True
        except Exception as e:
            logger.error("ingest_candle_error", symbol=symbol, error=str(e))
            return False
    
    async def ingest_event(self, symbol: str, event: Dict[str, Any]) -> bool:
        """
        Ingest an event (news, economic indicator, etc).
        
        Args:
            symbol: Symbol
            event: Event data {type, time, description, severity}
            
        Returns:
            True if event was accepted
        """
        try:
            self.event_buffer[symbol].append(event)
            
            # Trigger callbacks
            for callback in self.event_callbacks:
                try:
                    await callback(symbol, event)
                except Exception as e:
                    logger.error("event_callback_error", symbol=symbol, error=str(e))
            
            return True
        except Exception as e:
            logger.error("ingest_event_error", symbol=symbol, error=str(e))
            return False
    
    def register_tick_callback(self, callback: Callable):
        """Register callback for tick ingestion."""
        self.tick_callbacks.append(callback)
    
    def register_candle_callback(self, callback: Callable):
        """Register callback for candle ingestion."""
        self.candle_callbacks.append(callback)
    
    def register_event_callback(self, callback: Callable):
        """Register callback for event ingestion."""
        self.event_callbacks.append(callback)
    
    def get_latest_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get the latest tick."""
        if len(self.tick_buffer[symbol]) > 0:
            return self.tick_buffer[symbol][-1]
        return None
    
    def get_latest_candle(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get the latest candle."""
        if len(self.candle_buffer[symbol]) > 0:
            return self.candle_buffer[symbol][-1]
        return None
    
    def get_tick_history(self, symbol: str, count: int = 100) -> List[Dict[str, Any]]:
        """Get historical ticks."""
        return list(self.tick_buffer[symbol])[-count:]
    
    def get_candle_history(self, symbol: str, count: int = 100) -> List[Dict[str, Any]]:
        """Get historical candles."""
        return list(self.candle_buffer[symbol])[-count:]
    
    def get_event_history(self, symbol: str, count: int = 100) -> List[Dict[str, Any]]:
        """Get historical events."""
        return list(self.event_buffer[symbol])[-count:]
    
    def get_symbol_status(self, symbol: str) -> Dict[str, Any]:
        """Get ingestion status for a symbol."""
        return {
            "symbol": symbol,
            "ticks_buffered": len(self.tick_buffer[symbol]),
            "candles_buffered": len(self.candle_buffer[symbol]),
            "events_buffered": len(self.event_buffer[symbol]),
            "gap_detected": self.gap_detected[symbol],
            "missed_ticks": self.missed_ticks[symbol],
            "last_tick_time": self.last_tick_time[symbol],
        }
    
    def clear_buffers(self, symbol: Optional[str] = None):
        """Clear buffers for symbol(s)."""
        if symbol:
            symbols = [symbol]
        else:
            symbols = self.symbols
        
        for sym in symbols:
            self.tick_buffer[sym].clear()
            self.candle_buffer[sym].clear()
            self.event_buffer[sym].clear()
            self.missed_ticks[sym] = 0
            logger.info("buffers_cleared", symbol=sym)
