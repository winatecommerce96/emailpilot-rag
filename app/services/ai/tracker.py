"""
AI Usage Tracker - Centralized Context & Instrumentation
========================================================

Provides infrastructure for tracking AI usage across Orchestrator (LangChain)
and EmailPilot-Simple (Raw Anthropic SDK). Uses ContextVars to propagate
metadata (user_id, org_id) through async call stacks.

Usage:
    # 1. In Middleware/Entry Point:
    async with TrackingContext(user_id="u123", org_id="o456"):
        await process_request()

    # 2. In LLM Client Setup:
    client = LLMTracker.wrap_anthropic(Anthropic(api_key=...))

    # 3. LangChain automatically picks up the context if configured correctly.
"""

import os
import contextvars
from typing import Optional, Dict, Any
import structlog

logger = structlog.get_logger(__name__)

# --- 1. Context Management ---

# ContextVar to hold the current tracking metadata
_tracking_context = contextvars.ContextVar("tracking_context", default={})

class TrackingContext:
    """
    Async Context Manager to set and clear AI tracking metadata.
    """
    def __init__(
        self,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        client_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None
    ):
        self.metadata = {
            "user_id": user_id,
            "org_id": org_id,
            "client_id": client_id,
            "workflow_id": workflow_id,
            **(extra_metadata or {})
        }
        # Filter out None values
        self.metadata = {k: v for k, v in self.metadata.items() if v is not None}
        self.token = None

    async def __aenter__(self):
        # Merge with existing context if any (nested contexts)
        current = _tracking_context.get()
        new_context = {**current, **self.metadata}
        self.token = _tracking_context.set(new_context)
        
        # Also set LangChain environment variables for legacy/implicit support
        if "user_id" in self.metadata:
            os.environ["LANGCHAIN_METADATA_USER_ID"] = self.metadata["user_id"]
        if "org_id" in self.metadata:
            os.environ["LANGCHAIN_METADATA_ORG_ID"] = self.metadata["org_id"]
            
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.token:
            _tracking_context.reset(self.token)
            
        # Clean up env vars (best effort)
        os.environ.pop("LANGCHAIN_METADATA_USER_ID", None)
        os.environ.pop("LANGCHAIN_METADATA_ORG_ID", None)

def get_current_tracking_context() -> Dict[str, Any]:
    """Retrieve the current tracking metadata."""
    return _tracking_context.get()


# --- 2. Client Instrumentation ---

class LLMTracker:
    """
    Factory for wrapping LLM clients with LangSmith tracking.
    """
    
    @staticmethod
    def _get_tracer_project():
        return os.getenv("LANGSMITH_PROJECT", "emailpilot-orchestrator")

    @staticmethod
    def wrap_anthropic(client):
        """
        Wrap an Anthropic client (Sync or Async) with LangSmith tracing.
        
        Args:
            client: instance of anthropic.Anthropic or anthropic.AsyncAnthropic
            
        Returns:
            Wrapped client
        """
        try:
            from langsmith.wrappers import wrap_anthropic
            
            # Ensure context metadata is injected on every call
            # Note: wrap_anthropic doesn't automatically pull from ContextVars for metadata
            # in older versions, but the 'tracing_context' feature in 0.1+ helps.
            # We rely on the environment variables set by TrackingContext for implicit
            # metadata in some cases, or we can patch the create method.
            
            wrapped = wrap_anthropic(client)
            return wrapped
        except ImportError:
            logger.warning("LangSmith not installed or version too old. Returning unwrapped client.")
            return client
        except Exception as e:
            logger.error(f"Failed to wrap Anthropic client: {e}")
            return client

    @staticmethod
    def wrap_openai(client):
        """
        Wrap an OpenAI client with LangSmith tracing.
        """
        try:
            from langsmith.wrappers import wrap_openai
            return wrap_openai(client)
        except ImportError:
            logger.warning("LangSmith not installed. Returning unwrapped OpenAI client.")
            return client
        except Exception as e:
            logger.error(f"Failed to wrap OpenAI client: {e}")
            return client

    @staticmethod
    def get_langchain_callback():
        """
        Get a LangChain callback handler injected with current context.
        Useful for hybrid chains.
        """
        try:
            from langsmith.run_helpers import get_current_run_tree
            # Implementation depends on specific usage
            pass
        except ImportError:
            pass
