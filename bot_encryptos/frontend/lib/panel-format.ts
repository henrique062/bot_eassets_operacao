// Helpers de formatação e cores para o painel de análise manual (metodologia
// Encryptos). Espelham as funções de gerar_painel.py para consistência visual.

export function fmtPrice(p: number | null | undefined): string {
  if (p == null) return "—"
  if (p >= 100) return `$${p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  if (p >= 1) return `$${p.toFixed(4)}`
  return `$${p.toFixed(5)}`
}

export function fmtUsd(v: number | null | undefined): string {
  if (v == null) return "—"
  const units: [number, string][] = [[1e9, "B"], [1e6, "M"], [1e3, "K"]]
  for (const [div, suf] of units) {
    if (v >= div) return `$${(v / div).toFixed(1)}${suf}`
  }
  return `$${v.toFixed(0)}`
}

export function fmtCompact(v: number | null | undefined): string {
  if (v == null) return "—"
  const units: [number, string][] = [[1e9, "B"], [1e6, "M"], [1e3, "K"]]
  for (const [div, suf] of units) {
    if (Math.abs(v) >= div) return `${(v / div).toFixed(1)}${suf}`
  }
  return `${v.toFixed(0)}`
}

export function fmtNum(
  v: number | null | undefined,
  dec = 2,
  plus = false
): string {
  if (v == null) return "—"
  const s = v.toFixed(dec)
  return plus && v >= 0 ? `+${s}` : s
}

// Cor de texto para valores positivos/negativos (paleta do guia de estilo).
export const POS = "#039855" // Verde 600
export const NEG = "#D92D20" // Vermelho 600
export const WARN = "#DC6803" // Laranja 600
export const MUTED = "#98A2B3" // Cinza 400

export function colorPN(v: number | null | undefined): string {
  if (v == null) return MUTED
  return v >= 0 ? POS : NEG
}

// Limiares de T/OI calibrados (iguais ao gerar_painel.py)
export const TOI_ATENCAO = 40000
export const TOI_FORTE = 68000

export function colorToi(v: number | null | undefined): string {
  if (v == null) return MUTED
  if (v >= TOI_FORTE) return "#7F56D9" // roxo forte = SM focado
  if (v >= TOI_ATENCAO) return "#9E77ED"
  return MUTED
}

// Estilo do badge de setup (fundo + texto) por classe.
export function setupBadgeStyle(setup: string | null): { bg: string; color: string; border: string } {
  switch (setup) {
    case "ROBOS LIGADOS":
      return { bg: "#ECFDF3", color: "#027A48", border: "#A6F4C5" }
    case "ROBOS ATIVO":
      return { bg: "#EFF8FF", color: "#175CD3", border: "#B2DDFF" }
    case "FORÇA ESTRU":
      return { bg: "#EFF8FF", color: "#1849A9", border: "#B2DDFF" }
    case "ACUM 4H/1D":
      return { bg: "#FFFAEB", color: "#B54708", border: "#FEDF89" }
    case "ESTRUTURA CONTRADITÓRIA":
    case "SHORT ENTRANDO":
      return { bg: "#FEF3F2", color: "#B42318", border: "#FECDCA" }
    case "ACUM SILENCIOSA":
      return { bg: "#F4F3FF", color: "#5925DC", border: "#D9D6FE" }
    default:
      return { bg: "#F2F4F7", color: "#475467", border: "#EAECF0" }
  }
}
