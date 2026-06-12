import asyncio
import json
import bybit_service
import binance_service
from ai_service import analyze_funding_opportunities
from scoring import calculate_score

async def main():
    try:
        svc = binance_service
        rates = await svc.get_all_funding_rates()
        stats = await svc.get_stats()
        
        sorted_rates = sorted(rates, key=lambda x: x["fundingRate"], reverse=True)
        top_positive = sorted_rates[:10]
        top_negative = sorted_rates[-10:]

        key_symbols = [r["symbol"] for r in (top_positive[:5] + top_negative[:5])]
        print(f"Top symbols to fetch LSR: {key_symbols}")

        async def fetch_lsr(sym):
            try:
                data = await svc.get_long_short_ratio(sym, "1h", 1)
                if data:
                    return sym, data[0]
            except Exception:
                pass
            return sym, None

        lsr_results = await asyncio.gather(*[fetch_lsr(s) for s in key_symbols])
        lsr_data = {}
        for sym, data in lsr_results:
            if data:
                lsr_data[sym] = {
                    "longShortRatio": data["longShortRatio"],
                    "longAccount": data["longAccount"],
                    "shortAccount": data["shortAccount"],
                }

        async def simplify(item):
            score_data = await calculate_score(item)
            return {
                "symbol": item["symbol"],
                "fundingRatePercent": item["fundingRatePercent"],
                "monthlyRate": item["monthlyRate"],
                "lastPrice": item["lastPrice"],
                "volume24h": item.get("volume24h", 0),
                "price24hPcnt": item.get("price24hPcnt", 0),
                "fundingInterval": item.get("fundingInterval", 8),
                "lsr": lsr_data.get(item["symbol"]),
                "score": score_data["score"],
                "confidence": score_data["confidence"],
                "signal": score_data["signal"],
                "shouldOpen": score_data["shouldOpen"],
                "reasons": score_data["reasons"],
            }

        top_pos_simple = await asyncio.gather(*[simplify(r) for r in top_positive])
        top_neg_simple = await asyncio.gather(*[simplify(r) for r in top_negative])

        print("Calling analyze_funding_opportunities...")
        result = await analyze_funding_opportunities(
            top_pos_simple, top_neg_simple, lsr_data, stats, "binance"
        )
        print("Done!")
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
