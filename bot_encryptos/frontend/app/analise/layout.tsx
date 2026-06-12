import { Inter } from "next/font/google"
import { PanelTabs } from "@/components/panel/panel-tabs"

const inter = Inter({ subsets: ["latin"], display: "swap" })

// Seção de análise manual — identidade visual própria (guia de estilo: tema
// claro, fonte Inter, escala de cinzas, espaçamentos múltiplos de 4).
export default function AnaliseLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      className={`${inter.className} -m-5 min-h-[calc(100vh-57px)] bg-[#F9FAFB] p-6 text-[#475467]`}
    >
      <div className="mx-auto flex max-w-[1400px] flex-col gap-6">
        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold text-[#344054]">Análise Manual</h1>
          <p className="text-sm text-[#667085]">
            Metodologia Encryptos · visualização das moedas sem operar com o bot
          </p>
        </header>

        <PanelTabs />

        {children}
      </div>
    </div>
  )
}
