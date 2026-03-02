"""
Ratchet threshold calculation engine.
Computes adaptive trailing exit thresholds based on prediction strength and regime.
"""

from typing import Dict, Tuple
import numpy as np
import structlog


logger = structlog.get_logger(__name__)


class RatchetCalculator:
    """Calculates adaptive ratchet thresholds for trailing exits."""
    
    def calculate_ratchet(
        self,
        peak_profit: float,
        confidence: float,
        regime: str,
        ladder_position: int = 0,
        max_ladder_positions: int = 20,
    ) -> Tuple[float, str]:
        """
        Calculate ratchet threshold for a position.
        
        Args:
            peak_profit: Peak profit since entry
            confidence: Prediction confidence [0, 1]
            regime: Market regime
            ladder_position: Position in ladder sequence
            max_ladder_positions: Total positions in ladder
            
        Returns:
            (threshold: float, description: str)
        """
        try:
            # Base configuration
            if confidence > 0.65:
                base_retracement = 5.0  # 5% from peak
            elif confidence > 0.55:
                base_retracement = 3.0  # 3% from peak
            else:
                base_retracement = 1.5  # 1.5% from peak
            
            # Regime adjustment
            regime_multiplier = {
                "TREND": 1.0,
                "PULLBACK": 0.9,
                "MEAN_REVERSION": 0.7,
                "BREAKOUT": 1.1,
                "NEUTRAL": 0.5,
            }.get(regime, 1.0)
            
            # Ladder position adjustment (early = more room, late = tighter)
            position_factor = 1.0 + (ladder_position / max_ladder_positions) * 0.3
            
            # Combined retracement rate
            retracement_rate = base_retracement * regime_multiplier * position_factor
            
            # Calculate threshold
            threshold = peak_profit * (1.0 - retracement_rate / 100.0)
            
            description = f"Ratchet set at {retracement_rate:.1f}% from peak"
            
            return threshold, description
        
        except Exception as e:
            logger.error("ratchet_calculation_error", error=str(e))
            return peak_profit * 0.97, "Default ratchet (3%)"
