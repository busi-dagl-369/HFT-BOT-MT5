"""
Market regime detection and classification.
Classifies current market state into regime categories.
"""

from typing import Dict, Any, Optional
import numpy as np
import structlog


logger = structlog.get_logger(__name__)


class RegimeDetector:
    """
    Detects and classifies market regime from contextual features.
    """
    
    REGIMES = ["TREND", "PULLBACK", "MEAN_REVERSION", "BREAKOUT", "NEUTRAL"]
    
    def __init__(self):
        """Initialize regime detector."""
        self.regime_history = []
        self.max_history = 60
    
    async def detect_regime(
        self,
        temporal_signal: float,
        temporal_confidence: float,
        context: Dict[str, Any],
        features: Dict[str, Any],
    ) -> str:
        """
        Detect current market regime.
        
        Args:
            temporal_signal: Fused temporal signal [-1, 1]
            temporal_confidence: Confidence of fused signal [0, 1]
            context: Context dict from temporal fusion
            features: Market features dict
            
        Returns:
            Regime classification string
        """
        try:
            # Extract features for regime determination
            persistence = context.get('persistence', 0.5)
            volatility = features.get('realized_volatility', 0.0)
            momentum = features.get('momentum_1m', 0.0)
            atr = features.get('atr', 0.001)
            
            # Regime decision logic
            regime = self._classify_regime(
                signal=temporal_signal,
                confidence=temporal_confidence,
                persistence=persistence,
                volatility=volatility,
                momentum=momentum,
                atr=atr,
            )
            
            # Add to history
            self.regime_history.append(regime)
            if len(self.regime_history) > self.max_history:
                self.regime_history = self.regime_history[-self.max_history:]
            
            return regime
        except Exception as e:
            logger.error("regime_detection_error", error=str(e))
            return "NEUTRAL"
    
    def _classify_regime(
        self,
        signal: float,
        confidence: float,
        persistence: float,
        volatility: float,
        momentum: float,
        atr: float,
    ) -> str:
        """
        Classify regime based on signal characteristics.
        """
        
        # Neutral regime: low confidence or low signal strength
        if confidence < 0.5 or abs(signal) < 0.2:
            return "NEUTRAL"
        
        # Strong persistence + strong signal = TREND
        if persistence > 0.7 and abs(signal) > 0.6 and confidence > 0.65:
            return "TREND"
        
        # Moderate persistence + moderate signal = PULLBACK/CONTINUATION
        if persistence > 0.5 and 0.3 < abs(signal) <= 0.6:
            abs_momentum = abs(momentum)
            if abs_momentum < atr * 0.3:
                return "PULLBACK"
            else:
                return "BREAKOUT"
        
        # Low persistence + reversal signal = MEAN_REVERSION
        if persistence < 0.4 and confidence > 0.6:
            return "MEAN_REVERSION"
        
        # Default to neutral
        return "NEUTRAL"
    
    def get_regime_history(self) -> list:
        """Get regime history."""
        return self.regime_history.copy()
    
    def get_regime_persistence(self) -> float:
        """
        Calculate how long current regime has persisted.
        
        Returns:
            Persistence score [0, 1]
        """
        if len(self.regime_history) < 2:
            return 0.0
        
        current_regime = self.regime_history[-1]
        persistence_count = sum(1 for r in reversed(self.regime_history) if r == current_regime)
        persistence = min(1.0, persistence_count / 20.0)  # Max out at 20 steps
        
        return persistence
    
    def reset(self):
        """Reset regime history."""
        self.regime_history.clear()
