import logging, os, io
from datetime import datetime

_log_name      = "manufacturing_logger"
_configured    = False           # ➊ idempotency flag
_log_stream    = None            # ➋ only used in cloud mode

def init_logger(local_flag: bool = True):
    """Attach ONE handler to the named logger. Safe to call many times."""
    global _configured, _log_stream

    if _configured:              # already done – no duplicate handlers 👍
        return logging.getLogger(_log_name)

    logger = logging.getLogger(_log_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False     # don’t double-log through root

    # ------------------------------------------------------------------
    date_string = datetime.today().strftime("%Y%m%d")
    fmt = logging.Formatter(
        "%(asctime)s  |  %(levelname)-8s |  %(module)s:%(lineno)d  |  %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    if local_flag:                               # ------ local file
        log_dir  = f"./Logs/{date_string}"
        os.makedirs(log_dir, exist_ok=True)
        file_h  = logging.FileHandler(f"{log_dir}/ManufacturingLog.txt",
                                      mode="a",
                                      encoding="utf-8",
                                      errors="replace",         # never crash on exotic chars
        )
        file_h.setFormatter(fmt)
        logger.addHandler(file_h)

    else:                                        # ------ Stream → memory
        _log_stream = io.StringIO()
        str_h       = logging.StreamHandler(_log_stream)
        str_h.setFormatter(fmt)
        logger.addHandler(str_h)

    _configured = True
    logger.info("Logger initialised (local=%s).", local_flag)
    return logger


# Helper that scripts can import directly
def get_logger():
    if not _configured:               # safety-net if someone forgot init_logger()
        init_logger(True)
    return logging.getLogger(_log_name)


def get_log_stream():
    return _log_stream

def upload_log_to_gcs(log_content, gcs_module, log_file_path=None):
    # Use today's date for directory
    date_string = datetime.today().strftime('%Y%m%d')
    if log_file_path is None:
        cloud_logger_directory = f'Logs/{date_string}'
        blob_name = f"{cloud_logger_directory}/ManufacturingLog.txt"
    else:
        blob_name = log_file_path

    try:
        bucket = gcs_module._get_bucket()
        blob = bucket.blob(blob_name)

        # Append to old log if present
        if blob.exists():
            existing_log = blob.download_as_text()
            combined_log = existing_log + log_content
        else:
            combined_log = log_content
        blob.upload_from_string(combined_log)
        logging.info(f"Log content uploaded to GCS at {blob_name}")
    except Exception as e:
        logging.error(f"Error uploading log to GCS: {e}")
