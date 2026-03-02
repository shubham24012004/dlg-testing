import logging
import os
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

load_dotenv()

def logger_method(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    if logger.hasHandlers():
        logger.handlers.clear()
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if os.getenv("environment") == 'dev':
        # Create and configure logger
        handler = RotatingFileHandler('logger.log', maxBytes=1*1024*1024, backupCount=5)
        handler.setLevel(logging.DEBUG)
    else:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger
