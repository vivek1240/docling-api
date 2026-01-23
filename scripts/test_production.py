# %% [markdown]
# # DocProcess API - Production Testing Notebook
# 
# This script tests the production endpoints for:
# - Latency measurements
# - Accuracy validation
# - API functionality
# 
# Run each cell independently using VS Code's "Run Cell" or Cursor's interactive mode.

# %% [markdown]
# ## 1. Setup & Configuration

# %%
import requests
import time
import json
from datetime import datetime
from typing import Optional
import statistics

# =============================================================================
# CONFIGURATION - Update these values
# =============================================================================

# Production API URL (Railway)
API_BASE_URL = "https://web-production-00a7f.up.railway.app"

# Modal Direct URL (for comparison)
MODAL_DIRECT_URL = "https://vivek12345singh--docling-service-convert-endpoint.modal.run"

# Test documents
TEST_DOCUMENTS = {
    "arxiv_docling": "https://arxiv.org/pdf/2501.17887",  # Docling paper (8 pages)
    "arxiv_attention": "https://arxiv.org/pdf/1706.03762",  # Attention paper (15 pages)
    "simple_pdf": "https://www.w3.org/WAI/WCAG21/Techniques/pdf/img/table-word.pdf",  # Simple PDF
}

# Store results
test_results = {
    "api_key": None,
    "latency_tests": [],
    "accuracy_tests": [],
}

print("✅ Configuration loaded")
print(f"   API URL: {API_BASE_URL}")
print(f"   Modal URL: {MODAL_DIRECT_URL}")

# %% [markdown]
# ## 2. Health Check

# %%
def check_health():
    """Check API health status."""
    print("🔍 Checking API Health...")
    print("-" * 50)
    
    start = time.time()
    response = requests.get(f"{API_BASE_URL}/health")
    latency = (time.time() - start) * 1000
    
    data = response.json()
    
    print(f"Status Code: {response.status_code}")
    print(f"Latency: {latency:.2f}ms")
    print(f"Response: {json.dumps(data, indent=2)}")
    
    return data

health = check_health()

# %% [markdown]
# ## 3. Create API Key

# %%
def create_api_key(name: str = "Test Key", credits: int = 100):
    """Create a new API key for testing."""
    print("🔑 Creating API Key...")
    print("-" * 50)
    
    response = requests.post(
        f"{API_BASE_URL}/v1/keys",
        json={"name": name, "credits": credits}
    )
    
    data = response.json()
    
    print(f"Status Code: {response.status_code}")
    print(f"Key ID: {data.get('id')}")
    print(f"API Key: {data.get('key', '')[:30]}...")
    print(f"Credits: {data.get('credits')}")
    
    # Store for later use
    test_results["api_key"] = data.get("key")
    
    return data

key_data = create_api_key("Production Test", credits=500)

# %% [markdown]
# ## 4. Single Document Conversion Test

# %%
def convert_document(url: str, api_key: Optional[str] = None):
    """Convert a single document and measure performance."""
    api_key = api_key or test_results["api_key"]
    
    print(f"📄 Converting: {url[:50]}...")
    print("-" * 50)
    
    start = time.time()
    
    response = requests.post(
        f"{API_BASE_URL}/v1/convert/source",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "sources": [{"kind": "http", "url": url}],
            "options": {"output_format": "markdown"}
        },
        timeout=300  # 5 minute timeout for large docs
    )
    
    total_latency = (time.time() - start) * 1000
    
    data = response.json()
    
    if response.status_code == 200 and "results" in data:
        result = data["results"][0]
        markdown = result.get("markdown", "")
        
        print(f"✅ Status: {result.get('status')}")
        print(f"📄 Pages: {result.get('pages')}")
        print(f"📝 Markdown Length: {len(markdown):,} chars")
        print(f"⏱️  Total Latency: {total_latency:.2f}ms ({total_latency/1000:.2f}s)")
        print(f"💰 Credits Used: {data.get('credits_used')}")
        print(f"💳 Credits Remaining: {data.get('credits_remaining')}")
        
        # Calculate per-page metrics
        pages = result.get('pages', 1)
        print(f"\n📊 Performance Metrics:")
        print(f"   Latency per page: {total_latency/pages:.2f}ms")
        print(f"   Chars per page: {len(markdown)/pages:.0f}")
        
        return {
            "success": True,
            "url": url,
            "pages": pages,
            "markdown_length": len(markdown),
            "latency_ms": total_latency,
            "latency_per_page_ms": total_latency / pages,
            "credits_used": data.get("credits_used"),
            "markdown_preview": markdown[:500]
        }
    else:
        print(f"❌ Error: {data}")
        return {
            "success": False,
            "url": url,
            "error": data
        }

