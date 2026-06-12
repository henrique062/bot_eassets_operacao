"use client"

import { use } from "react"
import Link from "next/link"
import useSWR from "swr"
import { ArrowLeft } from "lucide-react"
import { api } from "@/lib/api"
import { PanelView } from "@/components/panel/panel-view"

export default function SnapshotPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const snapId = Number(id)

  const { data, error, isLoading } = useSWR(
    snapId ? `panel-snapshot-${snapId}` : null,
    () => api.getPanelSnapshot(snapId),
    { revalidateOnFocus: false }
  )

  return (
    <div className="flex flex-col gap-4">
      <Link
        href="/analise"
        className="flex w-fit items-center gap-2 text-sm font-semibold text-[#6366f1] hover:underline"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Voltar ao painel atual
      </Link>
      {data?.meta?.timestamp_brt && (
        <p className="text-sm text-[#9ca3af]">
          Snapshot de <span className="font-semibold text-[#f3f4f6]">{data.meta.timestamp_brt}</span>
        </p>
      )}
      <PanelView data={data} error={error} isLoading={isLoading} />
    </div>
  )
}
