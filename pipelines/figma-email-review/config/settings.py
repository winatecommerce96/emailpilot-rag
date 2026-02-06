"""
Configuration settings for Figma Email Review Pipeline.

Uses dataclasses for validation and environment variable support.
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
        secret_name: Name of the secret (e.g., 'figma-access-token')
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
class FigmaConfig:
    """Figma API configuration."""
    access_token: Optional[str] = None
    api_base_url: str = "https://api.figma.com/v1"
    max_concurrent_requests: int = 5
    timeout_seconds: int = 30
    image_scale: float = 2.0  # Scale for exporting frames as images
    image_format: str = "png"  # png, jpg, svg, pdf


@dataclass
class VisionConfig:
    """Gemini Vision API configuration."""
    api_key: Optional[str] = None
    model_name: str = "gemini-2.0-flash-lite"
    temperature: float = 0.3
    max_output_tokens: int = 2000  # Higher for detailed email analysis
    max_concurrent_requests: int = 5


@dataclass
class RAGConfig:
    """RAG service integration configuration."""
    base_url: str = "https://rag-service-p3cxgvcsla-uc.a.run.app"
    timeout_seconds: int = 30
    default_k: int = 5  # Number of results per query


@dataclass
class AsanaConfig:
    """Asana integration configuration."""
    # Custom field GIDs for identification
    messaging_stage_gid: Optional[str] = None  # GID of "Messaging Stage" field
    figma_url_gid: Optional[str] = None  # GID of "Figma URL" field
    client_field_gid: Optional[str] = None  # GID of "Client" field

    # Trigger value
    trigger_stage_value: str = "AI Email Review"

    # API configuration for posting results
    orchestrator_url: str = "https://app.emailpilot.ai"
    post_results_enabled: bool = True


@dataclass
class BestPracticesConfig:
    """Email best practices thresholds."""
    # Subject line
    subject_line_min_length: int = 20
    subject_line_max_length: int = 60
    subject_spam_triggers: List[str] = field(default_factory=lambda: [
        'FREE', 'URGENT', 'ACT NOW', 'LIMITED TIME', 'CLICK HERE',
        'BUY NOW', 'ORDER NOW', 'WINNER', 'CONGRATULATIONS'
    ])

    # CTA
    cta_required: bool = True
    min_cta_visibility_score: float = 0.7

    # Layout
    max_image_ratio: float = 0.6  # Max 60% images
    min_text_ratio: float = 0.3  # Min 30% text

    # Accessibility
    min_contrast_score: float = 0.7
    min_font_size_body: int = 14  # pixels
    min_font_size_cta: int = 16  # pixels

    # Mobile
    max_width_desktop: int = 640  # pixels
    min_button_height: int = 44  # pixels for touch targets


@dataclass
class ClientFigmaMapping:
    """Maps a client to their Figma files (optional fallback)."""
    client_id: str
    figma_file_key: str
    figma_project_id: Optional[str] = None
    page_ids: List[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class PipelineConfig:
    """Main pipeline configuration."""
    gcp_project_id: str
    vertex_data_store_id: str
    gcp_location: str = "us"
    firestore_collection: str = "figma_review_state"

    # Sub-configurations
    figma: FigmaConfig = field(default_factory=FigmaConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    asana: AsanaConfig = field(default_factory=AsanaConfig)
    best_practices: BestPracticesConfig = field(default_factory=BestPracticesConfig)


def parse_figma_url(figma_url: str) -> Dict[str, Optional[str]]:
    """
    Parse a Figma URL to extract file_key and optional node_id.

    Examples:
        https://www.figma.com/file/ABC123/Design-Name → {"file_key": "ABC123", "node_id": None}
        https://www.figma.com/file/ABC123/Design-Name?node-id=0:123 → {"file_key": "ABC123", "node_id": "0:123"}
        https://www.figma.com/design/ABC123/Design-Name → {"file_key": "ABC123", "node_id": None}

    Args:
        figma_url: Figma URL to parse

    Returns:
        Dictionary with file_key and optional node_id
    """
    import re
    from urllib.parse import urlparse, parse_qs

    result = {"file_key": None, "node_id": None}

    if not figma_url:
        return result

    # Parse URL
    parsed = urlparse(figma_url)

    # Extract file key from path
    # Matches /file/KEY/... or /design/KEY/... or /proto/KEY/...
    path_match = re.match(r'^/(file|design|proto)/([a-zA-Z0-9]+)', parsed.path)
    if path_match:
        result["file_key"] = path_match.group(2)

    # Extract node-id from query params
    query_params = parse_qs(parsed.query)
    node_id = None
    if 'node-id' in query_params:
        node_id = query_params['node-id'][0]
    elif 'starting-point-node-id' in query_params:
        node_id = query_params['starting-point-node-id'][0]

    if node_id:
        # Figma uses URL-encoded node IDs like "0%3A123" for "0:123"
        normalized = node_id.replace('%3A', ':')
        if ':' not in normalized and '-' in normalized:
            normalized = normalized.replace('-', ':', 1)
        result["node_id"] = normalized

    return result


def load_client_mappings(config_path: Optional[str] = None) -> Dict[str, List[ClientFigmaMapping]]:
    """
    Load client Figma mappings from YAML configuration file (optional fallback).

    This is optional since the primary trigger is from Asana with the Figma URL.

    Args:
        config_path: Path to client_mappings.yaml. If None, uses default location.

    Returns:
        Dictionary mapping client_id to list of ClientFigmaMapping objects.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "client_mappings.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        logger.info(f"Client mappings file not found: {config_path} (using Asana trigger)")
        return {}

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f) or {}

    mappings: Dict[str, List[ClientFigmaMapping]] = {}

    client_files = config.get('client_files') or []
    for client_config in client_files:
        client_id = client_config['client_id']

        if client_config.get('enabled', True):
            mapping = ClientFigmaMapping(
                client_id=client_id,
                figma_file_key=client_config['figma_file_key'],
                figma_project_id=client_config.get('figma_project_id'),
                page_ids=client_config.get('page_ids', []),
                enabled=True
            )

            if client_id not in mappings:
                mappings[client_id] = []
            mappings[client_id].append(mapping)

    logger.info(f"Loaded Figma mappings for {len(mappings)} clients")
    return mappings


