"""
Physics-aware validation guard for predictions.
Ensures predictions remain within statistically plausible bounds.
"""

from typing import Dict, Any, Tuple
import numpy as np
import structlog


logger = structlog.get_logger(__name__)


class PhysicsGuard:
    """
    Validates predictions against market physics.
    Constrains predictions to feasible ranges based on volatility.
    """
    
    def __init__(
        self,
        max_feasible_move_std: float = 3.0,
        confidence_dampening_enabled: bool = True,
    ):
        """
        Initialize physics guard.
        
        Args:
            max_feasible_move_std: Maximum move in standard deviations
            confidence_dampening_enabled: Whether to dampen confidence if infeasible
        """
        self.max_feasible_move_std = max_feasible_move_std
        self.confidence_dampening_enabled = confidence_dampening_enabled
    
    async def validate_and_adjust(
        self,
        direction: str,
        probability: float,
        confidence: float,
        expected_move: float,
        current_price: float,
        volatility: float,
        atr: float,
    ) -> Tuple[str, float, float, float, str]:
        """
        Validate prediction and adjust if needed.
        
        Args:
            direction: "UP", "DOWN", or "FLAT"
            probability: Probability [0, 1]
            confidence: Confidence [0, 1]
            expected_move: Expected move magnitude in pips
            current_price: Current price level
            volatility: Realized volatility
            atr: Average true range
            
        Returns:
            (adjusted_direction, adjusted_probability, adjusted_confidence, adjusted_expected_move, adjustment_reason)
        """
        try:
            adjustment_reason = "PASSED"
            adjusted_direction = direction
            adjusted_probability = probability
            adjusted_confidence = confidence
            adjusted_expected_move = expected_move
            
            # Calculate feasible move bounds
            feasible_move_max = volatility * self.max_feasible_move_std * 10000  # Convert to pips
            
            if expected_move is None or expected_move == 0:
                expected_move = atr * 0.5
            
            # Check if expected move exceeds feasible bounds
            if abs(expected_move) > feasible_move_max:
                adjustment_reason = "MOVE_EXCEEDS_FEASIBLE"
                
                # Dampen confidence
                if self.confidence_dampening_enabled:
                    excess_factor = abs(expected_move) / (feasible_move_max + 1e-8)
                    confidence_dampening = min(1.0, excess_factor)
                    adjusted_confidence = confidence * (1.0 - confidence_dampening * 0.5)
                
                # Cap expected move
                adjusted_expected_move = np.sign(expected_move) * feasible_move_max
            
            # Check probability extremes
            if probability < 0.0 or probability > 1.0:
                adjusted_probability = np.clip(probability, 0.0, 1.0)
                adjustment_reason = "PROBABILITY_CLIPPED"
            
            # Check for weak signals with high expected moves
            if confidence < 0.5 and abs(expected_move) > atr:
                adjusted_confidence = min(adjusted_confidence, 0.5)
                adjustment_reason = "WEAK_HIGH_MOVE"
            
            # Ensure directional consistency
            if direction == "FLAT":
                adjusted_probability = 0.5
                if abs(adjusted_expected_move) > atr * 0.2:
                    adjusted_expected_move = atr * 0.2
                    adjustment_reason = "FLAT_MOVE_REDUCED"
            
            if adjustment_reason != "PASSED":
                logger.debug(
                    "physics_guard_adjustment",
                    original_move=expected_move,
                    adjusted_move=adjusted_expected_move,
                    reason=adjustment_reason,
                )
            
            return (
                adjusted_direction,
                adjusted_probability,
                adjusted_confidence,
                adjusted_expected_move,
                adjustment_reason,
            )
        
        except Exception as e:
            logger.error("physics_guard_validation_error", error=str(e))
            return direction, probability, confidence, expected_move, "ERROR"
