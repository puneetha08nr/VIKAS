'use client'

import { Sparkline } from './Sparkline'
import type { KeywordStats } from '@/lib/types'

interface KpiStripProps {
  stats: KeywordStats
  loading?: boolean
}

const SP_RAW = [3, 4, 5, 6, 6, 7, 8, 9, 10, 11, 12, 12]
const SP_VALIDATED = [120, 132, 128, 142, 138, 156, 168, 172, 165, 178, 184, 192]
const SP_CLUSTERED = [890, 920, 940, 980, 1020, 1080, 1100, 1140, 1180, 1220, 1260, 1290]
const SP_TOTAL = [9, 9, 10, 10, 11, 11, 11, 12, 12, 13, 13, 14]

export function KpiStrip({ stats, loading = false }: KpiStripProps) {
  const items = [
    {
      label: 'Raw',
      value: stats.raw,
      foot: stats.raw > 0 ? 'awaiting validation' : 'all caught up',
      spark: SP_RAW,
      sparkColor: '#9A9AA3',
    },
    {
      label: 'Validated',
      value: stats.validated,
      foot: 'ready for clustering',
      spark: SP_VALIDATED,
      sparkColor: '#534AB7',
      delta: null,
    },
    {
      label: 'Clustered',
      value: stats.clustered ?? 0,
      delta: 12,
      foot: 'active in pipeline',
      spark: SP_CLUSTERED,
      sparkColor: '#16A34A',
    },
    {
      label: 'Total',
      value: stats.total,
      foot: 'keywords tracked',
      spark: SP_TOTAL,
      sparkColor: '#0EA5E9',
    },
  ]

  return (
    <div className="grid grid-cols-4 gap-3 mb-5">
      {items.map((it) => (
        <div
          key={it.label}
          className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm"
        >
          <div className="flex justify-between items-start gap-2">
            <div className="min-w-0 flex-1">
              <div className="text-xs text-gray-500 font-medium mb-1">
                {it.label}
              </div>
              <div className="text-2xl font-semibold tabular-nums leading-none mb-1.5">
                {loading ? (
                  <span className="text-gray-300">—</span>
                ) : (
                  it.value.toLocaleString()
                )}
                {it.delta != null && (
                  <span className="text-xs font-medium ml-2 text-green-600">
                    ▲ {it.delta}%
                  </span>
                )}
              </div>
              <div className="text-xs text-gray-400">{it.foot}</div>
            </div>
            <div className="shrink-0 mt-1">
              <Sparkline data={it.spark} color={it.sparkColor} />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