# Test with Docling paper
result = convert_document(TEST_DOCUMENTS["arxiv_docling"])

# %% [markdown]
# ## 5. Latency Benchmark - Multiple Documents

# %%
def run_latency_benchmark(num_runs: int = 3):
    """Run multiple conversions to measure average latency."""
    print("⏱️  Running Latency Benchmark...")
    print("=" * 60)
    
    api_key = test_results["api_key"]
    test_url = TEST_DOCUMENTS["arxiv_docling"]
    
    latencies = []
    
    for i in range(num_runs):
        print(f"\n🔄 Run {i+1}/{num_runs}")
        
        start = time.time()
        response = requests.post(
            f"{API_BASE_URL}/v1/convert/source",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "sources": [{"kind": "http", "url": test_url}],
                "options": {"output_format": "markdown"}
            },
            timeout=300
        )
        latency = (time.time() - start) * 1000
        
        if response.status_code == 200:
            data = response.json()
            pages = data["results"][0].get("pages", 1)
            latencies.append({
                "run": i + 1,
                "total_ms": latency,
                "per_page_ms": latency / pages,
                "pages": pages
            })
            print(f"   ✅ {latency:.2f}ms total, {latency/pages:.2f}ms/page")
        else:
            print(f"   ❌ Failed: {response.text[:100]}")
    
    if latencies:
        total_latencies = [l["total_ms"] for l in latencies]
        per_page_latencies = [l["per_page_ms"] for l in latencies]
        
        print("\n" + "=" * 60)
        print("📊 LATENCY SUMMARY")
        print("=" * 60)
        print(f"Runs: {len(latencies)}")
        print(f"\nTotal Latency:")
        print(f"   Min: {min(total_latencies):.2f}ms")
        print(f"   Max: {max(total_latencies):.2f}ms")
        print(f"   Avg: {statistics.mean(total_latencies):.2f}ms")
        if len(total_latencies) > 1:
            print(f"   Std: {statistics.stdev(total_latencies):.2f}ms")
        
        print(f"\nPer-Page Latency:")
        print(f"   Min: {min(per_page_latencies):.2f}ms")
        print(f"   Max: {max(per_page_latencies):.2f}ms")
        print(f"   Avg: {statistics.mean(per_page_latencies):.2f}ms")
        
        test_results["latency_tests"] = latencies
    
    return latencies

# Run benchmark (adjust num_runs as needed)
latency_results = run_latency_benchmark(num_runs=3)

# %% [markdown]
# ## 6. Compare: Railway API vs Modal Direct

