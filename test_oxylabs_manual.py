import asyncio
import os
from dotenv import load_dotenv
from app.services.oxylabs import OxylabsFetcher

# Load environment variables from .env
load_dotenv()

async def main():
    fetcher = OxylabsFetcher()
    test_url = "https://example.com"
    print(f"Testing Oxylabs connectivity with: {test_url}")
    
    result = await fetcher.fetch(test_url)
    
    if result["status"] == "ok":
        print("✅ SUCCESS: Oxylabs is connected and returned HTML.")
        print(f"Fetch time: {result['fetch_ms']}ms")
        print(f"HTML snippet: {result['html'][:200]}...")
    else:
        print("❌ FAILED: Oxylabs connection failed.")
        print(f"Error: {result['error']}")
        print(f"Fetch time: {result['fetch_ms']}ms")

if __name__ == "__main__":
    asyncio.run(main())
