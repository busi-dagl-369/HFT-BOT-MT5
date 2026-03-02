"""
Market connectors for pluggable data source support.
Abstraction layer supporting MT5, FIX, WebSocket, and other sources.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime
import structlog
import MetaTrader5 as mt5
from collections import deque


logger = structlog.get_logger(__name__)


class MarketConnector(ABC):
    """Abstract base for market data connectors."""
    
    @abstractmethod
    async def connect(self):
        """Establish connection to market data source."""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from market data source."""
        pass
    
    @abstractmethod
    async def is_connected(self) -> bool:
        """Check connection status."""
        pass
    
    @abstractmethod
    async def get_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get latest tick for symbol.
        
        Returns:
            {bid, ask, last, volume, time}
        """
        pass
    
    @abstractmethod
    async def get_order_book(self, symbol: str, depth: int = 20) -> Optional[Dict[str, Any]]:
        """
        Get order book snapshot (if available).
        
        Returns:
            {bids: [(price, volume), ...], asks: [(price, volume), ...]}
        """
        pass
    
    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: int = 1,
        count: int = 100,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get historical candles.
        
        Returns:
            List of {time, open, high, low, close, volume}
        """
        pass
    
    @abstractmethod
    async def subscribe_ticks(self, symbol: str, callback):
        """Subscribe to real-time tick updates."""
        pass


class MT5Connector(MarketConnector):
    """MetaTrader 5 market data connector."""
    
    def __init__(
        self,
        account: int,
        password: str,
        server: str,
        timeout: int = 60000,
    ):
        """
        Initialize MT5 connector.
        
        Args:
            account: MT5 account number
            password: MT5 password
            server: MT5 server name
            timeout: Connection timeout in milliseconds
        """
        self.account = account
        self.password = password
        self.server = server
        self.timeout = timeout
        self.connected = False
        self.tick_subscriptions: Dict[str, Any] = {}
    
    async def connect(self):
        """Connect to MT5 terminal."""
        try:
            if not mt5.initialize(
                account=self.account,
                password=self.password,
                server=self.server,
                timeout=self.timeout,
            ):
                error = mt5.last_error()
                logger.error("mt5_connection_failed", error=error)
                raise ConnectionError(f"MT5 connection failed: {error}")
            
            self.connected = True
            logger.info("mt5_connected", account=self.account, server=self.server)
        except Exception as e:
            logger.error("mt5_connect_exception", error=str(e))
            raise
    
    async def disconnect(self):
        """Disconnect from MT5 terminal."""
        try:
            if self.connected:
                mt5.shutdown()
                self.connected = False
                logger.info("mt5_disconnected")
        except Exception as e:
            logger.error("mt5_disconnect_exception", error=str(e))
    
    async def is_connected(self) -> bool:
        """Check MT5 connection status."""
        try:
            return self.connected and mt5.terminal_info() is not None
        except:
            return False
    
    async def get_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest tick from MT5."""
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                logger.warning("mt5_tick_fetch_failed", symbol=symbol)
                return None
            
            return {
                "bid": tick.bid,
                "ask": tick.ask,
                "last": tick.last,
                "time": datetime.fromtimestamp(tick.time),
                "volume": tick.volume if hasattr(tick, 'volume') else 0,
            }
        except Exception as e:
            logger.error("mt5_get_tick_error", symbol=symbol, error=str(e))
            return None
    
    async def get_order_book(self, symbol: str, depth: int = 20) -> Optional[Dict[str, Any]]:
        """
        Get order book snapshot from MT5.
        Note: MT5 doesn't provide true L2 order book, so we return bid/ask spread.
        """
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            
            # MT5 doesn't provide L2 depth, so return simple structure
            return {
                "bids": [(tick.bid, 0)],
                "asks": [(tick.ask, 0)],
                "time": datetime.fromtimestamp(tick.time),
            }
        except Exception as e:
            logger.error("mt5_get_order_book_error", symbol=symbol, error=str(e))
            return None
    
    async def get_candles(
        self,
        symbol: str,
        timeframe: int = 1,
        count: int = 100,
    ) -> Optional[List[Dict[str, Any]]]:
        """Get historical candles from MT5."""
        try:
            # Map timeframe to MT5 constants
            tf_map = {
                1: mt5.TIMEFRAME_M1,
                5: mt5.TIMEFRAME_M5,
                15: mt5.TIMEFRAME_M15,
                30: mt5.TIMEFRAME_M30,
                60: mt5.TIMEFRAME_H1,
                240: mt5.TIMEFRAME_H4,
                1440: mt5.TIMEFRAME_D1,
            }
            
            tf = tf_map.get(timeframe, mt5.TIMEFRAME_M1)
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
            
            if rates is None or len(rates) == 0:
                logger.warning("mt5_candles_fetch_failed", symbol=symbol, timeframe=timeframe)
                return None
            
            candles = []
            for rate in rates:
                candles.append({
                    "time": datetime.fromtimestamp(rate[0]),
                    "open": rate[1],
                    "high": rate[2],
                    "low": rate[3],
                    "close": rate[4],
                    "volume": rate[5],
                })
            
            return candles
        except Exception as e:
            logger.error(
                "mt5_get_candles_error",
                symbol=symbol,
                timeframe=timeframe,
                error=str(e),
            )
            return None
    
    async def subscribe_ticks(self, symbol: str, callback):
        """
        Subscribe to tick updates.
        Note: MT5 uses polling, so we implement periodic checks.
        """
        if symbol in self.tick_subscriptions:
            logger.warning("mt5_already_subscribed", symbol=symbol)
            return
        
        self.tick_subscriptions[symbol] = callback
        logger.info("mt5_subscribed_to_ticks", symbol=symbol)
        
        # Start background polling task
        asyncio.create_task(self._tick_polling_loop(symbol, callback))
    
    async def _tick_polling_loop(self, symbol: str, callback):
        """Background task for MT5 tick polling."""
        last_tick = None
        poll_interval = 0.1  # 100ms polling
        
        while symbol in self.tick_subscriptions:
            try:
                tick = await self.get_tick(symbol)
                
                # Only trigger callback on price change
                if tick and (last_tick is None or
                    tick['bid'] != last_tick.get('bid') or
                    tick['ask'] != last_tick.get('ask')):
                    await callback(tick)
                    last_tick = tick
                
                await asyncio.sleep(poll_interval)
            except Exception as e:
                logger.error("mt5_polling_error", symbol=symbol, error=str(e))
                await asyncio.sleep(1)
    
    async def unsubscribe_ticks(self, symbol: str):
        """Unsubscribe from tick updates."""
        if symbol in self.tick_subscriptions:
            del self.tick_subscriptions[symbol]
            logger.info("mt5_unsubscribed_from_ticks", symbol=symbol)
