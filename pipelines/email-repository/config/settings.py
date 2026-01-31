"""
Configuration settings for Email Repository Pipeline.

Uses dataclasses for configuration and fetches secrets from Google Secret Manager.
"""

import os
import yaml
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

# Secret Manager cache to avoid repeated API calls
_secrets_cache: Dict[str, str] = {}


def get_secret(secret_name: str, project_id: Optional[str] = None) -> Optional[str]:
    """
    Fetch a secret from Google Secret Manager.

    Args:
        secret_name: Name of the secret (e.g., 'email-sync-service-account')
        project_id: GCP project ID. If None, uses GCP_PROJECT_ID env var.

    Returns:
        Secret value as string, or None if not found.
    """
    # Check cache first
    if secret_name in _secrets_cache:
        return _secrets_cache[secret_name]

    # Allow environment variable override for local development
    env_override = os.getenv(secret_name.upper().replace('-', '_'))
    if env_override:
        _secrets_cache[secret_name] = env_override
        return env_override

    try:
        from google.cloud import secretmanager

        project = project_id or os.getenv('GCP_PROJECT_ID', 'emailpilot-438321')
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project}/secrets/{secret_name}/versions/latest"

        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("UTF-8")

        _secrets_cache[secret_name] = secret_value
        logger.info(f"Loaded secret '{secret_name}' from Secret Manager")
        return secret_value

    except ImportError:
        logger.warning("google-cloud-secret-manager not installed, using environment variables only")
        return None
    except Exception as e:
        logger.warning(f"Could not fetch secret '{secret_name}' from Secret Manager: {e}")
        return None


@dataclass
class GmailConfig:
    """Gmail API configuration for domain-wide delegation."""
    service_account_json: Optional[str] = None
    delegated_email: Optional[str] = None
    scopes: List[str] = field(default_factory=lambda: [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.metadata'
    ])
    max_results_per_query: int = 500


@dataclass
class DriveConfig:
    """Google Drive API configuration for uploads."""
    service_account_json: Optional[str] = None
    scopes: List[str] = field(default_factory=lambda: [
        'https://www.googleapis.com/auth/drive.file'
    ])
    root_folder_id: Optional[str] = None  # Root folder for EmailScreenshots
    root_folder_name: str = "EmailScreenshots"


@dataclass
class VisionConfig:
    """Gemini Vision API configuration for email categorization."""
    api_key: Optional[str] = None
    model_name: str = "gemini-2.0-flash-lite"  # Cheapest model for cost efficiency
    max_concurrent_requests: int = 10
    temperature: float = 0.3
    max_output_tokens: int = 800


@dataclass
class ScreenshotConfig:
    """Screenshot generation configuration."""
    viewport_width: int = 800
    viewport_height: int = 1200
    format: str = "png"  # "png" or "jpeg"
    jpeg_quality: int = 85  # Only used if format is jpeg
    max_concurrent: int = 5
    timeout_ms: int = 30000


@dataclass
class SyncSettings:
    """Sync behavior settings."""
    incremental_sync_enabled: bool = True
    batch_size: int = 25
    max_emails_per_sync: int = 500
    date_range_start: Optional[str] = None  # ISO date, e.g., "2023-01-01"
    sender_blocklist: List[str] = field(default_factory=lambda: [
        "noreply@",
        "no-reply@",
        "mailer-daemon@",
        "postmaster@"
    ])
    subject_blocklist: List[str] = field(default_factory=lambda: [
        "Out of Office",
        "Delivery Status",
        "Undeliverable",
        "Auto-Reply"
    ])


@dataclass
class EmailAccountConfig:
    """Configuration for a single email account."""
    account_email: str
    account_name: str = ""
    enabled: bool = True
    date_range_start: Optional[str] = None
    sender_blocklist: List[str] = field(default_factory=list)
    subject_blocklist: List[str] = field(default_factory=list)


@dataclass
class PipelineConfig:
    """Main pipeline configuration."""
    gcp_project_id: str
    vertex_data_store_id: str
    gcp_location: str = "us"
    firestore_collection: str = "email_sync"
    gmail: GmailConfig = field(default_factory=GmailConfig)
    drive: DriveConfig = field(default_factory=DriveConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    screenshot: ScreenshotConfig = field(default_factory=ScreenshotConfig)
    sync: SyncSettings = field(default_factory=SyncSettings)


def load_email_accounts(config_path: Optional[str] = None) -> List[EmailAccountConfig]:
    """
    Load email account configurations from YAML file.

    Args:
        config_path: Path to email_accounts.yaml. If None, uses default location.

    Returns:
        List of EmailAccountConfig objects.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "email_accounts.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        logger.warning(f"Email accounts file not found: {config_path}")
        return []

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f) or {}

    accounts = []
    email_accounts_list = config.get('email_accounts') or []

    for account_data in email_accounts_list:
        if not account_data.get('enabled', True):
            continue

        sync_settings = account_data.get('sync_settings', {}) or {}

        accounts.append(EmailAccountConfig(
            account_email=account_data['account_email'],
            account_name=account_data.get('account_name', ''),
            enabled=True,
            date_range_start=sync_settings.get('date_range_start'),
            sender_blocklist=sync_settings.get('sender_blocklist', []),
            subject_blocklist=sync_settings.get('subject_blocklist', [])
        ))

    logger.info(f"Loaded {len(accounts)} email account(s) from configuration")
    return accounts


def get_pipeline_config() -> PipelineConfig:
    """
    Create pipeline configuration from environment variables and Secret Manager.

    Secrets (fetched from Google Secret Manager):
        EMAIL_SYNC_SERVICE_ACCOUNT_SECRET: Secret name for service account (default: email-sync-service-account)
        GEMINI_API_KEY_SECRET: Secret name for Gemini API key (default: gemini-rag-image-processing)

    Environment variables (optional overrides):
        GCP_PROJECT_ID: Google Cloud project ID
        VERTEX_DATA_STORE_ID: Vertex AI Search data store ID
        GCP_LOCATION: GCP region (default: us)
        EMAIL_SYNC_DELEGATED_EMAIL: Email address to impersonate (Google Groups/alias)
        DRIVE_SCREENSHOTS_ROOT_FOLDER_ID: Root Drive folder for screenshots
    """
    project_id = os.getenv('GCP_PROJECT_ID', 'emailpilot-438321')

    # Secret names (configurable via environment)
    email_sa_secret = os.getenv('EMAIL_SYNC_SERVICE_ACCOUNT_SECRET', 'email-sync-service-account')
    gemini_secret_name = os.getenv('GEMINI_API_KEY_SECRET', 'gemini-rag-image-processing')

    # Fetch Gmail service account credentials
    gmail_credentials = None
    if os.getenv('EMAIL_SYNC_SERVICE_ACCOUNT_JSON'):
        gmail_credentials = os.getenv('EMAIL_SYNC_SERVICE_ACCOUNT_JSON')
    elif os.getenv('EMAIL_SYNC_SERVICE_ACCOUNT_FILE'):
        sa_file_path = os.getenv('EMAIL_SYNC_SERVICE_ACCOUNT_FILE')
        if Path(sa_file_path).exists():
            with open(sa_file_path, 'r') as f:
                gmail_credentials = f.read()
            logger.info(f"Loaded email service account from file: {sa_file_path}")
    else:
        gmail_credentials = get_secret(email_sa_secret, project_id)

    # Fetch Gemini API key
    gemini_api_key = (
        os.getenv('GEMINI_API_KEY') or
        get_secret(gemini_secret_name, project_id)
    )

    # Drive credentials (can reuse Gmail service account or use separate)
    drive_credentials = gmail_credentials
    if os.getenv('DRIVE_SERVICE_ACCOUNT_JSON'):
        drive_credentials = os.getenv('DRIVE_SERVICE_ACCOUNT_JSON')

    gmail_config = GmailConfig(
        service_account_json=gmail_credentials,
        delegated_email=os.getenv('EMAIL_SYNC_DELEGATED_EMAIL'),
        max_results_per_query=int(os.getenv('EMAIL_SYNC_MAX_RESULTS', '500'))
    )

    drive_config = DriveConfig(
        service_account_json=drive_credentials,
        root_folder_id=os.getenv('DRIVE_SCREENSHOTS_ROOT_FOLDER_ID')
    )

    vision_config = VisionConfig(
        api_key=gemini_api_key,
        model_name=os.getenv('GEMINI_MODEL_NAME', 'gemini-2.0-flash-lite'),
        max_concurrent_requests=int(os.getenv('GEMINI_MAX_CONCURRENT', '10'))
    )

    screenshot_config = ScreenshotConfig(
        viewport_width=int(os.getenv('SCREENSHOT_VIEWPORT_WIDTH', '800')),
        viewport_height=int(os.getenv('SCREENSHOT_VIEWPORT_HEIGHT', '1200')),
        format=os.getenv('SCREENSHOT_FORMAT', 'png'),
        max_concurrent=int(os.getenv('SCREENSHOT_MAX_CONCURRENT', '5'))
    )

    sync_settings = SyncSettings(
        incremental_sync_enabled=os.getenv('EMAIL_SYNC_INCREMENTAL', 'true').lower() == 'true',
        batch_size=int(os.getenv('EMAIL_SYNC_BATCH_SIZE', '25')),
        max_emails_per_sync=int(os.getenv('EMAIL_SYNC_MAX_EMAILS', '500'))
    )

    return PipelineConfig(
        gcp_project_id=project_id,
        vertex_data_store_id=os.getenv('VERTEX_DATA_STORE_ID', 'emailpilot-rag_1765205761919'),
        gcp_location=os.getenv('GCP_LOCATION', 'us'),
        firestore_collection=os.getenv('EMAIL_SYNC_FIRESTORE_COLLECTION', 'email_sync'),
        gmail=gmail_config,
        drive=drive_config,
        vision=vision_config,
        screenshot=screenshot_config,
        sync=sync_settings
    )


def save_email_accounts(
    accounts: List[EmailAccountConfig],
    config_path: Optional[str] = None
) -> bool:
    """
    Save email account configurations to YAML file.

    Args:
        accounts: List of EmailAccountConfig objects
        config_path: Path to save to. If None, uses default location.

    Returns:
        True if save successful, False otherwise.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "email_accounts.yaml"
    else:
        config_path = Path(config_path)

    config: Dict[str, Any] = {
        'email_accounts': [],
        'sync_settings': {
            'incremental_sync_enabled': True,
            'batch_size': 25,
            'screenshot_format': 'png',
            'max_emails_per_sync': 500
        }
    }

    for account in accounts:
        account_data: Dict[str, Any] = {
            'account_email': account.account_email,
            'account_name': account.account_name,
            'enabled': account.enabled
        }

        sync_settings: Dict[str, Any] = {}
        if account.date_range_start:
            sync_settings['date_range_start'] = account.date_range_start
        if account.sender_blocklist:
            sync_settings['sender_blocklist'] = account.sender_blocklist
        if account.subject_blocklist:
            sync_settings['subject_blocklist'] = account.subject_blocklist

        if sync_settings:
            account_data['sync_settings'] = sync_settings

        config['email_accounts'].append(account_data)

    try:
        with open(config_path, 'w') as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
        logger.info(f"Saved email accounts to {config_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save email accounts: {e}")
        return False
