import type { Metadata } from "next"
import "./globals.css"
import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"

export const metadata: Metadata = {
  title: "Phoenix Bot",
  description: "Dashboard de trading bot Encryptos",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className="dark">
      <body className="bg-[#0f1117] text-white">
        <div className="flex min-h-screen">
          <Sidebar />
          <div className="flex flex-col flex-1 min-w-0">
            <Header />
            <main className="flex-1 p-5 overflow-auto">{children}</main>
          </div>
        </div>
      </body>
    </html>
  )
}
