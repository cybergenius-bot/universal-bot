# logger_config.py

import logging
from logging.handlers import RotatingFileHandler
import sys

LOG_FORMAT = "%(asctime)s - [%(levelname)s] - %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s"
LOG_LEVEL = logging.INFO
LOG_FILE = "logs/bot.log"
MAX_BYTES = 1 * 1024 * 1024  # 1MB
BACKUP_COUNT = 5

def setup_logger(name: str = None) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)

    if not logger.handlers:
        formatter = logging.Formatter(LOG_FORMAT)

        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.WARNING)  # файл только WARNING+

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(logging.INFO)  # консоль INFO+

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

        logger.propagate = False  # отключаем повторную отправку наверх

    return logger
