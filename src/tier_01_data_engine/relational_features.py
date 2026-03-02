"""
Relational feature computation for cross-asset market context.
Computes correlations, spreads, and co-movement metrics.
"""

from typing import Dict, List, Any, Optional
import numpy as np
from collections import defaultdict
import structlog


logger = structlog.get_logger(__name__)


class RelationalFeaturesComputer:
    """
    Computes cross-asset relational features and correlations.
    Captures market regime from related instruments.
    """
    
    def __init__(self, lookback_ticks: int = 100):
        """
        Initialize relational features computer.
        
        Args:
            lookback_ticks: Number of ticks to use for correlation
        """
        self.lookback_ticks = lookback_ticks
        self.price_history: Dict[str, List[float]] = defaultdict(list)
    
    def add_price(self, symbol: str, price: float, max_history: int = 1000):
        """
        Add price point for symbol.
        
        Args:
            symbol: Symbol
            price: Price
            max_history: Maximum history to keep
        """
        self.price_history[symbol].append(price)
        
        # Maintain max history
        if len(self.price_history[symbol]) > max_history:
            self.price_history[symbol] = self.price_history[symbol][-max_history:]
    
    def compute_correlation(
        self,
        symbol1: str,
        symbol2: str,
        lookback: Optional[int] = None,
    ) -> Optional[float]:
        """
        Compute correlation between two symbols.
        
        Args:
            symbol1: First symbol
            symbol2: Second symbol
            lookback: Number of ticks to use (uses default if None)
            
        Returns:
            Correlation coefficient [-1, 1]
        """
        try:
            if lookback is None:
                lookback = self.lookback_ticks
            
            prices1 = self.price_history.get(symbol1, [])[- lookback:]
            prices2 = self.price_history.get(symbol2, [])[- lookback:]
            
            if len(prices1) < lookback or len(prices2) < lookback:
                return None
            
            returns1 = np.diff(np.log(prices1))
            returns2 = np.diff(np.log(prices2))
            
            corr = np.corrcoef(returns1, returns2)[0, 1]
            
            if np.isnan(corr):
                return 0.0
            
            return float(corr)
        except Exception as e:
            logger.error("correlation_computation_error", error=str(e))
            return None
    
    def compute_spread(
        self,
        symbol1: str,
        symbol2: str,
        ratio: float = 1.0,
    ) -> Optional[float]:
        """
        Compute spread between two symbols.
        
        Spread = symbol1 - (ratio * symbol2)
        
        Args:
            symbol1: First symbol (numerator)
            symbol2: Second symbol (denominator)
            ratio: Ratio for second symbol
            
        Returns:
            Current spread
        """
        try:
            prices1 = self.price_history.get(symbol1, [])
            prices2 = self.price_history.get(symbol2, [])
            
            if len(prices1) == 0 or len(prices2) == 0:
                return None
            
            spread = prices1[-1] - (ratio * prices2[-1])
            return spread
        except Exception as e:
            logger.error("spread_computation_error", error=str(e))
            return None
    
    def compute_relational_features(
        self,
        primary_symbol: str,
        related_symbols: Dict[str, float],  # {symbol: weight}
    ) -> Dict[str, float]:
        """
        Compute comprehensive relational features.
        
        Args:
            primary_symbol: Main symbol
            related_symbols: Related symbols and weights {symbol: weight}
            
        Returns:
            Dictionary of relational features
        """
        features = {}
        
        try:
            for related_sym, weight in related_symbols.items():
                corr = self.compute_correlation(primary_symbol, related_sym)
                spread = self.compute_spread(primary_symbol, related_sym, weight)
                
                if corr is not None:
                    features[f'correlation_{related_sym}'] = corr
                
                if spread is not None:
                    features[f'spread_{related_sym}'] = spread
            
            # Composite features
            if len(related_symbols) > 1:
                correlations = [v for k, v in features.items() if 'correlation' in k and v is not None]
                if correlations:
                    features['mean_correlation'] = np.mean(correlations)
                    features['correlation_volatility'] = np.std(correlations)
            
            logger.debug("relational_features_computed", count=len(features))
            return features
        
        except Exception as e:
            logger.error("relational_features_error", error=str(e))
            return {}
    
    def compute_regime_context(
        self,
        symbols: List[str],
    ) -> Dict[str, Any]:
        """
        Compute cross-market regime context.
        
        Returns metrics indicating overall market structure.
        """
        try:
            if len(symbols) < 2:
                return {}
            
            context = {}
            
            # Pairwise correlations
            correlations = []
            for i, sym1 in enumerate(symbols):
                for sym2 in symbols[i+1:]:
                    corr = self.compute_correlation(sym1, sym2)
                    if corr is not None:
                        correlations.append(corr)
            
            if correlations:
                context['mean_cross_correlation'] = np.mean(correlations)
                context['correlation_dispersion'] = np.std(correlations)
                context['max_correlation'] = np.max(correlations)
                context['min_correlation'] = np.min(correlations)
            
            # Individual symbol momentum
            momentums = []
            for sym in symbols:
                if sym in self.price_history and len(self.price_history[sym]) >= 2:
                    returns = np.diff(np.log(self.price_history[sym][-10:]))
                    if len(returns) > 0:
                        momentum = np.mean(returns) * 10000  # Basis points
                        momentums.append(momentum)
            
            if momentums:
                context['mean_momentum'] = np.mean(momentums)
                context['momentum_dispersion'] = np.std(momentums)
            
            return context
        except Exception as e:
            logger.error("regime_context_error", error=str(e))
            return {}
