import os

def replace_in_file(src, dst, replacements):
    with open(src, 'r', encoding='utf-8') as f:
        content = f.read()
    for old, new in replacements:
        content = content.replace(old, new)
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(content)

src_dir = r"d:\3 - Projetos investimentos\bot_taxa_cripto\frontend\src\components"

replacements_page = [
    ("PaperTrading", "RealTrading"),
    ("paper-trading", "real-trading"),
    ("Paper Trading", "Conta Real (Live)"),
    ("PaperTradingPage", "RealTradingPage"),
    ("Simulação em Tempo Real", "Execução em Tempo Real"),
]

replace_in_file(
    os.path.join(src_dir, "PaperTradingPage.jsx"),
    os.path.join(src_dir, "RealTradingPage.jsx"),
    replacements_page
)

replacements_comp = [
    ("PaperTrading", "RealTrading"),
    ("paper-trading", "real-trading"),
    ("paper_config", "real_config"),
    ("Paper Trading", "Conta Real (Live)"),
]

replace_in_file(
    os.path.join(src_dir, "PaperTrading.jsx"),
    os.path.join(src_dir, "RealTrading.jsx"),
    replacements_comp
)

print("Files cloned and modified.")
