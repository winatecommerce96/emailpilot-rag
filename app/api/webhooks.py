"""
Clerk Webhook Endpoint for RAG Spoke.

Handles Clerk user lifecycle events with proper Svix signature verification.
"""
import os
import logging
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Request, HTTPException, status

logger = logging.getLogger(__name__)

# Svix for Clerk webhook verification (lazy import)
try:
    from svix import Webhook as SvixWebhook, WebhookVerificationError as SvixVerificationError
    SVIX_AVAILABLE = True
except ImportError:
    SVIX_AVAILABLE = False
    SvixWebhook = None
    SvixVerificationError = Exception

router = APIRouter(prefix="/api/users", tags=["Webhooks"])


@router.post("/clerk/webhook", status_code=status.HTTP_202_ACCEPTED)
async def clerk_webhook(request: Request):
    """
    Handle Clerk webhook callbacks for user management.

    SECURITY: Verifies webhook signature using Svix before processing.
    Clerk webhooks use Svix for signature verification with headers:
    - svix-id
    - svix-timestamp
    - svix-signature
    """
    # =========================================================================
    # STEP 1: Verify webhook signature (CRITICAL SECURITY CHECK)
    # =========================================================================
    if not SVIX_AVAILABLE:
        logger.error("Svix module not installed - cannot verify Clerk webhooks")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook verification unavailable (svix module not installed)"
        )

    # Get webhook secret from environment
    webhook_secret = os.getenv("CLERK_WEBHOOK_SECRET", "").strip()

    if not webhook_secret:
        logger.error("CLERK_WEBHOOK_SECRET not configured for RAG spoke")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CLERK_WEBHOOK_SECRET not configured"
        )

    # Extract Svix headers
    svix_id = request.headers.get("svix-id")
    svix_timestamp = request.headers.get("svix-timestamp")
    svix_signature = request.headers.get("svix-signature")

    if not all([svix_id, svix_timestamp, svix_signature]):
        logger.warning("Missing Svix headers in Clerk webhook request")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required webhook signature headers (svix-id, svix-timestamp, svix-signature)"
        )

    # Get raw payload for signature verification
    payload = await request.body()
    headers = {
        "svix-id": svix_id,
        "svix-timestamp": svix_timestamp,
        "svix-signature": svix_signature,
    }

    # Verify signature
    try:
        wh = SvixWebhook(webhook_secret)
        event = wh.verify(payload, headers)
    except SvixVerificationError as e:
        logger.warning(f"Clerk webhook signature verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature"
        )
    except Exception as e:
        # Catch invalid secret format (base64 decode errors, etc.)
        logger.error(f"Clerk webhook secret configuration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook verification configuration error"
        )

    # =========================================================================
    # STEP 2: Process verified webhook event
    # =========================================================================
    event_type = event.get("type")
    data = event.get("data", {})

    logger.info(f"[RAG] Processing verified Clerk webhook: {event_type}")

    try:
        if event_type == "user.created":
            # Log user creation - RAG spoke can use this to init user preferences
            email_addresses = data.get("email_addresses", [])
            if email_addresses:
                email = email_addresses[0]["email_address"]
                logger.info(f"[RAG] New user created: {email}")
                # Future: Initialize user-specific RAG preferences, quotas, etc.

        elif event_type == "user.updated":
            email_addresses = data.get("email_addresses", [])
            if email_addresses:
                email = email_addresses[0]["email_address"]
                logger.info(f"[RAG] User updated: {email}")

        elif event_type == "user.deleted":
            email_addresses = data.get("email_addresses", [])
            if email_addresses:
                email = email_addresses[0]["email_address"]
                logger.info(f"[RAG] User deleted: {email}")
                # Future: Clean up user-specific data if needed

        else:
            logger.info(f"[RAG] Ignoring unhandled Clerk event type: {event_type}")

        return {"status": "success", "event_type": event_type, "service": "rag"}

    except Exception as e:
        logger.error(f"[RAG] Clerk webhook processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
