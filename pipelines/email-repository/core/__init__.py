"""Core module for Email Repository Pipeline."""

from .gmail_client import GmailClient, EmailMessage
from .screenshot_service import EmailScreenshotService
from .drive_uploader import DriveUploader
from .categorizer import EmailCategorizer
from .state_manager import EmailSyncStateManager
from .vertex_ingestion import EmailVertexIngestion
from .sync_orchestrator import EmailSyncOrchestrator

__all__ = [
    "GmailClient",
    "EmailMessage",
    "EmailScreenshotService",
    "DriveUploader",
    "EmailCategorizer",
    "EmailSyncStateManager",
    "EmailVertexIngestion",
    "EmailSyncOrchestrator",
]
