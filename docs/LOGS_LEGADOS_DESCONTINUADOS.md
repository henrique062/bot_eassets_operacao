# Logs legados descontinuados

Os scripts `backend/query_logs.py` e `backend/query_psycopg.py` foram descontinuados.

Motivo:
- os scripts consultavam tabelas legadas (`bot_logs`, `system_logs`) que nao existem no schema atual.
- a fonte suportada para logs do servidor e `server_logs`.

Uso recomendado:
- endpoint: `GET /api/server-logs`
- filtros suportados: `level`, `module`, `date_from`, `date_to`, `search`, `limit`, `offset`

Observacao:
- para logs de ordem/execucao por bot real, use `GET /api/real-trading/{session_id}/logs`.
