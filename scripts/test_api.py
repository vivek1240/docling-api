#!/usr/bin/env python3
"""
API Test Script
===============

Quick tests to verify the API is working correctly.

Usage:
    python scripts/test_api.py [--url URL] [--key KEY]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from client import DocProcessClient, DocProcessError


async def main(base_url: str, api_key: str = None):
    """Run API tests."""
    
    print("🧪 DocProcess API Tests")
    print("=" * 50)
    print(f"Base URL: {base_url}")
    print()
    
    # Test 1: Health Check
    print("1️⃣  Health Check...")
    try:
        async with DocProcessClient(api_key=api_key or "test", base_url=base_url) as client:
            health = await client.health_check()
            print(f"   ✅ API is healthy: {health.get('status', 'unknown')}")
            print(f"   Backend: {health.get('docling_backend', 'unknown')}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return
    
    print()
    
    # If no API key, create one
    if not api_key:
        print("2️⃣  Creating API Key...")
        import httpx
        try:
            async with httpx.AsyncClient(base_url=base_url) as http:
                response = await http.post(
                    "/v1/keys",
                    json={"name": "Test Key", "credits": 100}
                )
                if response.status_code == 201:
                    data = response.json()
                    api_key = data["key"]
                    print(f"   ✅ Created key: {api_key[:20]}...")
                else:
                    print(f"   ❌ Failed: {response.status_code}")
                    return
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            return
        
        print()
    
    # Test 3: Get Account Info
    print("3️⃣  Getting Account Info...")
    try:
        async with DocProcessClient(api_key=api_key, base_url=base_url) as client:
            info = await client.get_account_info()
            print(f"   ✅ Key ID: {info.key_id}")
            print(f"   Credits: {info.credits_remaining}")
            print(f"   Tier: {info.tier}")
    except DocProcessError as e:
        print(f"   ❌ Failed: {e}")
        return
    
    print()
    
    # Test 4: Convert Document
    print("4️⃣  Converting Document from URL...")
    test_url = "https://arxiv.org/pdf/2501.17887"
    print(f"   URL: {test_url}")
    try:
        async with DocProcessClient(api_key=api_key, base_url=base_url, timeout=120) as client:
            result = await client.convert_url(test_url)
            if result.success:
                first = result.first_result
                print(f"   ✅ Converted successfully!")
                print(f"   Pages: {first.pages}")
                print(f"   Credits used: {result.credits_used}")
                print(f"   Credits remaining: {result.credits_remaining}")
                if first.markdown:
                    preview = first.markdown[:200].replace('\n', ' ')
                    print(f"   Preview: {preview}...")
            else:
                print(f"   ❌ Conversion failed: {result.first_result.error}")
    except DocProcessError as e:
        print(f"   ❌ Failed: {e}")
    except asyncio.TimeoutError:
        print("   ⚠️  Timeout (document may still be processing)")
    
    print()
    print("=" * 50)
    print("✅ Tests complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the DocProcess API")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--key",
        default=None,
        help="API key (if not provided, a new one will be created)"
    )
    
    args = parser.parse_args()
    
    asyncio.run(main(args.url, args.key))