def get_pipeline_config() -> PipelineConfig:
    """
    Create pipeline configuration from environment variables and Secret Manager.

    Environment Variables:
        GCP_PROJECT_ID: Google Cloud project ID
        VERTEX_DATA_STORE_ID: Vertex AI Search data store ID
        GCP_LOCATION: GCP region (default: us)
        FIGMA_ACCESS_TOKEN: Figma API personal access token
        GEMINI_API_KEY: Gemini API key
        RAG_SERVICE_URL: RAG service base URL (default: https://rag-service-p3cxgvcsla-uc.a.run.app)
        ASANA_MESSAGING_STAGE_GID: GID of "Messaging Stage" custom field
        ASANA_FIGMA_URL_GID: GID of "Figma URL" custom field
        ASANA_CLIENT_FIELD_GID: GID of "Client" custom field
        ORCHESTRATOR_URL: Orchestrator service URL for posting Asana comments
    """
    project_id = os.getenv('GCP_PROJECT_ID', 'emailpilot-438321')

    # Figma configuration
    figma_token = (
        os.getenv('FIGMA_ACCESS_TOKEN') or
        get_secret('figma-access-token', project_id)
    )

    figma_config = FigmaConfig(
        access_token=figma_token,
        timeout_seconds=int(os.getenv('FIGMA_TIMEOUT', '30')),
        image_scale=float(os.getenv('FIGMA_IMAGE_SCALE', '2.0'))
    )

    # Gemini Vision configuration
    gemini_api_key = (
        os.getenv('GEMINI_API_KEY') or
        get_secret('gemini-rag-image-processing', project_id)
    )

    vision_config = VisionConfig(
        api_key=gemini_api_key,
        model_name=os.getenv('GEMINI_MODEL_NAME', 'gemini-2.0-flash-lite'),
        temperature=float(os.getenv('GEMINI_TEMPERATURE', '0.3'))
    )

    # RAG service configuration
    rag_config = RAGConfig(
        base_url=os.getenv('RAG_SERVICE_URL', 'https://rag-service-p3cxgvcsla-uc.a.run.app'),
        timeout_seconds=int(os.getenv('RAG_TIMEOUT', '30')),
        default_k=int(os.getenv('RAG_DEFAULT_K', '5'))
    )

    # Asana configuration
    asana_config = AsanaConfig(
        messaging_stage_gid=os.getenv('ASANA_MESSAGING_STAGE_GID'),
        figma_url_gid=os.getenv('ASANA_FIGMA_URL_GID'),
        client_field_gid=os.getenv('ASANA_CLIENT_FIELD_GID'),
        trigger_stage_value=os.getenv('ASANA_TRIGGER_STAGE', 'AI Email Review'),
        orchestrator_url=os.getenv('ORCHESTRATOR_URL', 'https://app.emailpilot.ai'),
        post_results_enabled=os.getenv('ASANA_POST_RESULTS', 'true').lower() == 'true'
    )

    return PipelineConfig(
        gcp_project_id=project_id,
        vertex_data_store_id=os.getenv('VERTEX_DATA_STORE_ID', 'emailpilot-rag_1765205761919'),
        gcp_location=os.getenv('GCP_LOCATION', 'us'),
        firestore_collection=os.getenv('FIGMA_REVIEW_FIRESTORE_COLLECTION', 'figma_review_state'),
        figma=figma_config,
        vision=vision_config,
        rag=rag_config,
        asana=asana_config
    )
