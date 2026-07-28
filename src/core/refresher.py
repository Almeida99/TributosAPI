import logging

logger = logging.getLogger(__name__)

_refresh_fn = None

def set_refresher(fn):
    global _refresh_fn
    _refresh_fn = fn
    logger.info("Refresher function set.")

def trigger_refresh():
    if _refresh_fn:
        logger.info("Triggering dynamic route refresh...")
        try:
            _refresh_fn()
        except Exception as e:
            logger.error(f"Error during refresh: {e}")
    else:
        logger.warning("Refresher function not set, skip refresh.")
