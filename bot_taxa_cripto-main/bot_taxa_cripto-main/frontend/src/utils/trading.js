/**
 * Utilitários de cálculo compartilhados entre componentes de trading.
 */

/**
 * Deriva a margem de entrada de uma operação a partir de diferentes combinações
 * de campos disponíveis, em ordem de confiabilidade decrescente:
 *   1. entryMargin direto (mais confiável)
 *   2. notional / leverage
 *   3. totalPnl / totalPnlPct (inverso do percentual)
 *   4. pricePnl / pricePnlPct (fallback extra)
 *
 * Retorna null quando não há dados suficientes para derivar.
 */
export function deriveEntryMargin({ entryMargin, notional, leverage, totalPnl, totalPnlPct, pricePnl, pricePnlPct }) {
    const directMargin = Number(entryMargin);
    if (Number.isFinite(directMargin) && directMargin > 0) return directMargin;

    const notionalNum = Number(notional);
    const levNum = Number(leverage);
    if (Number.isFinite(notionalNum) && notionalNum > 0) {
        if (Number.isFinite(levNum) && levNum > 0) return notionalNum / levNum;
        return notionalNum;
    }

    const pnlNum = Number(totalPnl);
    const pnlPctNum = Number(totalPnlPct);
    if (Number.isFinite(pnlNum) && Number.isFinite(pnlPctNum) && Math.abs(pnlPctNum) > 1e-9) {
        return Math.abs(pnlNum / (pnlPctNum / 100));
    }

    const pricePnlNum = Number(pricePnl);
    const pricePnlPctNum = Number(pricePnlPct);
    if (Number.isFinite(pricePnlNum) && Number.isFinite(pricePnlPctNum) && Math.abs(pricePnlPctNum) > 1e-9) {
        return Math.abs(pricePnlNum / (pricePnlPctNum / 100));
    }

    return null;
}
