import httpx
import asyncio

async def main():
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.get("http://localhost:8001/api/ai-analysis?exchange=binance")
            print(f"Status: {res.status_code}")
            print(res.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
