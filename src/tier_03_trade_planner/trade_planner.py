"""
Tier 03 - Adaptive Trade Planner
Converts probabilistic AI forecasts into dynamically evolving limit-order ladders.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from uuid import uuid4
import numpy as np
import structlog

from ..config import get_config
from ..messaging import TradePlanPacket, MessagingBroker, PredictionPacket
from .ladder_generator import LadderGenerator
from .path_modeler import PathModeler


logger = structlog.get_logger(__name__)


class TradePlanner:
    """
    Converts predictions into adaptive limit-order ladders.
    Ladders evolve dynamically with price and prediction updates.
    """
    
    def __init__(self):
        """Initialize Trade Planner."""
        self.config = get_config()
        self.running = False
        
        # Components
        self.path_modeler = PathModeler()
        self.ladder_generator = LadderGenerator()
        self.messaging_broker: Optional[MessagingBroker] = None
        
        # State tracking
        self.symbols = self.config.data_engine.symbols
        self.active_ladders: Dict[str, Dict[str, Any]] = {sym: None for sym in self.symbols}
        self.last_ladder_prediction_id: Dict[str, str] = {sym: None for sym in self.symbols}
        
        logger.info("trade_planner_initialized", symbols=self.symbols)
    
    async def initialize(self):
        """Initialize messaging."""
        try:
            self.messaging_broker = MessagingBroker(
                backend=self.config.messaging.backend,
                zmq_host=self.config.messaging.zmq_host,
                zmq_port=self.config.messaging.zmq_port,
                redis_host=self.config.messaging.redis_host,
                redis_port=self.config.messaging.redis_port,
            )
            await self.messaging_broker.initialize()
            
            # Subscribe to predictions
            await self.messaging_broker.subscribe(
                topic=self.config.messaging.predictions_topic,
                callback=self._on_prediction,
            )
            
            logger.info("trade_planner_components_initialized")
        except Exception as e:
            logger.error("trade_planner_initialization_error", error=str(e))
            raise
    
    async def run(self):
        """Main planner loop."""
        self.running = True
        logger.info("trade_planner_starting")
        
        while self.running:
            try:
                await self._update_active_ladders()
                import asyncio
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error("trade_planner_run_error", error=str(e))
                import asyncio
                await asyncio.sleep(1)
    
    async def _on_prediction(self, message: Dict[str, Any]):
        """Handle new prediction from Prediction Engine."""
        try:
            symbol = message.get('symbol')
            if symbol not in self.symbols:
                return
            
            # Parse prediction
            prediction = PredictionPacket(**message)
            
            # Check activation thresholds
            if (prediction.probability > self.config.trade_planner.min_probability and
                prediction.confidence > self.config.trade_planner.min_confidence):
                
                # Generate new ladder plan
                plan = await self._plan_ladder(prediction)
                
                # Publish trade plan
                if plan:
                    await self.messaging_broker.publish(
                        topic=self.config.messaging.trade_plans_topic,
                        message=plan.__dict__,
                    )
                    
                    # Update state
                    self.active_ladders[symbol] = plan.__dict__
                    self.last_ladder_prediction_id[symbol] = prediction.prediction_id
                    
                    logger.info("trade_plan_generated", symbol=symbol, prediction_id=prediction.prediction_id)
            else:
                # Cancel existing ladder if thresholds not met
                if self.active_ladders[symbol]:
                    self.active_ladders[symbol] = None
                    logger.debug("ladder_suspended_low_confidence", symbol=symbol)
        
        except Exception as e:
            logger.error("prediction_handling_error", error=str(e))
    
    async def _plan_ladder(self, prediction: PredictionPacket) -> Optional[TradePlanPacket]:
        """Generate trade plan ladder from prediction."""
        try:
            # Get regime-specific configuration
            regime_config = self.config.trade_planner.regime_configs.get(
                prediction.regime,
                self.config.trade_planner.regime_configs["NEUTRAL"]
            )
            
            # Ladder direction
            ladder_direction = "BUY" if prediction.direction == "UP" else "SELL"
            
            # Model predicted path
            path = self.path_modeler.model_path(
                direction=prediction.direction,
                expected_move=prediction.expected_move,
                return_distribution=prediction.return_distribution,
                volatility_factor=1.0,
            )
            
            # Generate ladder orders
            ladder_orders = self.ladder_generator.generate_ladder(
                direction=ladder_direction,
                path=path,
                confidence=prediction.confidence,
                regime=prediction.regime,
                config=regime_config,
                base_spacing=self.config.trade_planner.ladder_base_spacing,
                max_orders=self.config.trade_planner.ladder_max_orders,
            )
            
            if not ladder_orders:
                logger.warning("ladder_generation_failed", symbol=prediction.symbol)
                return None
            
            # Create trade plan packet
            plan = TradePlanPacket(
                prediction_id=prediction.prediction_id,
                timestamp=datetime.now().isoformat(),
                symbol=prediction.symbol,
                ladder_direction=ladder_direction,
                ladder_regime=prediction.regime,
                spacing=self.config.trade_planner.ladder_base_spacing,
                ladder_orders=ladder_orders,
                predicted_path=path,
                regime_duration_ticks=100,  # Placeholder
            )
            
            return plan
        except Exception as e:
            logger.error("ladder_planning_error", symbol=prediction.symbol, error=str(e))
            return None
    
    async def _update_active_ladders(self):
        """Update active ladders to follow predicted paths."""
        try:
            for symbol in self.symbols:
                ladder = self.active_ladders[symbol]
                if ladder is None:
                    continue
                
                # Update ladder positions based on market movement
                # This would be updated in real-time as price moves
                # For now, this is a placeholder for continuous ladder evolution
        except Exception as e:
            logger.error("ladder_update_error", error=str(e))
    
    async def stop(self):
        """Stop the planner."""
        self.running = False
        
        if self.messaging_broker:
            await self.messaging_broker.close()
        
        logger.info("trade_planner_stopped")
