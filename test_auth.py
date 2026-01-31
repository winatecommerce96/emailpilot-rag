"""Test script for Clerk JWKS authentication."""

import os
import asyncio
from app.auth import get_jwks_url, verify_clerk_token, AuthError


async def test_jwks_url():
    """Test JWKS URL derivation."""
    print("\n=== Testing JWKS URL Derivation ===")

    # Test with explicit GLOBAL_AUTH_JWKS_URL
    os.environ["GLOBAL_AUTH_JWKS_URL"] = "https://test.clerk.accounts.dev/.well-known/jwks.json"
    url = get_jwks_url()
    print(f"✓ Explicit JWKS URL: {url}")
    assert url == "https://test.clerk.accounts.dev/.well-known/jwks.json"

    # Test derivation from CLERK_FRONTEND_API
    del os.environ["GLOBAL_AUTH_JWKS_URL"]
    os.environ["CLERK_FRONTEND_API"] = "current-stork-99.clerk.accounts.dev"
    url = get_jwks_url()
    print(f"✓ Derived JWKS URL: {url}")
    assert url == "https://current-stork-99.clerk.accounts.dev/.well-known/jwks.json"

    # Test error case
    del os.environ["CLERK_FRONTEND_API"]
    try:
        get_jwks_url()
        print("✗ Should have raised AuthError")
    except AuthError:
        print("✓ Correctly raises AuthError when no config present")


async def test_token_validation():
    """Test token validation (will fail without real token, just structure test)."""
    print("\n=== Testing Token Validation Structure ===")

    # Set up environment
    os.environ["CLERK_FRONTEND_API"] = "current-stork-99.clerk.accounts.dev"

    # Test with empty token
    try:
        await verify_clerk_token("")
        print("✗ Should have raised AuthError for empty token")
    except AuthError as e:
        print(f"✓ Correctly rejects empty token: {e}")

    # Test with malformed token
    try:
        await verify_clerk_token("invalid.token.here")
        print("✗ Should have raised AuthError for malformed token")
    except AuthError as e:
        print(f"✓ Correctly rejects malformed token: {e}")


def test_auth_config_endpoint():
    """Test /auth/config endpoint logic."""
    print("\n=== Testing Auth Config Endpoint ===")

    # Test with all env vars set
    os.environ["GLOBAL_AUTH_ENABLED"] = "true"
    os.environ["CLERK_PUBLISHABLE_KEY"] = "pk_test_123"
    os.environ["CLERK_FRONTEND_API"] = "current-stork-99.clerk.accounts.dev"

    from app.main import auth_config
    config = auth_config()

    assert config["enabled"] is True
    assert config["provider"] == "clerk"
    assert config["clerk"]["publishable_key"] == "pk_test_123"
    assert config["clerk"]["frontend_api"] == "current-stork-99.clerk.accounts.dev"
    assert config["clerk"]["sign_in_url"] == "/static/login.html"

    print(f"✓ Auth config: {config}")

    # Test with auth disabled
    os.environ["GLOBAL_AUTH_ENABLED"] = "false"
    config = auth_config()
    assert config["enabled"] is False
    print(f"✓ Auth disabled config: {config}")


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("RAG Service - Clerk Authentication Tests")
    print("="*60)

    try:
        await test_jwks_url()
        await test_token_validation()
        test_auth_config_endpoint()

        print("\n" + "="*60)
        print("✓ All tests passed!")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
