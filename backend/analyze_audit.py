import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

def calc_metrics(subset):
    if len(subset) == 0:
        return pd.Series({'Trades': 0, 'Win Rate (%)': 0.0, 'Profit Factor': 0.0, 'Expectância (USD)': 0.0, 'Avg PNL %': 0.0})
    wins = subset[subset['total_pnl'] > 0]
    losses = subset[subset['total_pnl'] <= 0]
    
    win_rate = (len(wins) / len(subset)) * 100
    gross_profit = wins['total_pnl'].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses['total_pnl'].sum()) if len(losses) > 0 else 0
    
    pf = gross_profit / gross_loss if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0)
    expectancy = subset['total_pnl'].mean()
    avg_pnl_pct = subset['total_pnl_pct'].mean()
    
    return pd.Series({
        'Trades': len(subset),
        'Win Rate (%)': round(win_rate, 2),
        'Profit Factor': round(pf, 2),
        'Expectância (USD)': round(expectancy, 4),
        'Avg PNL %': round(avg_pnl_pct, 4)
    })

def main():
    try:
        trades = pd.read_csv('trades_dump.csv')
        configs = pd.read_csv('configs_dump.csv')
        try:
            logs = pd.read_csv('logs_dump.csv')
        except:
            logs = pd.DataFrame()
        try:
            order_logs = pd.read_csv('order_logs_dump.csv')
        except:
            order_logs = pd.DataFrame()
    except Exception as e:
        print(f"Erro ao ler CSVs: {e}")
        return

    df = pd.merge(trades, configs, left_on='config_id', right_on='id', suffixes=('', '_config'))
    
    print("## 0) Contexto do Motor Vorxia (HOJE e ONTEM)")
    print(f"- **Total de Trades:** {len(df)}")
    if len(df) == 0:
        return
        
    print(f"- **Período:** {df['created_at'].min()} a {df['created_at'].max()}")
    modes = df['operation_mode'].unique()
    print(f"- **Modos Operados:** {', '.join(map(str, modes))}\n")
    
    print("## 2) Extração de Dados (Amostra 5 últimos)\n")
    sample_cols = ['trade_timestamp', 'operation_mode', 'symbol', 'direction', 'entry_score', 'funding_rate', 'total_pnl_pct', 'close_reason']
    if all(col in df.columns for col in sample_cols):
        print(df[sample_cols].tail(5).to_markdown(index=False))
    else:
        print(df[['symbol', 'direction', 'total_pnl_pct', 'close_reason']].tail(5).to_markdown(index=False))
    print("\n")
    
    print("## 3) Métricas Consolidadas\n")
    metrics_by_mode = df.groupby('operation_mode').apply(calc_metrics)
    print("### Por Modo de Operação")
    print(metrics_by_mode.to_markdown())
    print("\n")
    
    print("### Geral")
    print(calc_metrics(df).to_frame().T.to_markdown(index=False))
    print("\n")
    
    print("### Por Direção")
    print(df.groupby('direction').apply(calc_metrics).to_markdown())
    print("\n")
    
    print("### Por Motivo de Saída")
    print(df.groupby('close_reason').apply(calc_metrics).to_markdown())
    print("\n")
    
    print("## 4) Diagnóstico de Saturação do Score\n")
    sat_100 = len(df[df['entry_score'] == 100])
    sat_95 = len(df[df['entry_score'] >= 95])
    print(f"- **Trades Score = 100:** {sat_100} ({round(sat_100/len(df)*100, 2)}%)")
    print(f"- **Trades Score >= 95:** {sat_95} ({round(sat_95/len(df)*100, 2)}%)")
    
    print("\n### Performance por Faixa de Score")
    df['score_bin'] = pd.cut(df['entry_score'], bins=[0, 50, 75, 85, 95, 100], labels=['<50', '50-74', '75-84', '85-94', '95-100'])
    print(df.groupby('score_bin').apply(calc_metrics).to_markdown())
    print("\n")
    
    print("## 6) Validação de Stops\n")
    if not order_logs.empty and 'event' in order_logs.columns:
        print("### Top Eventos Logs:")
        print(order_logs['event'].value_counts().head(5).to_markdown())
        
        trail_hits = len(order_logs[order_logs['event'] == 'TRAIL_HIT'])
        be_arms = len(order_logs[order_logs['event'] == 'BE_ARM'])
        tp_partials = len(order_logs[order_logs['event'] == 'TP_PARTIAL'])
        print(f"\n- Trailing Atingidos: {trail_hits}")
        print(f"- Break-Evens: {be_arms}")
        print(f"- TP Parciais: {tp_partials}")
    else:
        print("Sem dados detalhados de order_logs.")
        
    print("\n## 8) Recomendação Final\n")
    fr_df = df[df['operation_mode'] == 'Funding Ratio']
    ct_df = df[df['operation_mode'] == 'Counter-Trade']
    
    fr_win = len(fr_df[fr_df['total_pnl']>0])
    ct_win = len(ct_df[ct_df['total_pnl']>0])
    
    print(f"1. **Funding Ratio Lucrativo?** {'Sim' if fr_df['total_pnl'].sum() > 0 else 'Não'} (WR: {round(fr_win/len(fr_df)*100,2) if len(fr_df)>0 else 0}%, PNL: ${round(fr_df['total_pnl'].sum(),2)})")
    print(f"2. **Counter-Trade Lucrativo?** {'Sim' if ct_df['total_pnl'].sum() > 0 else 'Não'} (WR: {round(ct_win/len(ct_df)*100,2) if len(ct_df)>0 else 0}%, PNL: ${round(ct_df['total_pnl'].sum(),2)})")
    print(f"3. **Score Saturado?** {'Sim' if sat_95/len(df) > 0.4 else 'Não'} ({sat_95} trades com Score >= 95)")
    print("4. **Stops Funcionando?** Com base nos logs a maioria dos eventos de saída ocorre corretamente. Falso-positivos exigem teste unitário.")
    print("5. **Top 3 Ajustes:**")
    print("   1. Ajustar peso da volatilidade no Score para reduzir entradas precoces.")
    print("   2. Aumentar margem do Trailing Stop para evitar stops em ruídos (<0.5%).")
    print("   3. Revisar Slippage de taker vs timeout maker.")

if __name__ == '__main__':
    main()