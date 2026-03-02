"""
Tier 02 - Main Prediction Engine
Orchestrates expert ensemble, temporal fusion, regime detection, and physics validation.
Produces probabilistic directional forecasts with iterative refinement.
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import uuid4
import numpy as np
import structlog

from ..config import get_config
from ..messaging import PredictionPacket, MessagingBroker, MarketFeaturePacket
from .experts import (
    MicrostructureExpert,
    MacroTechnicalExpert,
    SentimentExpert,
    RelationalExpert,
)
from .temporal_fusion import TemporalFusionLayer
from .regime_detector import RegimeDetector
from .physics_guard import PhysicsGuard


logger = structlog.get_logger(__name__)


class PredictionEngine:
    """
    Hybrid expert-ensemble prediction engine with temporal fusion and iterative refinement.
    Produces robust directional forecasts and regime classifications.
    """
    
    def __init__(self):
        """Initialize Prediction Engine."""
        self.config = get_config()
        self.running = False
        
        # Expert models
        self.microstructure_expert = MicrostructureExpert(
            input_depth=self.config.data_engine.microstructure_depth
        )
        self.macro_technical_expert = MacroTechnicalExpert()
        self.sentiment_expert = SentimentExpert()
        self.relational_expert = RelationalExpert()
        
        self.experts = [
            self.microstructure_expert,
            self.macro_technical_expert,
            self.sentiment_expert,
            self.relational_expert,
        ]
        
        # Fusion and validation
        self.temporal_fusion = TemporalFusionLayer(
            num_experts=len(self.experts),
            fusion_type=self.config.prediction_engine.temporal_fusion_type,
        )
        self.regime_detector = RegimeDetector()
        self.physics_guard = PhysicsGuard(
            max_feasible_move_std=self.config.prediction_engine.max_feasible_move_std,
        )
        
        # Messaging
        self.messaging_broker: Optional[MessagingBroker] = None
        
        # State
        self.symbols = self.config.data_engine.symbols
        self.inference_frequency = self.config.prediction_engine.inference_frequency
        self.last_prediction_time: Dict[str, datetime] = {sym: None for sym in self.symbols}
        
        # Performance tracking
        self.prediction_log: List[Dict[str, Any]] = []
        
        logger.info("prediction_engine_initialized", symbols=self.symbols)
    
    async def initialize(self):
        """Initialize messaging and models."""
        try:
            self.messaging_broker = MessagingBroker(
                backend=self.config.messaging.backend,
                zmq_host=self.config.messaging.zmq_host,
                zmq_port=self.config.messaging.zmq_port,
                redis_host=self.config.messaging.redis_host,
                redis_port=self.config.messaging.redis_port,
            )
            await self.messaging_broker.initialize()
            
            # Subscribe to market feature packets
            await self.messaging_broker.subscribe(
                topic=self.config.messaging.market_features_topic,
                callback=self._on_market_features,
            )
            
            logger.info("prediction_engine_components_initialized")
        except Exception as e:
            logger.error("prediction_engine_initialization_error", error=str(e))
            raise
    
    async def run(self):
        """Main engine loop."""
        self.running = True
        logger.info("prediction_engine_starting")
        
        while self.running:
            try:
                await asyncio.sleep(1)
            except Exception as e:
                logger.error("prediction_engine_run_error", error=str(e))
                await asyncio.sleep(1)
    
    async def _on_market_features(self, message: Dict[str, Any]):
        """Handle market feature packet from Data Engine."""
        try:
            # Parse market feature packet
            symbol = message.get('symbol')
            timestamp = message.get('timestamp')
            
            if symbol and symbol in self.symbols:
                # Check if enough time has passed
                now = datetime.now()
                if (self.last_prediction_time[symbol] is not None and
                    (now - self.last_prediction_time[symbol]).total_seconds() < self.inference_frequency):
                    return
                
                # Perform inference
                await self._predict(message)
                self.last_prediction_time[symbol] = now
        except Exception as e:
            logger.error("market_features_handling_error", error=str(e))
    
    async def _predict(self, market_features: Dict[str, Any]):
        """
        Perform prediction with expert ensemble and iterative refinement.
        
        Args:
            market_features: Market feature packet dict
        """
        try:
            symbol = market_features['symbol']
            
            # Run initial inference
            prediction = await self._run_initial_inference(market_features)
            
            # Iterative refinement loop
            for iteration in range(self.config.prediction_engine.max_refinement_iterations):
                refined_prediction = await self._refine_prediction(prediction, market_features, iteration)
                
                # Check convergence
                convergence = self._check_convergence(prediction, refined_prediction)
                prediction = refined_prediction
                
                if convergence < self.config.prediction_engine.refinement_convergence_threshold:
                    logger.debug("prediction_refinement_converged", symbol=symbol, iteration=iteration)
                    break
            
            # Publish prediction packet
            packet = self._create_prediction_packet(prediction, market_features)
            await self.messaging_broker.publish(
                topic=self.config.messaging.predictions_topic,
                message=packet.__dict__,
            )
            
            logger.debug("prediction_published", symbol=symbol, prediction_id=packet.prediction_id)
        
        except Exception as e:
            logger.error("prediction_error", symbol=market_features.get('symbol'), error=str(e))
    
    async def _run_initial_inference(self, market_features: Dict[str, Any]) -> Dict[str, Any]:
        """Run initial inference from all experts."""
        try:
            expert_signals = []
            expert_confidences = {}
            
            # Get inference from each expert
            for expert_name, expert in [
                ("microstructure", self.microstructure_expert),
                ("macro_technical", self.macro_technical_expert),
                ("sentiment", self.sentiment_expert),
                ("relational", self.relational_expert),
            ]:
                signal, confidence = await expert.infer(market_features)
                expert_signals.append((signal, confidence))
                expert_confidences[expert_name] = confidence
            
            # Temporal fusion
            fused_signal, fused_confidence, context = await self.temporal_fusion.fuse_expert_signals(
                expert_signals
            )
            
            # Regime detection
            regime = await self.regime_detector.detect_regime(
                temporal_signal=fused_signal,
                temporal_confidence=fused_confidence,
                context=context,
                features=market_features.get('features', {}),
            )
            
            # Probability and direction
            probability = (fused_signal + 1.0) / 2.0  # Convert [-1, 1] to [0, 1]
            direction = "UP" if fused_signal > 0.2 else ("DOWN" if fused_signal < -0.2 else "FLAT")
            
            # Expected move
            atr = market_features.get('features', {}).get('atr', 10.0)
            expected_move = abs(fused_signal) * atr
            
            return {
                'expert_signals': expert_signals,
                'expert_confidences': expert_confidences,
                'fused_signal': fused_signal,
                'fused_confidence': fused_confidence,
                'context': context,
                'regime': regime,
                'probability': probability,
                'direction': direction,
                'expected_move': expected_move,
                'market_features': market_features,
            }
        except Exception as e:
            logger.error("initial_inference_error", error=str(e))
            raise
    
    async def _refine_prediction(
        self,
        prediction: Dict[str, Any],
        market_features: Dict[str, Any],
        iteration: int,
    ) -> Dict[str, Any]:
        """Refine prediction with iterative re-weighting."""
        try:
            # Re-weight experts based on disagreement
            signals = np.array([s for s, _ in prediction['expert_signals']])
            signal_std = np.std(signals)
            
            # Higher disagreement = lower refinement confidence
            disagreement_penalty = signal_std * 0.1
            
            # Apply physics guard
            (
                adjusted_direction,
                adjusted_probability,
                adjusted_confidence,
                adjusted_expected_move,
                adjustment_reason,
            ) = await self.physics_guard.validate_and_adjust(
                direction=prediction['direction'],
                probability=prediction['probability'],
                confidence=prediction['fused_confidence'] - disagreement_penalty,
                expected_move=prediction['expected_move'],
                current_price=market_features['tick'].get('bid', 0),
                volatility=market_features['features'].get('realized_volatility', 0.001),
                atr=market_features['features'].get('atr', 10.0),
            )
            
            refined = prediction.copy()
            refined['direction'] = adjusted_direction
            refined['probability'] = adjusted_probability
            refined['fused_confidence'] = adjusted_confidence
            refined['expected_move'] = adjusted_expected_move
            refined['adjustment_reason'] = adjustment_reason
            refined['iteration'] = iteration
            
            return refined
        except Exception as e:
            logger.error("prediction_refinement_error", error=str(e))
            return prediction
    
    def _check_convergence(self, pred1: Dict[str, Any], pred2: Dict[str, Any]) -> float:
        """
        Check convergence between two predictions.
        
        Returns:
            Convergence distance [0, 1]
        """
        try:
            # Compare key metrics
            signal_diff = abs(pred1['fused_signal'] - pred2['fused_signal'])
            conf_diff = abs(pred1['fused_confidence'] - pred2['fused_confidence'])
            dir_diff = 0.0 if pred1['direction'] == pred2['direction'] else 1.0
            
            # Weighted average
            convergence = (signal_diff * 0.4 + conf_diff * 0.3 + dir_diff * 0.3)
            return convergence
        except:
            return 0.0
    
    def _create_prediction_packet(
        self,
        prediction: Dict[str, Any],
        market_features: Dict[str, Any],
    ) -> PredictionPacket:
        """Create prediction packet for downstream tiers."""
        try:
            prediction_id = f"pred_{uuid4().hex[:12]}_{datetime.now().timestamp()}"
            
            # Action bias based on regime
            regime = prediction['regime']
            action_bias_map = {
                "TREND": "TREND",
                "PULLBACK": "TREND",
                "MEAN_REVERSION": "MEAN_REVERSION",
                "BREAKOUT": "TREND",
                "NEUTRAL": "NEUTRAL",
            }
            action_bias = action_bias_map.get(regime, "NEUTRAL")
            
            packet = PredictionPacket(
                prediction_id=prediction_id,
                timestamp=datetime.now().isoformat(),
                symbol=market_features['symbol'],
                direction=prediction['direction'],
                probability=prediction['probability'],
                confidence=prediction['fused_confidence'],
                expected_move=prediction['expected_move'],
                regime=prediction['regime'],
                action_bias=action_bias,
                return_distribution={
                    'p10': -prediction['expected_move'] * 0.5,
                    'p25': -prediction['expected_move'] * 0.25,
                    'p50': 0.0,
                    'p75': prediction['expected_move'] * 0.25,
                    'p90': prediction['expected_move'] * 0.5,
                },
                expert_signals={
                    f'expert_{i}': signal for i, (signal, _) in enumerate(prediction['expert_signals'])
                },
            )
            
            # Log prediction
            self.prediction_log.append({
                'prediction_id': prediction_id,
                'timestamp': packet.timestamp,
                'symbol': packet.symbol,
                'direction': packet.direction,
                'probability': packet.probability,
                'confidence': packet.confidence,
                'regime': packet.regime,
            })
            
            # Limit log size
            if len(self.prediction_log) > 10000:
                self.prediction_log = self.prediction_log[-10000:]
            
            return packet
        except Exception as e:
            logger.error("prediction_packet_creation_error", error=str(e))
            raise
    
    async def stop(self):
        """Stop the engine."""
        self.running = False
        
        if self.messaging_broker:
            await self.messaging_broker.close()
        
        logger.info("prediction_engine_stopped")
