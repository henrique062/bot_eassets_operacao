# -*- coding: utf-8 -*-
"""
Prepara os dados do último snapshot para análise da metodologia Encryptos NO CHAT.

Não chama nenhuma API. Apenas lê o último snapshot salvo no banco (ou o JSON mais
recente da pasta, importando-o se necessário), seleciona os candidatos mais
relevantes (união de top score / top entrada / top T-OI), anexa o histórico de
cada um e imprime um relatório compacto em stdout.

A skill `analise-encryptos` roda este script, lê a saída e aplica o protocolo
para montar a lista ranqueada (veredito / fase / razão) diretamente no chat.

Uso:
    python analise_dados.py [N]      # N = nº de candidatos (padrão 30)
"""
import sys
import glob
import json

import gerar_painel as core
import db


def _ensure_snapshot():
    """Garante que há um snapshot no banco; senão importa o JSON mais recente."""
    sid = db.latest_snapshot_id()
    if sid:
        return sid
    cands = sorted(glob.glob("eassets-panel-*.json"))
    if not cands:
        return None
    with open(cands[-1], encoding="utf-8") as f:
        doc = json.load(f)
    sid, _, _ = db.ingest(doc, source=cands[-1])
    return sid


def build_candidates(data, max_n=30):
    """União de top score / top entrada / top T-OI (sem BTC), com histórico."""
    rows = [r for r in core.build_rows(data) if r["symbol"] != "BTCUSDT"]
    by_score = sorted(rows, key=lambda r: r["score"], reverse=True)[:15]
    by_entry = sorted(rows, key=lambda r: r["entry_score"], reverse=True)[:15]
    by_toi = sorted([r for r in rows if r["toi"] is not None],
                    key=lambda r: r["toi"], reverse=True)[:15]
    seen, chosen = set(), []
    for r in by_score + by_entry + by_toi:
        if r["symbol"] not in seen:
            seen.add(r["symbol"])
            chosen.append(r)
        if len(chosen) >= max_n:
            break
    return chosen


def fnum(v, d=2):
    return f"{v:.{d}f}" if isinstance(v, (int, float)) else "—"


def main():
    max_n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    sid = _ensure_snapshot()
    if not sid:
        print("Nenhum snapshot no banco e nenhum eassets-panel-*.json na pasta.")
        return 1

    meta, data = db.get_snapshot(sid)
    btc = data.get("BTCUSDT")
    macro = core.btc_macro(btc)
    chosen = build_candidates(data, max_n=max_n)

    print(f"# DADOS PARA ANÁLISE ENCRYPTOS")
    print(f"Snapshot: {core.to_brt(meta['timestamp'])} BRT · exchange {meta['exchange']} · "
          f"setup {meta['setup']} · {meta['symbols']} ativos escaneados")
    print(f"Total de snapshots no histórico: {db.stats()['snapshots']}")
    print()
    print("## GATE MACRO — BITCOIN")
    print(f"Estado: {macro['state']} · janela_segura={macro['safe']}")
    if btc:
        print(f"RSI 5m={fnum(btc.get('rsi:5m'),1)} · 30m={fnum(btc.get('rsi:30m'),1)} · "
              f"1h={fnum(btc.get('rsi:1h'),1)} · 4h={fnum(btc.get('rsi:4h'),1)} · "
              f"1D={fnum(btc.get('rsi:1D'),1)}")
        print(f"OI trend={fnum(btc.get('oi_trend:5m'),2)} · "
              f"1D%={fnum(btc.get('price_change:1D'),2)}")
    print()
    print(f"## CANDIDATOS ({len(chosen)}) — união top score / top entrada / top T-OI")
    print("Legenda EXP=exp_btc (força vs BTC) · OIt=oi_trend · LSRt=lsr_trend · "
          "fr=funding · T/OI=trades_1D por $1M de OI · entrada=critérios setup de ouro")
    print()

    for i, r in enumerate(chosen, 1):
        e = data[r["symbol"]]
        chk = r["checklist"]
        falt = [k for k in ("exp_pos", "tpm_hot", "lsr_fuel", "oi_in",
                            "rsi_runway", "accumulation", "funding_neg") if not chk[k]]
        oi = e.get("oi:5m")
        oi_s = f"${oi/1e6:.1f}M" if isinstance(oi, (int, float)) else "—"
        print(f"### {i}. {r['asset']} ({r['symbol']})")
        print(f"preço={core.fmt_price(e.get('price'))} · 1D%={fnum(r['change'])} · "
              f"score_estrutural={r['score']} · setup_painel={r['badge']} · "
              f"entrada={r['entry_score']}/7 (falta: {', '.join(falt) or 'nada'}) · "
              f"armadilha={r['trap']}")
        print(f"  EXP 1D={fnum(e.get('exp_btc:1D'))} 4h={fnum(e.get('exp_btc:4h'))} "
              f"1h={fnum(e.get('exp_btc:1h'))} 15m={fnum(e.get('exp_btc:15m'))} "
              f"5m={fnum(e.get('exp_btc:5m'))}")
        print(f"  OI={oi_s} OIt={fnum(e.get('oi_trend:5m'))} · "
              f"LSR={fnum(e.get('lsr:5m'),3)} LSRt={fnum(e.get('lsr_trend:5m'))} · "
              f"fr={e.get('fr')} · T/OI={core.fmt_compact(r['toi'])}")
        print(f"  TPM 5m={e.get('trades_minute:5m')} 1h={e.get('trades_minute:1h')} · "
              f"TPS 5m={e.get('trades_second:5m')} · "
              f"RSI 1h={fnum(e.get('rsi:1h'),1)} 4h={fnum(e.get('rsi:4h'),1)} "
              f"1D={fnum(e.get('rsi:1D'),1)} · "
              f"range 1h={e.get('range_level:1h')} 4h={e.get('range_level:4h')} "
              f"1D={e.get('range_level:1D')}")
        hist = db.symbol_history(r["symbol"])
        if len(hist) > 1:
            serie = " | ".join(
                f"{core.to_brt(h['timestamp'], '%d/%m %H:%M')}: sc{h['score']} rk{h['rank']} "
                f"exp4h{fnum(h['exp_4h'],0)} oit{fnum(h['oi_trend'],0)} toi{core.fmt_compact(h['toi'])}"
                for h in reversed(hist))   # cronológico antigo->novo
            print(f"  HIST ({len(hist)} snaps): {serie}")
        else:
            print(f"  HIST: 1 snapshot só (sem série temporal ainda)")
        print()

    print("---")
    print("Aplique o protocolo Encryptos (gate BTC + força relativa + combustão + "
          "financiamento + acumulação + armadilhas + fases) e monte a lista ranqueada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
