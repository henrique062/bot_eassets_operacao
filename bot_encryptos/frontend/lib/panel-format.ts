// Helpers de formatação e cores para o painel de moedas (metodologia
// Encryptos). Espelham as funções de gerar_painel.py para consistência visual.
// Tema escuro, alinhado ao restante do dashboard.

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

// Paleta (tema escuro do dashboard)
export const POS = "#4ade80" // green-400
export const NEG = "#f87171" // red-400
export const WARN = "#fbbf24" // amber-400
export const MUTED = "#6b7280" // gray-500
export const ACCENT = "#6366f1" // indigo

export function colorPN(v: number | null | undefined): string {
  if (v == null) return MUTED
  return v >= 0 ? POS : NEG
}

// Limiares de T/OI calibrados (iguais ao gerar_painel.py)
export const TOI_ATENCAO = 40000
export const TOI_FORTE = 68000

export function colorToi(v: number | null | undefined): string {
  if (v == null) return MUTED
  if (v >= TOI_FORTE) return "#c084fc" // roxo forte = SM focado
  if (v >= TOI_ATENCAO) return "#a78bfa"
  return MUTED
}

// Estilo do badge de setup (fundo translúcido + texto) por classe — tema escuro.
export function setupBadgeStyle(setup: string | null): { bg: string; color: string; border: string } {
  switch (setup) {
    case "ROBOS LIGADOS":
      return { bg: "rgba(52,211,153,0.12)", color: "#4ade80", border: "rgba(52,211,153,0.35)" }
    case "ROBOS ATIVO":
      return { bg: "rgba(56,189,248,0.12)", color: "#38bdf8", border: "rgba(56,189,248,0.35)" }
    case "FORÇA ESTRU":
      return { bg: "rgba(99,102,241,0.12)", color: "#818cf8", border: "rgba(99,102,241,0.35)" }
    case "ACUM 4H/1D":
      return { bg: "rgba(251,191,36,0.12)", color: "#fbbf24", border: "rgba(251,191,36,0.35)" }
    case "ESTRUTURA CONTRADITÓRIA":
    case "SHORT ENTRANDO":
      return { bg: "rgba(248,113,113,0.12)", color: "#f87171", border: "rgba(248,113,113,0.4)" }
    case "ACUM SILENCIOSA":
      return { bg: "rgba(192,132,252,0.12)", color: "#c084fc", border: "rgba(192,132,252,0.4)" }
    default:
      return { bg: "rgba(107,114,128,0.12)", color: "#9ca3af", border: "#2a2d3a" }
  }
}
