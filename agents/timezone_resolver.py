from datetime import datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo
import re

# Comprehensive lookup table for cities and countries
LOCATION_TIMEZONE_MAP = {
    # Japan
    "japan": "Asia/Tokyo",
    "tokyo": "Asia/Tokyo",
    "osaka": "Asia/Tokyo",
    "yokohama": "Asia/Tokyo",
    "fukuoka": "Asia/Tokyo",

    # Singapore
    "singapore": "Asia/Singapore",

    # Indonesia
    "indonesia": "Asia/Jakarta",
    "jakarta": "Asia/Jakarta",
    "bandung": "Asia/Jakarta",
    "surabaya": "Asia/Jakarta",
    "bali": "Asia/Makassar",

    # United States & Canada
    "united states": "America/New_York",
    "usa": "America/New_York",
    "us": "America/New_York",
    "new york": "America/New_York",
    "san francisco": "America/Los_Angeles",
    "los angeles": "America/Los_Angeles",
    "california": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "washington": "America/New_York",
    "texas": "America/Chicago",
    "dallas": "America/Chicago",
    "austin": "America/Chicago",
    "chicago": "America/Chicago",
    "toronto": "America/Toronto",
    "canada": "America/Toronto",
    "vancouver": "America/Vancouver",

    # United Kingdom & Europe
    "united kingdom": "Europe/London",
    "uk": "Europe/London",
    "london": "Europe/London",
    "germany": "Europe/Berlin",
    "berlin": "Europe/Berlin",
    "munich": "Europe/Berlin",
    "frankfurt": "Europe/Berlin",
    "netherlands": "Europe/Amsterdam",
    "amsterdam": "Europe/Amsterdam",
    "france": "Europe/Paris",
    "paris": "Europe/Paris",
    "ireland": "Europe/Dublin",
    "dublin": "Europe/Dublin",
    "sweden": "Europe/Stockholm",
    "stockholm": "Europe/Stockholm",

    # Australia & NZ
    "australia": "Australia/Sydney",
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "new zealand": "Pacific/Auckland",
    "auckland": "Pacific/Auckland",
}

def resolve_timezone(location_str: str) -> str:
    """
    Resolves a location string to an IANA timezone identifier.
    Defaults to 'Asia/Tokyo' if unknown.
    """
    if not location_str:
        return "Asia/Tokyo"
        
    normalized = location_str.lower().strip()
    # Check exact and substring matches
    for key, tz in LOCATION_TIMEZONE_MAP.items():
        if re.search(r'\b' + re.escape(key) + r'\b', normalized):
            return tz

    # Default fallback
    return "Asia/Tokyo"

def calculate_target_utc(iana_timezone: str, target_hour: int = 9) -> datetime:
    """
    Calculates the exact UTC datetime for target_hour:00 local time.
    If 09:00 AM in the target timezone has already passed today, targets tomorrow 09:00 AM.
    """
    try:
        tz = ZoneInfo(iana_timezone)
    except Exception:
        tz = ZoneInfo("Asia/Tokyo")

    now_target = datetime.now(tz)
    target_today = datetime.combine(now_target.date(), time(target_hour, 0, 0), tzinfo=tz)

    if now_target >= target_today:
        target_time = target_today + timedelta(days=1)
    else:
        target_time = target_today

    return target_time.astimezone(timezone.utc)
