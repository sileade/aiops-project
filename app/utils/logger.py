"""
Модуль логирования для AIOps системы
"""
import logging
import sys
from config.settings import settings

def setup_logger(name: str) -> logging.Logger:
    """Настройка логгера для модуля"""
    logger = logging.getLogger(name)
    logger.setLevel(settings.log_level)
    
    # Формат логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Handler для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler для файла
    file_handler = logging.FileHandler('/app/data/logs/aiops.log')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger("aiops")
