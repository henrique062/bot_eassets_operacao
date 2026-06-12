import asyncio

import database as db
from real_trader import _sync_positions_once


async def main() -> None:
    await db.init_db()
    try:
        rows = await db.fetch(
            """
            SELECT
                c.id,
                c.session_name,
                c.exchange,
                c.user_id,
                c.leverage,
                c.fee_rate,
                c.balance,
                COUNT(p.id) AS positions_count
            FROM real_config c
            JOIN real_positions p ON p.config_id = c.id
            WHERE COALESCE(c.active, FALSE) = FALSE
            GROUP BY c.id, c.session_name, c.exchange, c.user_id, c.leverage, c.fee_rate, c.balance
            ORDER BY c.id
            """
        )

        if not rows:
            print("Nenhuma posicao vinculada a bot inativo foi encontrada.")
            return

        print(f"Encontradas {len(rows)} sessoes inativas com posicoes abertas.")
        total_closed = 0
        total_remaining = 0
        total_errors = 0

        for row in rows:
            session_id = int(row["id"])
            session_name = row["session_name"] or f"Bot #{session_id}"
            session_cfg = {
                "exchange": row["exchange"] or "binance",
                "user_id": row["user_id"],
                "leverage": int(row["leverage"] or 1),
                "feeRate": float(row["fee_rate"] or 0.0004),
                "balance": float(row["balance"] or 0),
            }

            print(
                f"\n[ReconcileInactive] Sessao {session_id} ({session_name}) "
                f"- posicoes no inicio: {int(row['positions_count'] or 0)}"
            )
            result = await _sync_positions_once(
                session_id,
                session_cfg,
                include_inactive=True,
                close_reason="exchange_sync_orphan",
            )

            closed_in_db = int(result.get("closed_in_db", 0) or 0)
            remaining_symbols = list(result.get("remaining_symbols", []))
            errors = list(result.get("errors", []))

            total_closed += closed_in_db
            total_remaining += len(remaining_symbols)
            total_errors += len(errors)

            print(f"[ReconcileInactive] Fechadas no DB: {closed_in_db}")
            if remaining_symbols:
                print(
                    "[ReconcileInactive] Ainda abertas na exchange/DB: "
                    + ", ".join(remaining_symbols)
                )
            if errors:
                print(f"[ReconcileInactive] Erros nao fatais: {len(errors)}")
                for err in errors[:5]:
                    print(f"  - {err}")

        leftovers = await db.fetch(
            """
            SELECT c.id, c.session_name, p.symbol, p.direction
            FROM real_positions p
            JOIN real_config c ON c.id = p.config_id
            WHERE COALESCE(c.active, FALSE) = FALSE
            ORDER BY c.id, p.symbol
            """
        )

        print("\nResumo final:")
        print(f"- Posicoes fechadas no DB: {total_closed}")
        print(f"- Posicoes ainda remanescentes: {len(leftovers)}")
        print(f"- Erros nao fatais: {total_errors}")

        if leftovers:
            print("\nPendencias para acao manual:")
            for row in leftovers:
                name = row["session_name"] or f"Bot #{row['id']}"
                print(
                    f"- sessao={row['id']} "
                    f"nome={name} "
                    f"simbolo={row['symbol']} direcao={row['direction']}"
                )

    finally:
        await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())
