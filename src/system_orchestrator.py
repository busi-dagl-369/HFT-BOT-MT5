"""
System integration orchestrator.
Coordinates all five tiers and messaging infrastructure.
"""

import asyncio
from typing import Optional
import structlog

from .config import setup_logging, get_config
from .tier_01_data_engine import DataEngine
from .tier_02_prediction_engine import PredictionEngine
from .tier_03_trade_planner import TradePlanner
from .tier_05_exit_manager import RatchetExitManager


logger = structlog.get_logger(__name__)


class TradingSystem:
    """
    Orchestrates all tiers of the trading system.
    Manages initialization, execution, and graceful shutdown.
    """
    
    def __init__(self):
        """Initialize trading system."""
        self.config = get_config()
        
        # Initialize tiers
        self.data_engine: Optional[DataEngine] = None
        self.prediction_engine: Optional[PredictionEngine] = None
        self.trade_planner: Optional[TradePlanner] = None
        self.exit_manager: Optional[RatchetExitManager] = None
        
        # Tier tasks
        self.tier_tasks = []
        
        logger.info("trading_system_initialized", environment=self.config.environment)
    
    async def initialize(self):
        """Initialize all system tiers."""
        try:
            logger.info("trading_system_initialization_started")
            
            # Initialize Tier 01: Data Engine
            logger.info("initializing_tier_01_data_engine")
            self.data_engine = DataEngine()
            await self.data_engine.initialize()
            logger.info("tier_01_initialized")
            
            # Initialize Tier 02: Prediction Engine
            logger.info("initializing_tier_02_prediction_engine")
            self.prediction_engine = PredictionEngine()
            await self.prediction_engine.initialize()
            logger.info("tier_02_initialized")
            
            # Initialize Tier 03: Trade Planner
            logger.info("initializing_tier_03_trade_planner")
            self.trade_planner = TradePlanner()
            await self.trade_planner.initialize()
            logger.info("tier_03_initialized")
            
            # Tier 04: MT5 Execution Engine
            # Note: Tier 04 is an MT5 EA, runs in MT5 terminal
            logger.info("tier_04_mt5_ea_must_be_loaded_in_terminal")
            
            # Initialize Tier 05: Ratchet Exit Manager
            logger.info("initializing_tier_05_ratchet_exit_manager")
            self.exit_manager = RatchetExitManager()
            await self.exit_manager.initialize()
            logger.info("tier_05_initialized")
            
            logger.info("trading_system_fully_initialized")
        
        except Exception as e:
            logger.error("system_initialization_error", error=str(e))
            await self.shutdown()
            raise
    
    async def run(self):
        """Run all tiers concurrently."""
        try:
            logger.info("trading_system_starting_execution")
            
            # Create tasks for each tier
            self.tier_tasks = [
                asyncio.create_task(self.data_engine.run()),
                asyncio.create_task(self.prediction_engine.run()),
                asyncio.create_task(self.trade_planner.run()),
                asyncio.create_task(self.exit_manager.run()),
            ]
            
            # Wait for all tasks
            await asyncio.gather(*self.tier_tasks, return_exceptions=True)
        
        except Exception as e:
            logger.error("system_run_error", error=str(e))
            await self.shutdown()
    
    async def shutdown(self):
        """Gracefully shutdown all tiers."""
        try:
            logger.info("trading_system_shutdown_initiated")
            
            # Stop all tiers
            if self.data_engine:
                await self.data_engine.stop()
            
            if self.prediction_engine:
                await self.prediction_engine.stop()
            
            if self.trade_planner:
                await self.trade_planner.stop()
            
            if self.exit_manager:
                await self.exit_manager.stop()
            
            # Cancel remaining tasks
            for task in self.tier_tasks:
                if not task.done():
                    task.cancel()
            
            logger.info("trading_system_shutdown_complete")
        
        except Exception as e:
            logger.error("system_shutdown_error", error=str(e))


async def main():
    """Main entry point for trading system."""
    # Setup logging
    setup_logging(
        log_level=get_config().log_level,
        log_format=get_config().log_format,
        log_dir=get_config().structured_logs_dir,
        component="hft_bot_trading_system",
    )
    
    logger.info("===== HFT-BOT Trading System Starting =====")
    
    # Create and run system
    system = TradingSystem()
    
    try:
        await system.initialize()
        await system.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await system.shutdown()
    except Exception as e:
        logger.error("fatal_error", error=str(e))
        await system.shutdown()
        raise


if __name__ == "__main__":
    asyncio.run(main())
