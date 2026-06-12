import { PanelTabs } from "@/components/panel/panel-tabs"

// Painel de Moedas — análise da metodologia Encryptos (mesmo tema escuro do
// restante do dashboard).
export default function AnaliseLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-4">
      <PanelTabs />
      {children}
    </div>
  )
}
