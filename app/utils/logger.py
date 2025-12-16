"""
Модуль логирования для AIOps системы
"""
import logging
import sys
import os
from config.settings import settings


def setup_logger(name: str) -> logging.Logger:
    """Настройка логгера для модуля"""
    logger = logging.getLogger(name)
    logger.setLevel(settings.log_level)
    
    # Проверяем, не добавлены ли уже handlers
    if logger.handlers:
        return logger
    
    # Формат логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Handler для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler для файла (с проверкой существования директории)
    log_dir = os.getenv("LOG_DIR", "/app/data/logs")
    
    # Пробуем создать директорию, если её нет
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "aiops.log")
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (PermissionError, OSError) as e:
        # Если не удалось создать файл, логируем только в консоль
        logger.warning(f"Не удалось создать файл логов: {e}. Логирование только в консоль.")
    
    return logger


logger = setup_logger("aiops")
