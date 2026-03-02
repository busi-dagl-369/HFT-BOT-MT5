"""
Backtesting and simulation framework.
Allows running the system on historical data without MT5.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any
import json
import structlog

from src.config import get_config
from src.tier_01_data_engine import DataEngine
from src.tier_02_prediction_engine import PredictionEngine
from src.tier_03_trade_planner import TradePlanner
from src.tier_05_exit_manager import RatchetExitManager


logger = structlog.get_logger(__name__)


class BacktestSimulator:
    """
    Simulates system behavior on historical tick data.
    Useful for validation and parameter tuning without live trading.
    """
    
    def __init__(self, data_file: str):
        """
        Initialize backtest simulator.
        
        Args:
            data_file: Path to historical tick data (JSON or CSV)
        """
        self.config = get_config()
        self.data_file = data_file
        self.tick_data: List[Dict[str, Any]] = []
        
        # Tiers
        self.data_engine: DataEngine = None
        self.prediction_engine: PredictionEngine = None
        self.trade_planner: TradePlanner = None
        self.exit_manager: RatchetExitManager = None
        
        # Statistics
        self.stats = {
            'total_ticks': 0,
            'predictions': 0,
            'trades_opened': 0,
            'trades_closed': 0,
            'total_pnl': 0.0,
            'accuracy': 0.0,
        }
    
    async def load_data(self):
        """Load historical tick data."""
        try:
            with open(self.data_file, 'r') as f:
                if self.data_file.endswith('.json'):
                    self.tick_data = json.load(f)
                else:
                    # CSV parsing
                    import csv
                    reader = csv.DictReader(f)
                    self.tick_data = [row for row in reader]
            
            logger.info("historical_data_loaded", ticks=len(self.tick_data))
        except Exception as e:
            logger.error("data_loading_error", error=str(e))
            raise
    
    async def run_backtest(self):
        """Run backtest on historical data."""
        try:
            logger.info("backtest_starting", total_ticks=len(self.tick_data))
            
            # Initialize tiers
            self.data_engine = DataEngine()
            self.prediction_engine = PredictionEngine()
            self.trade_planner = TradePlanner()
            self.exit_manager = RatchetExitManager()
            
            await self.data_engine.initialize()
            await self.prediction_engine.initialize()
            await self.trade_planner.initialize()
            await self.exit_manager.initialize()
            
            # Simulate tick by tick
            for i, tick in enumerate(self.tick_data):
                if i % 100 == 0:
                    logger.debug("backtest_progress", tick_number=i, total=len(self.tick_data))
                
                # Inject tick into system
                await self._inject_tick(tick)
                
                # Small delay to allow async processing
                await asyncio.sleep(0.001)
            
            logger.info("backtest_complete", stats=self.stats)
            self._print_backtest_summary()
        
        except Exception as e:
            logger.error("backtest_error", error=str(e))
            raise
    
    async def _inject_tick(self, tick: Dict[str, Any]):
        """Inject a tick into the system."""
        try:
            # Format tick for data engine
            processed_tick = {
                'bid': float(tick.get('bid', 0)),
                'ask': float(tick.get('ask', 0)),
                'last': float(tick.get('last', 0)),
                'volume': float(tick.get('volume', 0)),
                'time': datetime.fromisoformat(tick['timestamp']),
            }
            
            symbol = tick.get('symbol', 'EURUSD')
            
            # Process through data engine
            await self.data_engine._on_tick(symbol, processed_tick)
            
            self.stats['total_ticks'] += 1
        
        except Exception as e:
            logger.error("tick_injection_error", error=str(e))
    
    def _print_backtest_summary(self):
        """Print backtest summary statistics."""
        print("\n" + "="*60)
        print("BACKTEST SUMMARY")
        print("="*60)
        print(f"Total Ticks: {self.stats['total_ticks']}")
        print(f"Predictions Generated: {self.stats['predictions']}")
        print(f"Trades Opened: {self.stats['trades_opened']}")
        print(f"Trades Closed: {self.stats['trades_closed']}")
        print(f"Total P&L: {self.stats['total_pnl']:.2f}")
        print(f"Accuracy: {self.stats['accuracy']:.2%}")
        print("="*60 + "\n")


async def run_backtest(data_file: str):
    """Run backtest on data file."""
    simulator = BacktestSimulator(data_file)
    await simulator.load_data()
    await simulator.run_backtest()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python backtest.py <data_file>")
        sys.exit(1)
    
    asyncio.run(run_backtest(sys.argv[1]))
