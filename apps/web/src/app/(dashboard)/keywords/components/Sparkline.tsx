'use client'

interface SparklineProps {
  data: number[]
  width?: number
  height?: number
  color?: string
  filled?: boolean
}

export function Sparkline({
  data,
  width = 84,
  height = 24,
  color = '#534AB7',
  filled = true,
}: SparklineProps) {
  if (!data || data.length < 2) return null
  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const stepX = width / (data.length - 1)
  const points = data.map((v, i) => {
    const x = i * stepX
    const y = height - ((v - min) / range) * (height - 4) - 2
    return [x, y] as [number, number]
  })
  const path = points
    .map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`))
    .join(' ')
  const area = `${path} L${width},${height} L0,${height} Z`
  const last = points[points.length - 1]
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      {filled && (
        <path d={area} fill={color} fillOpacity="0.10" />
      )}
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={last[0]} cy={last[1]} r="1.8" fill={color} />
    </svg>
  )
}
