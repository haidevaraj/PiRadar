import logging
import time
from pathlib import Path
import requests

logger = logging.getLogger(__name__)

def check_and_update_routes(routes_path: Path) -> None:
    """
    Checks if the airline_routes.json file exists and is less than a week old.
    If not, pulls the latest version from the Jonty/airline-route-data repository.
    """
    url = "https://raw.githubusercontent.com/Jonty/airline-route-data/main/airline_routes.json"
    one_week_seconds = 7 * 24 * 60 * 60
    
    should_download = False
    
    if not routes_path.exists():
        logger.info("Static airline routes file missing at %s. Downloading...", routes_path)
        should_download = True
    else:
        file_age = time.time() - routes_path.stat().st_mtime
        if file_age > one_week_seconds:
            logger.info("Static airline routes file is older than one week. Refreshing...")
            should_download = True
            
    if should_download:
        try:
            # Ensure the directory exists
            routes_path.parent.mkdir(parents=True, exist_ok=True)
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            with open(routes_path, "wb") as f:
                f.write(response.content)
            logger.info("✓ Successfully updated airline_routes.json from GitHub.")
        except Exception as exc:
            logger.error("Failed to update airline routes from GitHub: %s. Using existing data if available.", exc)