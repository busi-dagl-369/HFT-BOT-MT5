"""
Tier 01 - Multi-Modal Market Data Engine
Orchestrates synchronized ingestion, aggregation, and feature computation.
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import structlog
from uuid import uuid4

from ..config import get_config
from ..messaging import MarketFeaturePacket, MessagingBroker
from .market_connectors import MT5Connector
from .stream_ingestion import StreamIngestion
from .candle_aggregator import CandleAggregator
from .feature_engineering import FeatureEngineer
from .microstructure_processor import MicrostructureProcessor
from .relational_features import RelationalFeaturesComputer


logger = structlog.get_logger(__name__)


class DataEngine:
    """
    Multi-modal market data engine.
    Ingests ticks, candles, order-book, events; computes features; publishes packets.
    """
    
    def __init__(self):
        """Initialize Data Engine."""
        self.config = get_config()
        self.running = False
        
        # Components
        self.connector: Optional[MT5Connector] = None
        self.stream_ingestion: Optional[StreamIngestion] = None
        self.candle_aggregator: Optional[CandleAggregator] = None
        self.feature_engineer: Optional[FeatureEngineer] = None
        self.microstructure_processor: Optional[MicrostructureProcessor] = None
        self.relational_features: Optional[RelationalFeaturesComputer] = None
        self.messaging_broker: Optional[MessagingBroker] = None
        
        # State
        self.symbols = self.config.data_engine.symbols
        self.last_feature_publish_time: Dict[str, datetime] = {sym: None for sym in self.symbols}
        self.feature_update_interval = self.config.data_engine.feature_update_interval
        
        logger.info("data_engine_initialized", symbols=self.symbols)
    
    async def initialize(self):
        """Initialize all components."""
        try:
            # Initialize market connector
            self.connector = MT5Connector(
                account=self.config.mt5.account,
                password=self.config.mt5.password,
                server=self.config.mt5.server,
                timeout=self.config.mt5.timeout,
            )
            await self.connector.connect()
            
            # Initialize stream ingestion
            self.stream_ingestion = StreamIngestion(
                symbols=self.symbols,
                tick_buffer_size=self.config.data_engine.tick_buffer_size,
                candle_buffer_size=self.config.data_engine.candle_buffer_size,
            )
            
            # Initialize candle aggregator
            self.candle_aggregator = CandleAggregator(
                timeframe_minutes=self.config.data_engine.timeframe
            )
            
            # Initialize feature engineer
            self.feature_engineer = FeatureEngineer(
                atr_period=self.config.data_engine.atr_period,
                volatility_period=self.config.data_engine.volatility_period,
            )
            
            # Initialize microstructure processor
            self.microstructure_processor = MicrostructureProcessor(
                depth_levels=self.config.data_engine.microstructure_depth,
            )
            
            # Initialize relational features computer
            self.relational_features = RelationalFeaturesComputer(
                lookback_ticks=self.config.data_engine.correlation_lookback,
            )
            
            # Initialize messaging broker
            self.messaging_broker = MessagingBroker(
                backend=self.config.messaging.backend,
                zmq_host=self.config.messaging.zmq_host,
                zmq_port=self.config.messaging.zmq_port,
                redis_host=self.config.messaging.redis_host,
                redis_port=self.config.messaging.redis_port,
            )
            await self.messaging_broker.initialize()
            
            # Load initial candles
            for symbol in self.symbols:
                candles = await self.connector.get_candles(
                    symbol=symbol,
                    timeframe=self.config.data_engine.timeframe,
                    count=self.config.data_engine.candle_buffer_size,
                )
                if candles:
                    for candle in candles:
                        await self.stream_ingestion.ingest_candle(symbol, candle)
            
            # Subscribe to tick updates
            for symbol in self.symbols:
                await self.connector.subscribe_ticks(symbol, self._on_tick)
            
            # Register candle aggregator callback
            self.candle_aggregator.register_callback(self._on_candle_complete)
            
            logger.info("data_engine_components_initialized")
        except Exception as e:
            logger.error("data_engine_initialization_error", error=str(e))
            raise
    
    async def run(self):
        """Main engine loop."""
        self.running = True
        logger.info("data_engine_starting")
        
        try:
            # Feature computation loop
            while self.running:
                try:
                    await self._compute_and_publish_features()
                    await asyncio.sleep(self.feature_update_interval)
                except Exception as e:
                    logger.error("feature_computation_loop_error", error=str(e))
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error("data_engine_run_error", error=str(e))
            self.running = False
    
    async def _on_tick(self, symbol: str, tick: Dict[str, Any]):
        """Handle new tick from market connector."""
        try:
            # Ingest tick
            await self.stream_ingestion.ingest_tick(symbol, tick)
            
            # Update relational features
            price = (tick['bid'] + tick['ask']) / 2
            self.relational_features.add_price(symbol, price)
            
            # Add to candle aggregator
            completed_candle = self.candle_aggregator.add_tick(symbol, tick)
            
            # If candle completed, ingest it
            if completed_candle:
                await self.stream_ingestion.ingest_candle(symbol, completed_candle)
            
        except Exception as e:
            logger.error("tick_handling_error", symbol=symbol, error=str(e))
    
    async def _on_candle_complete(self, candle: Dict[str, Any]):
        """Handle completed candle (triggered by candle aggregator)."""
        try:
            symbol = candle['symbol']
            await self.stream_ingestion.ingest_candle(symbol, candle)
            logger.debug("candle_completed", symbol=symbol, time=candle['time'])
        except Exception as e:
            logger.error("candle_complete_error", error=str(e))
    
    async def _compute_and_publish_features(self):
        """Compute features and publish market feature packets."""
        try:
            for symbol in self.symbols:
                # Check if enough time has passed since last publish
                now = datetime.now()
                if (self.last_feature_publish_time[symbol] is not None and
                    (now - self.last_feature_publish_time[symbol]).total_seconds() < self.feature_update_interval):
                    continue
                
                # Get latest market state
                tick = self.stream_ingestion.get_latest_tick(symbol)
                if tick is None:
                    continue
                
                # Get history
                tick_history = self.stream_ingestion.get_tick_history(symbol, count=200)
                candle_history = self.stream_ingestion.get_candle_history(symbol, count=100)
                
                if not tick_history or not candle_history:
                    continue
                
                # Compute features
                price = (tick['bid'] + tick['ask']) / 2
                features = self.feature_engineer.compute_features(
                    symbol=symbol,
                    price=price,
                    bid=tick['bid'],
                    ask=tick['ask'],
                    tick_history=tick_history,
                    candle_history=candle_history,
                )
                
                # Compute microstructure tensor
                order_book = await self.connector.get_order_book(symbol, depth=self.config.data_engine.microstructure_depth)
                microstructure_tensor = None
                microstructure_dict = None
                
                if order_book:
                    microstructure_tensor = self.microstructure_processor.process_order_book(
                        symbol=symbol,
                        order_book=order_book,
                        mid_price=price,
                    )
                    if microstructure_tensor is not None:
                        microstructure_dict = {
                            'tensor': microstructure_tensor.tolist(),
                            'imbalance': float(self.microstructure_processor.create_depth_imbalance(microstructure_tensor)),
                            'profile': self.microstructure_processor.create_liquidity_profile(microstructure_tensor),
                        }
                
                # Compute relational features
                related_symbols = {s: 1.0 for s in self.symbols if s != symbol}
                relational = self.relational_features.compute_relational_features(
                    primary_symbol=symbol,
                    related_symbols=related_symbols,
                )
                
                # Get current candle state
                current_candle = self.candle_aggregator.get_current_candle(symbol)
                latest_candle = candle_history[-1] if candle_history else None
                
                candle_state = {
                    'time': latest_candle['time'].isoformat() if latest_candle else None,
                    'open': latest_candle['open'] if latest_candle else price,
                    'high': latest_candle['high'] if latest_candle else price,
                    'low': latest_candle['low'] if latest_candle else price,
                    'close': latest_candle['close'] if latest_candle else price,
                    'volume': latest_candle['volume'] if latest_candle else 0,
                }
                
                # Create and publish market feature packet
                packet = MarketFeaturePacket(
                    timestamp=tick['time'].isoformat(),
                    symbol=symbol,
                    tick={
                        'bid': tick['bid'],
                        'ask': tick['ask'],
                        'last': tick.get('last', price),
                        'volume': tick.get('volume', 0),
                    },
                    candles=candle_state,
                    features=features,
                    microstructure=microstructure_dict,
                    relational=relational,
                    event_flags={},
                )
                
                # Publish packet
                await self.messaging_broker.publish(
                    topic=self.config.messaging.market_features_topic,
                    message=packet.__dict__,
                )
                
                self.last_feature_publish_time[symbol] = now
                logger.debug("market_feature_packet_published", symbol=symbol)
        
        except Exception as e:
            logger.error("feature_publication_error", error=str(e))
    
    async def stop(self):
        """Stop the engine."""
        self.running = False
        
        if self.connector:
            await self.connector.disconnect()
        
        if self.messaging_broker:
            await self.messaging_broker.close()
        
        logger.info("data_engine_stopped")
