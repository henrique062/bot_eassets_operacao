import asyncio
import binance_service

async def test():
    rates = await binance_service.get_all_funding_rates()
    for rate in rates[:3]:
        print(f"{rate['symbol']}: Funding={rate['fundingRatePercent']}%, NextTime={rate['nextFundingTime']}")

asyncio.run(test())
