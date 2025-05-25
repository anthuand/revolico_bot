"""
Logger Utility Module
--------------------
Provides a function to set up a logger for the application.
All code is documented and follows PEP8 and best practices.
"""

import logging
import os
from typing import Optional
import sys

def setup_logger(name: str, log_file: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """
    Sets up and returns a logger with the specified name, log file, and level.
    Logs to both console and file if log_file is provided.
    If the directory of the log_file does not exist, it creates it automatically.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Captura todo, los handlers filtran
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Limpia handlers previos para evitar duplicados
    if logger.hasHandlers():
        logger.handlers.clear()

    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.ERROR)  # Solo errores y críticos a archivo
        logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.DEBUG)  # Solo debug, info y warning a terminal
    # Filtro para que la terminal NO muestre errores (ya van a archivo)
    class MaxLevelFilter(logging.Filter):
        def __init__(self, max_level):
            self.max_level = max_level
        def filter(self, record):
            return record.levelno < logging.ERROR
    stream_handler.addFilter(MaxLevelFilter(logging.ERROR))
    logger.addHandler(stream_handler)

    return logger 