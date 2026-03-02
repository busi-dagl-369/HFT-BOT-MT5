"""
Structured logging infrastructure for the trading system.
Provides JSON-based structured logging with context preservation.
"""

import structlog
import logging
import logging.handlers
from pathlib import Path
from pythonjsonlogger import jsonlogger


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    log_dir: str = "./logs",
    component: str = "trading_system",
):
    """
    Setup structured logging for the trading system.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: "json" or "console"
        log_dir: Directory for log files
        component: Component name for tagging
    """
    
    # Create log directory
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    # Configure standard logging
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # File handler with JSON formatter
    file_handler = logging.handlers.RotatingFileHandler(
        f"{log_dir}/{component}.log",
        maxBytes=100 * 1024 * 1024,  # 100 MB
        backupCount=5,
    )
    
    if log_format == "json":
        formatter = jsonlogger.JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    if log_format == "json":
        console_formatter = jsonlogger.JsonFormatter()
    else:
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    logger = structlog.get_logger(__name__)
    logger.info("logging_configured", log_level=log_level, format=log_format)
    
    return logger


def get_logger(name: str = __name__):
    """Get a structlog logger instance."""
    return structlog.get_logger(name)
