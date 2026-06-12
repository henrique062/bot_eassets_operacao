"use client"

import useSWR from "swr"
import { api } from "@/lib/api"
import { PanelView } from "@/components/panel/panel-view"

export default function PainelPage() {
  const { data, error, isLoading } = useSWR("panel-latest", api.getPanelLatest, {
    refreshInterval: 60_000,
    revalidateOnFocus: false,
  })
  const { data: snapshots } = useSWR("panel-snapshots", api.getPanelSnapshots, {
    revalidateOnFocus: false,
  })

  const selector = (
    <div className="flex flex-col justify-between gap-2 rounded-2xl border border-[#EAECF0] bg-white px-5 py-4 shadow-[0_8px_24px_rgba(16,24,40,0.06)] lg:w-72">
      <label htmlFor="snap" className="text-sm font-semibold text-[#344054]">
        Snapshot
      </label>
      <select
        id="snap"
        defaultValue=""
        onChange={(e) => {
          if (e.target.value) window.location.href = `/analise/snapshot/${e.target.value}`
        }}
        className="h-10 w-full rounded-lg border border-[#D0D5DD] bg-white px-3 text-sm text-[#475467] outline-none focus:border-[#6366f1]"
      >
        <option value="">
          {data?.meta?.timestamp_brt ? `Atual · ${data.meta.timestamp_brt}` : "Último"}
        </option>
        {snapshots?.map((s) => (
          <option key={s.id} value={s.id}>
            {s.timestamp_brt} · {s.symbols ?? "—"} ativos
          </option>
        ))}
      </select>
      <span className="text-xs text-[#667085]">
        {snapshots?.length ?? 0} snapshots no histórico
      </span>
    </div>
  )

  return <PanelView data={data} error={error} isLoading={isLoading} selector={selector} />
}