# %%
def compare_railway_vs_modal():
    """Compare latency between Railway API and direct Modal call."""
    print("🔄 Comparing Railway API vs Modal Direct...")
    print("=" * 60)
    
    api_key = test_results["api_key"]
    test_url = TEST_DOCUMENTS["arxiv_docling"]
    
    results = {}
    
    # Test Railway API
    print("\n📡 Testing Railway API...")
    start = time.time()
    response = requests.post(
        f"{API_BASE_URL}/v1/convert/source",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "sources": [{"kind": "http", "url": test_url}],
            "options": {"output_format": "markdown"}
        },
        timeout=300
    )
    railway_latency = (time.time() - start) * 1000
    
    if response.status_code == 200:
        data = response.json()
        results["railway"] = {
            "latency_ms": railway_latency,
            "pages": data["results"][0].get("pages"),
            "markdown_len": len(data["results"][0].get("markdown", ""))
        }
        print(f"   ✅ Latency: {railway_latency:.2f}ms")
    
    # Test Modal Direct
    print("\n🚀 Testing Modal Direct...")
    start = time.time()
    response = requests.post(
        MODAL_DIRECT_URL,
        json={"url": test_url, "output_format": "markdown"},
        timeout=300
    )
    modal_latency = (time.time() - start) * 1000
    
    if response.status_code == 200:
        data = response.json()
        results["modal"] = {
            "latency_ms": modal_latency,
            "pages": data.get("pages"),
            "markdown_len": len(data.get("markdown", ""))
        }
        print(f"   ✅ Latency: {modal_latency:.2f}ms")
    
    # Comparison
    if "railway" in results and "modal" in results:
        overhead = results["railway"]["latency_ms"] - results["modal"]["latency_ms"]
        overhead_pct = (overhead / results["modal"]["latency_ms"]) * 100
        
        print("\n" + "=" * 60)
        print("📊 COMPARISON RESULTS")
        print("=" * 60)
        print(f"Railway API:   {results['railway']['latency_ms']:.2f}ms")
        print(f"Modal Direct:  {results['modal']['latency_ms']:.2f}ms")
        print(f"Overhead:      {overhead:.2f}ms ({overhead_pct:.1f}%)")
        print(f"\nMarkdown lengths match: {results['railway']['markdown_len'] == results['modal']['markdown_len']}")
    
    return results

comparison = compare_railway_vs_modal()

# %% [markdown]
# ## 7. Accuracy Test - Content Validation

# %%
def test_accuracy():
    """Test accuracy by checking for expected content in converted documents."""
    print("🎯 Running Accuracy Tests...")
    print("=" * 60)
    
    api_key = test_results["api_key"]
    
    # Test cases: (url, expected_strings)
    test_cases = [
        {
            "name": "Docling Paper",
            "url": TEST_DOCUMENTS["arxiv_docling"],
            "expected": [
                "Docling",
                "document conversion",
                "IBM Research",
                "PDF",
                "table",
            ]
        },
    ]
    
    results = []
    
    for test in test_cases:
        print(f"\n📄 Testing: {test['name']}")
        print("-" * 40)
        
        response = requests.post(
            f"{API_BASE_URL}/v1/convert/source",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "sources": [{"kind": "http", "url": test["url"]}],
                "options": {"output_format": "markdown"}
            },
            timeout=300
        )
        
        if response.status_code == 200:
            data = response.json()
            markdown = data["results"][0].get("markdown", "").lower()
            
            found = []
            missing = []
            
            for expected in test["expected"]:
                if expected.lower() in markdown:
                    found.append(expected)
                else:
                    missing.append(expected)
            
            accuracy = len(found) / len(test["expected"]) * 100
            
            print(f"   Found: {found}")
            if missing:
                print(f"   Missing: {missing}")
            print(f"   Accuracy: {accuracy:.1f}%")
            
            results.append({
                "name": test["name"],
                "found": found,
                "missing": missing,
                "accuracy": accuracy
            })
        else:
            print(f"   ❌ Request failed: {response.status_code}")
    
    test_results["accuracy_tests"] = results
    return results

accuracy_results = test_accuracy()

# %% [markdown]
# ## 8. Load Test - Multiple Concurrent Requests

# %%
import concurrent.futures

