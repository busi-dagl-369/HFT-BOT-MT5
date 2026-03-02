"""
Tier 05 - Ratchet Exit Manager
Tracks peak profits, manages adaptive trailing exits, and closes positions
when deterioration triggers are breached.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import structlog

from ..config import get_config
from ..messaging import ExitStatePacket, MessagingBroker, ExecutionStatePacket, PredictionPacket


logger = structlog.get_logger(__name__)


class RatchetExitManager:
    """
    Prediction-aware ratchet exit manager.
    Continuously tracks and exits positions based on profit deterioration.
    """
    
    def __init__(self):
        """Initialize Ratchet Exit Manager."""
        self.config = get_config()
        self.running = False
        
        # Messaging
        self.messaging_broker: Optional[MessagingBroker] = None
        
        # State tracking
        self.symbols = self.config.data_engine.symbols
        self.position_tracking: Dict[str, Dict[str, Any]] = {}  # position_id -> tracking info
        self.daily_loss = 0.0
        self.consecutive_losses = 0
        
        logger.info("ratchet_exit_manager_initialized", symbols=self.symbols)
    
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
            
            # Subscribe to execution state
            await self.messaging_broker.subscribe(
                topic=self.config.messaging.execution_states_topic,
                callback=self._on_execution_state,
            )
            
            # Subscribe to predictions for alignment checks
            await self.messaging_broker.subscribe(
                topic=self.config.messaging.predictions_topic,
                callback=self._on_prediction_update,
            )
            
            logger.info("ratchet_exit_manager_initialized_messaging")
        except Exception as e:
            logger.error("ratchet_exit_manager_initialization_error", error=str(e))
            raise
    
    async def run(self):
        """Main exit manager loop."""
        self.running = True
        logger.info("ratchet_exit_manager_starting")
        
        while self.running:
            try:
                await self._check_exits()
                import asyncio
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error("ratchet_exit_manager_run_error", error=str(e))
                import asyncio
                await asyncio.sleep(1)
    
    async def _on_execution_state(self, message: Dict[str, Any]):
        """Handle execution state update from Execution Engine."""
        try:
            symbol = message.get('symbol')
            prediction_id = message.get('prediction_id')
            open_positions = message.get('open_positions', [])
            
            # Update tracking for each position
            for position in open_positions:
                pos_id = f"{symbol}_{position.get('position_id', 'unknown')}"
                
                if pos_id not in self.position_tracking:
                    # New position
                    self.position_tracking[pos_id] = {
                        'symbol': symbol,
                        'prediction_id': prediction_id,
                        'entry_price': position.get('entry_price'),
                        'volume': position.get('volume'),
                        'entry_time': datetime.now(),
                        'peak_pnl': 0.0,
                        'current_pnl': 0.0,
                        'ratchet_threshold': float('inf'),
                        'exit_triggered': False,
                    }
                
                # Update P&L
                current_pnl = message.get('pnl', 0.0)
                self.position_tracking[pos_id]['current_pnl'] = current_pnl
                
                # Track peak
                if current_pnl > self.position_tracking[pos_id]['peak_pnl']:
                    self.position_tracking[pos_id]['peak_pnl'] = current_pnl
        
        except Exception as e:
            logger.error("execution_state_handling_error", error=str(e))
    
    async def _on_prediction_update(self, message: Dict[str, Any]):
        """Handle prediction update for prediction alignment checks."""
        try:
            prediction = PredictionPacket(**message)
            
            # Check for positions that need alignment updates
            for pos_id, pos_data in self.position_tracking.items():
                if pos_data['symbol'] == prediction.symbol:
                    # Check for direction flip
                    if (prediction.direction == "UP" and pos_data.get('direction') == "SELL") or \
                       (prediction.direction == "DOWN" and pos_data.get('direction') == "BUY"):
                        logger.warning("prediction_direction_flip", position=pos_id)
                        pos_data['exit_triggered'] = True
                    
                    # Check confidence collapse
                    if prediction.confidence < self.config.exit_manager.ratchet_configs.get(
                        "CONFIDENCE_THRESHOLD", 0.5
                    ):
                        logger.warning("confidence_collapse", position=pos_id, confidence=prediction.confidence)
                        pos_data['exit_triggered'] = True
        
        except Exception as e:
            logger.error("prediction_update_handling_error", error=str(e))
    
    async def _check_exits(self):
        """Check all positions for exit triggers."""
        try:
            positions_to_close = []
            
            for pos_id, pos_data in self.position_tracking.items():
                # Skip already exited
                if pos_data.get('exit_triggered', False):
                    positions_to_close.append(pos_id)
                    continue
                
                # Calculate ratchet threshold
                peak_pnl = pos_data['peak_pnl']
                current_pnl = pos_data['current_pnl']
                
                # Determine ratchet config based on conditions
                ratchet_config_key = self._get_ratchet_config_key(pos_data)
                ratchet_config = self.config.exit_manager.ratchet_configs.get(
                    ratchet_config_key,
                    {'retracement_percent': 3.0, 'min_hold_ticks': 30}
                )
                
                # Calculate max allowed drawdown from peak
                max_drawdown_percent = ratchet_config['retracement_percent']
                max_allowed_drawdown = peak_pnl * (1.0 - max_drawdown_percent / 100.0)
                
                # Check if drawdown breached threshold
                if current_pnl < max_allowed_drawdown and peak_pnl > 0:
                    logger.info(
                        "ratchet_threshold_breached",
                        position=pos_id,
                        peak_pnl=peak_pnl,
                        current_pnl=current_pnl,
                        threshold=max_allowed_drawdown,
                    )
                    positions_to_close.append(pos_id)
            
            # Close triggered positions
            for pos_id in positions_to_close:
                await self._close_position(pos_id)
                del self.position_tracking[pos_id]
        
        except Exception as e:
            logger.error("exit_check_error", error=str(e))
    
    def _get_ratchet_config_key(self, pos_data: Dict[str, Any]) -> str:
        """Determine which ratchet config to use based on position context."""
        # This could be based on:
        # - Position age
        # - Ladder index
        # - Regime type
        # For now, simple heuristic:
        return "MODERATE_CONFIDENCE"
    
    async def _close_position(self, pos_id: str):
        """Close a position."""
        try:
            pos_data = self.position_tracking[pos_id]
            
            # Create exit state packet
            exit_packet = ExitStatePacket(
                position_id=pos_id,
                prediction_id=pos_data['prediction_id'],
                timestamp=datetime.now().isoformat(),
                symbol=pos_data['symbol'],
                ladder_index=0,  # Would be tracked in real implementation
                current_profit=pos_data['current_pnl'],
                peak_profit=pos_data['peak_pnl'],
                ratchet_threshold=pos_data['peak_pnl'] * 0.97,  # 3% from peak
                exit_triggered=True,
                ratchet_reason="DRAWDOWN_THRESHOLD_BREACHED",
            )
            
            # Publish exit state
            await self.messaging_broker.publish(
                topic=self.config.messaging.exit_states_topic,
                message=exit_packet.__dict__,
            )
            
            logger.info("position_closed", position=pos_id, pnl=pos_data['current_pnl'])
        except Exception as e:
            logger.error("position_closing_error", error=str(e))
    
    async def stop(self):
        """Stop the manager."""
        self.running = False
        
        if self.messaging_broker:
            await self.messaging_broker.close()
        
        logger.info("ratchet_exit_manager_stopped")
