#!/usr/bin/env python3
"""
Main entry point for HFT-BOT Trading System.
Starts all Python tiers (01, 02, 03, 05) and coordinates with MT5 EA (tier 04).
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.system_orchestrator import main
from src.logging_utils import setup_logging
from src.config import get_config


if __name__ == "__main__":
    asyncio.run(main())
