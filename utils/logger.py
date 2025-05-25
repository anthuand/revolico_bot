"""
Logger Utility Module
--------------------
Provides a function to set up a logger for the application.
All code is documented and follows PEP8 and best practices.
"""

import logging
import os
from typing import Optional

def setup_logger(name: str, log_file: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """
    Sets up and returns a logger with the specified name, log file, and level.
    Logs to both console and file if log_file is provided.
    If the directory of the log_file does not exist, it creates it automatically.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Evita agregar múltiples handlers en ejecuciones repetidas
    if not logger.hasHandlers():
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger 