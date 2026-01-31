"""
Configuration settings for Image Repository Pipeline.

Uses Pydantic for validation and environment variable support.
Fetches secrets from Google Secret Manager.
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
        secret_name: Name of the secret (e.g., 'emailpilot-gemini-api-key')
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
class DriveConfig:
    """Google Drive API configuration."""
    service_account_json: Optional[str] = None
    scopes: List[str] = field(default_factory=lambda: [
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/drive.metadata.readonly'
    ])
    page_size: int = 100  # Files per API request
    max_file_size_mb: int = 50  # Skip files larger than this


@dataclass
class VisionConfig:
    """Gemini Vision API configuration."""
    api_key: Optional[str] = None
    model_name: str = "gemini-2.0-flash-lite"  # Fast/cheap model for image captioning
    max_concurrent_requests: int = 10
    temperature: float = 0.3
    max_output_tokens: int = 500


@dataclass
class SyncSettings:
    """Sync behavior settings."""
    incremental_sync_enabled: bool = True
    full_resync_interval_days: int = 30
    batch_size: int = 50
    supported_formats: List[str] = field(default_factory=lambda: [
        'image/jpeg', 'image/png', 'image/webp', 'image/gif'
    ])
    skip_folders: List[str] = field(default_factory=lambda: [
        'Archive', 'DO NOT USE', 'Deprecated', 'Old', 'Backup'
    ])


@dataclass
class ClientFolderMapping:
    """Maps a client to their Drive folders."""
    client_id: str
    folder_id: str
    folder_name: str = ""
    folder_type: str = "client"  # "client" or "shared"
    enabled: bool = True


@dataclass
class PipelineConfig:
    """Main pipeline configuration."""
    gcp_project_id: str
    vertex_data_store_id: str
    gcp_location: str = "us"
    firestore_collection: str = "image_sync_state"
    drive: DriveConfig = field(default_factory=DriveConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    sync: SyncSettings = field(default_factory=SyncSettings)


def load_folder_mappings(config_path: Optional[str] = None) -> Dict[str, List[ClientFolderMapping]]:
    """
    Load client folder mappings from YAML configuration file.

    Args:
        config_path: Path to folder_mappings.yaml. If None, uses default location.

    Returns:
        Dictionary mapping client_id to list of ClientFolderMapping objects.
        Shared folders are added to each client.
    """
    if config_path is None:
        # Default to config directory relative to this file
        config_path = Path(__file__).parent / "folder_mappings.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        logger.warning(f"Folder mappings file not found: {config_path}")
        return {}

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f) or {}

    mappings: Dict[str, List[ClientFolderMapping]] = {}

    # Parse shared folders (apply to all clients)
    shared_folders = []
    shared_folder_list = config.get('shared_folders') or []
    for folder in shared_folder_list:
        if folder and folder.get('enabled', True):
            shared_folders.append(ClientFolderMapping(
                client_id="shared",
                folder_id=folder['folder_id'],
                folder_name=folder.get('name', ''),
                folder_type="shared",
                enabled=True
            ))

    # Parse per-client folders
    client_folder_list = config.get('client_folders') or []
    for client_config in client_folder_list:
        client_id = client_config['client_id']
        client_mappings = []

        for folder in client_config.get('folders', []):
            if folder.get('enabled', True):
                client_mappings.append(ClientFolderMapping(
                    client_id=client_id,
                    folder_id=folder['folder_id'],
                    folder_name=folder.get('name', ''),
                    folder_type="client",
                    enabled=True
                ))

        # Add shared folders to each client's mappings
        mappings[client_id] = client_mappings + shared_folders

    # Also store shared mappings separately for reference
    if shared_folders:
        mappings['_shared'] = shared_folders

    logger.info(f"Loaded folder mappings for {len(mappings)} clients")
    return mappings


def get_pipeline_config() -> PipelineConfig:
    """
    Create pipeline configuration from environment variables and Secret Manager.

    Secrets (fetched from Google Secret Manager):
        GEMINI_API_KEY_SECRET: Secret name for Gemini API key (default: gemini-rag-image-processing)
        IMAGE_SYNC_SERVICE_ACCOUNT_SECRET: Secret name for service account (default: rag-service-account)

    Environment variables (optional overrides):
        GCP_PROJECT_ID: Google Cloud project ID
        VERTEX_DATA_STORE_ID: Vertex AI Search data store ID
        GCP_LOCATION: GCP region (default: us)
        GEMINI_API_KEY: Direct override for Gemini API key (bypasses Secret Manager)
        IMAGE_SYNC_SERVICE_ACCOUNT_JSON: Direct override for service account JSON
    """
    project_id = os.getenv('GCP_PROJECT_ID', 'emailpilot-438321')

    # Secret names (configurable via environment)
    gemini_secret_name = os.getenv('GEMINI_API_KEY_SECRET', 'gemini-rag-image-processing')
    service_account_secret_name = os.getenv('IMAGE_SYNC_SERVICE_ACCOUNT_SECRET', 'rag-service-account')

    # Fetch Gemini API key from Secret Manager (with env var fallback)
    gemini_api_key = (
        os.getenv('GEMINI_API_KEY') or
        get_secret(gemini_secret_name, project_id)
    )

    # Fetch Google credentials from Secret Manager (with env var/file fallback)
    google_credentials = None

    # Option 1: Direct JSON string in env var
    if os.getenv('IMAGE_SYNC_SERVICE_ACCOUNT_JSON'):
        google_credentials = os.getenv('IMAGE_SYNC_SERVICE_ACCOUNT_JSON')
    # Option 2: Path to JSON file
    elif os.getenv('IMAGE_SYNC_SERVICE_ACCOUNT_FILE'):
        sa_file_path = os.getenv('IMAGE_SYNC_SERVICE_ACCOUNT_FILE')
        if Path(sa_file_path).exists():
            with open(sa_file_path, 'r') as f:
                google_credentials = f.read()
            logger.info(f"Loaded service account from file: {sa_file_path}")
    # Option 3: Legacy env var
    elif os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON'):
        google_credentials = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    # Option 4: Secret Manager
    else:
        google_credentials = get_secret(service_account_secret_name, project_id)

    drive_config = DriveConfig(
        service_account_json=google_credentials,
        max_file_size_mb=int(os.getenv('IMAGE_SYNC_MAX_FILE_SIZE_MB', '50'))
    )

    vision_config = VisionConfig(
        api_key=gemini_api_key,
        model_name=os.getenv('GEMINI_MODEL_NAME', 'gemini-2.0-flash-lite'),
        max_concurrent_requests=int(os.getenv('GEMINI_MAX_CONCURRENT', '10'))
    )

    sync_settings = SyncSettings(
        incremental_sync_enabled=os.getenv('IMAGE_SYNC_INCREMENTAL', 'true').lower() == 'true',
        batch_size=int(os.getenv('IMAGE_SYNC_BATCH_SIZE', '50'))
    )

    return PipelineConfig(
        gcp_project_id=project_id,
        vertex_data_store_id=os.getenv('VERTEX_DATA_STORE_ID', 'emailpilot-rag_1765205761919'),
        gcp_location=os.getenv('GCP_LOCATION', 'us'),
        firestore_collection=os.getenv('IMAGE_SYNC_FIRESTORE_COLLECTION', 'image_sync_state'),
        drive=drive_config,
        vision=vision_config,
        sync=sync_settings
    )


def save_folder_mappings(
    mappings: Dict[str, List[ClientFolderMapping]],
    config_path: Optional[str] = None
) -> bool:
    """
    Save folder mappings to YAML configuration file.

    Args:
        mappings: Dictionary of client_id to folder mappings
        config_path: Path to save to. If None, uses default location.

    Returns:
        True if save successful, False otherwise.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "folder_mappings.yaml"
    else:
        config_path = Path(config_path)

    # Build YAML structure
    config: Dict[str, Any] = {
        'shared_folders': [],
        'client_folders': [],
        'sync_settings': {
            'incremental_sync_enabled': True,
            'max_file_size_mb': 50,
            'skip_folders': ['Archive', 'DO NOT USE', 'Deprecated']
        }
    }

    # Extract shared folders
    if '_shared' in mappings:
        for mapping in mappings['_shared']:
            config['shared_folders'].append({
                'folder_id': mapping.folder_id,
                'name': mapping.folder_name,
                'enabled': mapping.enabled
            })

    # Extract per-client folders
    for client_id, client_mappings in mappings.items():
        if client_id.startswith('_'):
            continue

        client_folders = []
        for mapping in client_mappings:
            if mapping.folder_type == 'client':
                client_folders.append({
                    'folder_id': mapping.folder_id,
                    'name': mapping.folder_name,
                    'enabled': mapping.enabled
                })

        if client_folders:
            config['client_folders'].append({
                'client_id': client_id,
                'client_name': client_id.replace('-', ' ').title(),
                'folders': client_folders
            })

    try:
        with open(config_path, 'w') as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
        logger.info(f"Saved folder mappings to {config_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save folder mappings: {e}")
        return False
