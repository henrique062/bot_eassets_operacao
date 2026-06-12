# -*- coding: utf-8 -*-
"""
Salva no banco uma análise da metodologia Encryptos feita no chat.

Recebe o JSON da análise (de um arquivo ou via stdin) e grava ligado ao último
snapshot importado (ou a um snapshot específico via --sid). Permite comparar
análises de dias diferentes depois.

Estrutura esperada do JSON:
{
  "resumo_btc": "texto da leitura do BTC",
  "janela_aberta": true,
  "ativos": [
    {"symbol": "PLAYUSDT", "veredito": "COMPRAR", "confianca": 80,
     "fase": "IGNIÇÃO", "razao": "..."},
    ...
  ]
}

Uso:
    python salvar_analise.py analise.json
    Get-Content analise.json | python salvar_analise.py        # stdin (PowerShell)
    python salvar_analise.py analise.json --sid 3              # snapshot específico
"""
import sys
import json

import db


def main():
    args = [a for a in sys.argv[1:]]
    sid = None
    if "--sid" in args:
        i = args.index("--sid")
        sid = int(args[i + 1])
        del args[i:i + 2]

    if args:
        with open(args[0], encoding="utf-8") as f:
            raw = f.read()
    else:
        raw = sys.stdin.read()

    if not raw.strip():
        print("Nenhum JSON recebido (passe arquivo ou via stdin).")
        return 1
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"JSON inválido: {exc}")
        return 1
    if "ativos" not in data or not isinstance(data["ativos"], list):
        print("JSON sem a chave 'ativos' (lista). Nada salvo.")
        return 1

    if sid is None:
        sid = db.latest_snapshot_id()
    if not sid:
        print("Nenhum snapshot no banco. Importe um JSON antes de salvar análise.")
        return 1

    db.save_analise(sid, data)
    print(f"OK: análise salva no snapshot {sid} — {len(data['ativos'])} ativos · "
          f"janela_aberta={bool(data.get('janela_aberta'))}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
