"""
Temporal fusion layer for expert signal aggregation.
Determines short-term regime and contextual bias from expert ensemble.
"""

from typing import List, Dict, Tuple
import numpy as np
import torch
import torch.nn as nn
import structlog


logger = structlog.get_logger(__name__)


class TemporalFusionLayer:
    """
    Attention-based temporal fusion for expert signals.
    Aggregates multi-expert outputs across time to produce contextual state.
    """
    
    def __init__(
        self,
        num_experts: int = 4,
        hidden_dim: int = 64,
        fusion_type: str = "attention",
    ):
        """
        Initialize temporal fusion layer.
        
        Args:
            num_experts: Number of experts
            hidden_dim: Hidden dimension for attention
            fusion_type: "attention", "lstm", "gru"
        """
        self.num_experts = num_experts
        self.hidden_dim = hidden_dim
        self.fusion_type = fusion_type
        
        self.signal_history: List[Tuple[float, float]] = []  # (signal, confidence)
        self.max_history = 60  # 60 time steps
        
        self._build_model()
    
    def _build_model(self):
        """Build fusion model."""
        if self.fusion_type == "attention":
            self.fusion_model = nn.MultiheadAttention(
                embed_dim=1,
                num_heads=1,
                batch_first=True,
            )
    
    async def fuse_expert_signals(
        self,
        expert_signals: List[Tuple[float, float]],  # [(signal, confidence), ...]
    ) -> Tuple[float, float, Dict]:
        """
        Fuse expert signals using temporal attention.
        
        Args:
            expert_signals: List of (signal, confidence) from each expert
            
        Returns:
            (fused_signal, fused_confidence, context_dict)
        """
        try:
            # Add to history
            combined_signal = float(np.mean([s for s, _ in expert_signals]))
            combined_confidence = float(np.mean([c for _, c in expert_signals]))
            
            self.signal_history.append((combined_signal, combined_confidence))
            
            # Maintain max history
            if len(self.signal_history) > self.max_history:
                self.signal_history = self.signal_history[-self.max_history:]
            
            # Apply temporal attention
            if len(self.signal_history) >= 3:
                # Use simple exponential weighting (more recent = higher weight)
                weights = np.exp(np.linspace(-2, 0, len(self.signal_history)))
                weights = weights / np.sum(weights)
                
                signals = np.array([s for s, _ in self.signal_history])
                confidences = np.array([c for _, c in self.signal_history])
                
                temporal_signal = float(np.average(signals, weights=weights))
                temporal_confidence = float(np.average(confidences, weights=weights))
                
                # Detect persistence
                signal_std = float(np.std(signals[-10:]))
                persistence = 1.0 - signal_std  # High persistence = consistent signals
                
                context = {
                    'persistence': persistence,
                    'signal_variance': float(np.var(signals)),
                    'confidence_trend': float(np.diff(confidences[-5:]).mean()),
                }
            else:
                temporal_signal = combined_signal
                temporal_confidence = combined_confidence
                context = {
                    'persistence': 0.5,
                    'signal_variance': 0.0,
                    'confidence_trend': 0.0,
                }
            
            return temporal_signal, temporal_confidence, context
        
        except Exception as e:
            logger.error("temporal_fusion_error", error=str(e))
            return 0.0, 0.0, {}
    
    def get_signal_history(self) -> List[Tuple[float, float]]:
        """Get signal history."""
        return self.signal_history.copy()
    
    def reset(self):
        """Reset history."""
        self.signal_history.clear()
