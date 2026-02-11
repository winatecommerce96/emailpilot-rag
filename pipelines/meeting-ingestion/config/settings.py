import os
from typing import List

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings

class MeetingPipelineSettings(BaseSettings):
    # OAuth Scopes
    SCOPES: List[str] = [
        'https://www.googleapis.com/auth/calendar.events.readonly',
        'https://www.googleapis.com/auth/drive.readonly', # For transcripts/recordings
        'https://www.googleapis.com/auth/userinfo.email' # To identify the user
    ]

    # Callback URL - auto-detect local vs production
    # Cloud Run sets ENVIRONMENT=production (not ENV)
    REDIRECT_URI: str = os.getenv(
        "MEETING_OAUTH_REDIRECT_URI",
        "https://rag.emailpilot.ai/api/meeting/callback"
        if os.getenv("ENVIRONMENT", "development") == "production"
        else "http://localhost:8003/api/meeting/callback"
    )

    # Scanning Configuration
    LOOKBACK_HOURS: int = 24  # Default for manual scans
    INITIAL_SCAN_DAYS: int = 60  # 60-day lookback for new user signup
    WEEKLY_SCAN_DAYS: int = 7  # Weekly scheduled scans

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra env vars from .env file

settings = MeetingPipelineSettings()
