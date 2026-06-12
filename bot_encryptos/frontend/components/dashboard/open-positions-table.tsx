import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatCurrency, minutesAgo } from "@/lib/utils"
import type { Position } from "@/lib/types"
import { AlphaBadge } from "@/components/ui/alpha-badge"

interface OpenPositionsTableProps {
  positions: Position[] | undefined
}

export function OpenPositionsTable({ positions }: OpenPositionsTableProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Posições Abertas</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {!positions ? (
          <div className="p-5 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-8 w-full animate-pulse rounded bg-[#2a2d3a]" aria-hidden="true" />
            ))}
          </div>
        ) : positions.length === 0 ? (
          <p className="p-5 text-sm text-[#6b7280]">Nenhuma posição aberta.</p>
        ) : (
          <Table aria-label="Posições abertas">
            <TableHeader>
              <TableRow>
                <TableHead>Símbolo</TableHead>
                <TableHead>Direção</TableHead>
                <TableHead>Entrada</TableHead>
                <TableHead>Valor</TableHead>
                <TableHead>Aberta há</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {positions.map((pos) => (
                <TableRow key={pos.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-medium">{pos.symbol}</span>
                      <AlphaBadge isAlpha={pos.is_alpha} />
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={pos.direction === "LONG" ? "success" : "danger"}>
                      {pos.direction}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono">{formatCurrency(pos.entry_price)}</TableCell>
                  <TableCell className="font-mono">{formatCurrency(pos.value)}</TableCell>
                  <TableCell className="text-[#6b7280]">
                    {minutesAgo(pos.open_timestamp)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
