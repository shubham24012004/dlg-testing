import logging
import logging.config
import os
from pathlib import Path

_configured = False # Module-level flag to ensure one-time configuration

def setup_logging(log_dir: str = None, level: str = "INFO") -> None:
    global _configured

    if _configured:
        return
   
    if log_dir is None:
        log_dir = Path(__file__).parent.parent / "logs"
    
    os.makedirs(log_dir, exist_ok=True)
    
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                'format': '%(asctime)s | %(name)s | %(funcName)s | %(levelname)s | %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            }
        },

        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'INFO',
                'formatter': 'standard',
                'stream': 'ext://sys.stdout'
            },
            'file_app': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': level,
                'formatter': 'standard',
                'filename': os.path.join(log_dir, 'app.log'),
                'maxBytes': 5 * 1024 * 1024,
                'backupCount': 5,
                'encoding': 'utf-8'
            },
            'file_db': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'INFO',
                'formatter': 'standard',
                'filename': os.path.join(log_dir, 'db_activity.log'),
                'maxBytes': 5 * 1024 * 1024,
                'backupCount': 5,
                'encoding': 'utf-8'
            }
        },
        'loggers': {
            'dlg': {
                'handlers': ['console', 'file_app'],
                'level': level,
                'propagate': False
            },
            'dlg.db': {
                'handlers': ['file_db'],
                'level': 'INFO',
                'propagate': False
            }
        },

        'root': {
            'level': 'WARNING',
            'handlers': ['console']
        }
    })

    _configured = True

__all__ = ['setup_logging']