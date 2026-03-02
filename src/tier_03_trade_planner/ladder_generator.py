"""
Ladder order generation from predicted paths.
"""

from typing import Dict, List, Any, Optional
import numpy as np
import structlog


logger = structlog.get_logger(__name__)


class LadderGenerator:
    """Generates limit-order ladders from predicted paths."""
    
    def generate_ladder(
        self,
        direction: str,
        path: Dict[str, Any],
        confidence: float,
        regime: str,
        config: Dict[str, Any],
        base_spacing: float = 10.0,
        max_orders: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Generate limit-order ladder.
        
        Args:
            direction: "BUY" or "SELL"
            path: Predicted path dict
            confidence: Prediction confidence
            regime: Market regime
            config: Regime-specific config
            base_spacing: Base spacing in pips
            max_orders: Maximum orders
            
        Returns:
            List of {price, volume, order_type, ladder_index}
        """
        try:
            target = path.get('target', 0)
            envelope_upper = path.get('envelope_upper', target * 1.5)
            envelope_lower = path.get('envelope_lower', target * 0.5)
            
            # Adjust spacing by volatility
            spacing = base_spacing * config.get('spacing_adjustment', 1.0)
            
            # Volume scaling by confidence
            if self.config.trade_planner.confidence_volume_scaling:
                base_volume = self.config.trade_planner.base_contract_size * (0.5 + confidence * 0.5)
            else:
                base_volume = self.config.trade_planner.base_contract_size
            
            # Generate orders
            orders = []
            num_orders = min(int(abs(target) / spacing), max_orders)
            
            if direction == "BUY":
                for i in range(num_orders):
                    price = i * spacing
                    volume = base_volume * (1.0 - i / (num_orders + 1))
                    orders.append({
                        'price': price,
                        'volume': volume,
                        'order_type': 'BUY',
                        'ladder_index': i,
                    })
            else:
                for i in range(num_orders):
                    price = -i * spacing
                    volume = base_volume * (1.0 - i / (num_orders + 1))
                    orders.append({
                        'price': price,
                        'volume': volume,
                        'order_type': 'SELL',
                        'ladder_index': i,
                    })
            
            logger.debug("ladder_generated", num_orders=len(orders), direction=direction)
            return orders
        
        except Exception as e:
            logger.error("ladder_generation_error", error=str(e))
            return []
