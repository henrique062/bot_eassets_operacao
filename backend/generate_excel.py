import pandas as pd
import numpy as np
import json

def main():
    try:
        trades = pd.read_csv('trades_dump.csv')
        configs = pd.read_csv('configs_dump.csv')
    except:
        print("Erro: CSVs não encontrados.")
        return

    # Merge para ter os parâmetros originais
    df = pd.merge(trades, configs, left_on='config_id', right_on='id', suffixes=('', '_cfg'))
    
    # 1. ABA: Operações Reais
    aba_real = df[['created_at', 'symbol', 'operation_mode', 'direction', 'entry_score', 
                   'entry_price', 'exit_price', 'total_pnl', 'total_pnl_pct', 'close_reason']].copy()
    aba_real.columns = ['Data/Hora', 'Símbolo', 'Modo', 'L/S', 'Score Entrada', 
                        'Preço Entrada', 'Preço Saída', 'PNL (USD)', 'PNL %', 'Motivo Saída']

    # 2. ABA: Projeções de Configuração (Simulação)
    # Vamos simular 3 cenários baseados nos trades reais:
    
    projs = []
    for _, row in df.iterrows():
        pnl_base = row['total_pnl']
        pnl_pct_base = row['total_pnl_pct']
        leverage_atual = row['leverage']
        
        # Cenário A: Alavancagem Conservadora (5x) e Somente Maker
        # (Ajustamos o PNL proporcionalmente à alavancagem)
        fator_lev = 5 / leverage_atual if leverage_atual > 0 else 1
        pnl_cenario_a = pnl_base * fator_lev
        
        # Cenário B: Alavancagem Agressiva (20x)
        fator_lev_b = 20 / leverage_atual if leverage_atual > 0 else 1
        pnl_cenario_b = pnl_base * fator_lev_b
        
        # Cenário C: Filtro de Qualidade (Apenas se Score >= 80)
        # Se o score for menor, o lucro seria 0 (não entrou)
        score = row['entry_score'] if not pd.isna(row['entry_score']) else 0
        pnl_cenario_c = pnl_base if score >= 80 else 0

        projs.append({
            'Símbolo': row['symbol'],
            'Score': score,
            'PNL Real (USD)': pnl_base,
            'PNL Real (%)': pnl_pct_base,
            'Proj 5x Lev (USD)': pnl_cenario_a,
            'Proj 20x Lev (USD)': pnl_cenario_b,
            'Proj Score > 80 (USD)': pnl_cenario_c,
            'Modo': row['operation_mode']
        })
    
    aba_projs = pd.DataFrame(projs)

    # 3. ABA: Resumo Comparativo
    resumo_data = {
        'Cenário': ['Real (Atual)', 'Conservador (5x Lev)', 'Agressivo (20x Lev)', 'Filtro Score > 80'],
        'Lucro Total (USD)': [
            aba_projs['PNL Real (USD)'].sum(),
            aba_projs['Proj 5x Lev (USD)'].sum(),
            aba_projs['Proj 20x Lev (USD)'].sum(),
            aba_projs['Proj Score > 80 (USD)'].sum()
        ],
        'Win Rate (%)': [
            (len(aba_projs[aba_projs['PNL Real (USD)'] > 0]) / len(aba_projs)) * 100,
            (len(aba_projs[aba_projs['Proj 5x Lev (USD)'] > 0]) / len(aba_projs)) * 100,
            (len(aba_projs[aba_projs['Proj 20x Lev (USD)'] > 0]) / len(aba_projs)) * 100,
            (len(aba_projs[aba_projs['Proj Score > 80 (USD)'] > 0]) / len(aba_projs[aba_projs['Proj Score > 80 (USD)'] != 0])) * 100 if len(aba_projs[aba_projs['Proj Score > 80 (USD)'] != 0]) > 0 else 0
        ]
    }
    aba_resumo = pd.DataFrame(resumo_data)

    # Gerar o arquivo Excel
    with pd.ExcelWriter('ANALISE GEMINI - MOEDAS.xlsx', engine='openpyxl') as writer:
        aba_resumo.to_excel(writer, sheet_name='RESUMO_EXECUTIVO', index=False)
        aba_real.to_excel(writer, sheet_name='OPERACOES_REAIS', index=False)
        aba_projs.to_excel(writer, sheet_name='PROJECOES_E_CENARIOS', index=False)

    print("Planilha 'ANALISE GEMINI - MOEDAS.xlsx' gerada com sucesso.")

if __name__ == '__main__':
    main()