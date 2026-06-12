#!/usr/bin/env python3
"""
BANCADA PHOENIX — Gerador de dashboard estático
Lê dadosmoedas.txt e salva o HTML.

Uso: python gerar_dashboard.py [entrada] [saida]
"""

import json
import os
import sys

from engine import generate_html

INPUT_FILE  = "dadosmoedas.txt"
OUTPUT_FILE = "BANCADA PHOENIX — DASHBOARD UNIFICADO 300.html"


def main():
    input_file  = sys.argv[1] if len(sys.argv) > 1 else INPUT_FILE
    output_file = sys.argv[2] if len(sys.argv) > 2 else OUTPUT_FILE

    if not os.path.exists(input_file):
        print(f"[ERRO] Arquivo não encontrado: {input_file}")
        sys.exit(1)

    print(f"[INFO] Lendo {input_file}...")
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"[INFO] {len(data.get('data', {}))} moedas encontradas.")
    html = generate_html(data)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[OK] Dashboard gerado: {output_file}")


if __name__ == "__main__":
    main()
