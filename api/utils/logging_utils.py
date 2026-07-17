import logging
import os
from datetime import datetime


def setup_logging():
    """Configure date-based file and console logging."""
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    current_date = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"app_{current_date}.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

    noisy_loggers = [
        "opensearch",
        "opensearchpy",
        "urllib3.connectionpool",
        "botocore",
        "boto3",
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.info("Logging initialized successfully.")
