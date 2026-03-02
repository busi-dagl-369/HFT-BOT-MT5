"""
Microstructure tensor processing for order-book data.
Constructs normalized depth tensors for deep learning models.
"""

from typing import Dict, List, Any, Optional
import numpy as np
import structlog


logger = structlog.get_logger(__name__)


class MicrostructureProcessor:
    """
    Processes order-book microstructure into normalized tensors.
    Creates DeepLOB-style depth tensors for neural network models.
    """
    
    def __init__(self, depth_levels: int = 20):
        """
        Initialize microstructure processor.
        
        Args:
            depth_levels: Number of order book depth levels to capture
        """
        self.depth_levels = depth_levels
    
    def process_order_book(
        self,
        symbol: str,
        order_book: Dict[str, Any],
        mid_price: float,
    ) -> Optional[np.ndarray]:
        """
        Process order book snapshot into a normalized microstructure tensor.
        
        Creates a tensor of shape (depth_levels, 4) containing:
        - Bid price relative to mid
        - Bid volume
        - Ask price relative to mid
        - Ask volume
        
        Args:
            symbol: Symbol
            order_book: {bids: [(price, volume), ...], asks: [...]}
            mid_price: Current mid price for normalization
            
        Returns:
            Normalized microstructure tensor (depth_levels, 4)
        """
        try:
            tensor = np.zeros((self.depth_levels, 4), dtype=np.float32)
            
            bids = order_book.get('bids', [])
            asks = order_book.get('asks', [])
            
            # Fill bid side (left side of midprice)
            for i, (price, volume) in enumerate(bids[:self.depth_levels]):
                if price > 0 and mid_price > 0:
                    price_diff = (price - mid_price) / mid_price * 10000  # Normalized pips
                    tensor[i, 0] = price_diff  # Relative price
                    tensor[i, 1] = np.log(volume + 1)  # Log volume
            
            # Fill ask side (right side of midprice)
            for i, (price, volume) in enumerate(asks[:self.depth_levels]):
                if price > 0 and mid_price > 0:
                    price_diff = (price - mid_price) / mid_price * 10000  # Normalized pips
                    tensor[i, 2] = price_diff  # Relative price
                    tensor[i, 3] = np.log(volume + 1)  # Log volume
            
            logger.debug(
                "microstructure_tensor_created",
                symbol=symbol,
                shape=(self.depth_levels, 4),
            )
            return tensor
        
        except Exception as e:
            logger.error("microstructure_processing_error", symbol=symbol, error=str(e))
            return None
    
    def create_depth_imbalance(self, tensor: np.ndarray) -> float:
        """
        Compute depth-weighted imbalance from microstructure tensor.
        
        Imbalance = sum(bid_volumes) - sum(ask_volumes)
        """
        try:
            bid_volume = np.sum(np.exp(tensor[:, 1]))  # Exponentiate log volumes
            ask_volume = np.sum(np.exp(tensor[:, 3]))
            
            total = bid_volume + ask_volume
            if total == 0:
                return 0.0
            
            imbalance = (bid_volume - ask_volume) / (total + 1e-8)
            return imbalance
        except:
            return 0.0
    
    def create_liquidity_profile(self, tensor: np.ndarray) -> Dict[str, float]:
        """
        Create liquidity profile from microstructure tensor.
        
        Returns metrics on depth and liquidity distribution.
        """
        try:
            bid_volumes = np.exp(tensor[:, 1])
            ask_volumes = np.exp(tensor[:, 3])
            
            profile = {
                'bid_total_volume': np.sum(bid_volumes),
                'ask_total_volume': np.sum(ask_volumes),
                'bid_level_1_volume': bid_volumes[0] if len(bid_volumes) > 0 else 0,
                'ask_level_1_volume': ask_volumes[0] if len(ask_volumes) > 0 else 0,
                'bid_concentration': bid_volumes[0] / (np.sum(bid_volumes) + 1e-8),
                'ask_concentration': ask_volumes[0] / (np.sum(ask_volumes) + 1e-8),
            }
            return profile
        except:
            return {}