def load_test(num_requests: int = 5, max_workers: int = 3):
    """Run multiple concurrent requests to test load handling."""
    print(f"🔥 Load Test: {num_requests} requests, {max_workers} concurrent workers")
    print("=" * 60)
    
    api_key = test_results["api_key"]
    test_url = TEST_DOCUMENTS["arxiv_docling"]
    
    def make_request(request_id):
        start = time.time()
        try:
            response = requests.post(
                f"{API_BASE_URL}/v1/convert/source",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "sources": [{"kind": "http", "url": test_url}],
                    "options": {"output_format": "markdown"}
                },
                timeout=300
            )
            latency = (time.time() - start) * 1000
            success = response.status_code == 200
            return {
                "id": request_id,
                "success": success,
                "latency_ms": latency,
                "status_code": response.status_code
            }
        except Exception as e:
            return {
                "id": request_id,
                "success": False,
                "error": str(e)
            }
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(make_request, i) for i in range(num_requests)]
        
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            status = "✅" if result.get("success") else "❌"
            print(f"   {status} Request {result['id']}: {result.get('latency_ms', 0):.2f}ms")
    
    # Summary
    successful = [r for r in results if r.get("success")]
    if successful:
        latencies = [r["latency_ms"] for r in successful]
        print("\n" + "=" * 60)
        print("📊 LOAD TEST SUMMARY")
        print("=" * 60)
        print(f"Total Requests: {num_requests}")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {num_requests - len(successful)}")
        print(f"Success Rate: {len(successful)/num_requests*100:.1f}%")
        print(f"\nLatency (successful requests):")
        print(f"   Min: {min(latencies):.2f}ms")
        print(f"   Max: {max(latencies):.2f}ms")
        print(f"   Avg: {statistics.mean(latencies):.2f}ms")
    
    return results

# Run load test (adjust parameters as needed)
# Warning: This uses credits!
load_results = load_test(num_requests=3, max_workers=2)

# %% [markdown]
# ## 9. Check Remaining Credits

# %%
def check_credits():
    """Check remaining credits for the API key."""
    print("💳 Checking Credits...")
    print("-" * 50)
    
    api_key = test_results["api_key"]
    
    # Make a request to get credits info
    response = requests.get(
        f"{API_BASE_URL}/v1/usage",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
    else:
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    
    return response.json() if response.status_code == 200 else None

credits_info = check_credits()

# %% [markdown]
# ## 10. Final Summary Report

# %%
def generate_report():
    """Generate a final summary report of all tests."""
    print("\n" + "=" * 70)
    print("📋 FINAL TEST REPORT")
    print("=" * 70)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API URL: {API_BASE_URL}")
    
    print("\n🔑 API KEY")
    print("-" * 40)
    if test_results["api_key"]:
        print(f"   Key: {test_results['api_key'][:30]}...")
    
    print("\n⏱️  LATENCY TESTS")
    print("-" * 40)
    if test_results["latency_tests"]:
        latencies = [t["total_ms"] for t in test_results["latency_tests"]]
        print(f"   Runs: {len(latencies)}")
        print(f"   Average: {statistics.mean(latencies):.2f}ms")
        print(f"   Range: {min(latencies):.2f}ms - {max(latencies):.2f}ms")
    
    print("\n🎯 ACCURACY TESTS")
    print("-" * 40)
    if test_results["accuracy_tests"]:
        for test in test_results["accuracy_tests"]:
            print(f"   {test['name']}: {test['accuracy']:.1f}%")
    
    print("\n" + "=" * 70)
    print("✅ Testing Complete!")
    print("=" * 70)

generate_report()

# %% [markdown]
# ## Bonus: Quick Test Function

# %%
def quick_test(url: str):
    """Quick function to test any URL."""
    api_key = test_results["api_key"]
    if not api_key:
        print("❌ No API key. Run cell 3 first!")
        return
    
    print(f"🚀 Quick converting: {url}")
    start = time.time()
    
    response = requests.post(
        f"{API_BASE_URL}/v1/convert/source",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "sources": [{"kind": "http", "url": url}],
            "options": {"output_format": "markdown"}
        },
        timeout=300
    )
    
    latency = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        result = data["results"][0]
        print(f"✅ Done in {latency:.2f}s")
        print(f"   Pages: {result.get('pages')}")
        print(f"   Length: {len(result.get('markdown', '')):,} chars")
        return result.get("markdown")
    else:
        print(f"❌ Error: {response.text}")
        return None

# Example usage:
# markdown = quick_test("https://example.com/document.pdf")
