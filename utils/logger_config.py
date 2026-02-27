import logging
import os
from dotenv import load_dotenv

load_dotenv()

def logger_method(name):
    if os.getenv("environment") == 'dev':
        # Create and configure logger
        logging.basicConfig(filename="logger.log",
                            level=logging.DEBUG,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            filemode='w')
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(name)
    return logger
