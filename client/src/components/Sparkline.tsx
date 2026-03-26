interface Props {
  data: number[]
  width?: number
  height?: number
  color?: string
  min?: number
  max?: number
}

export function Sparkline({ data, width = 64, height = 16, color = '#3fb950', min = 0, max = 500 }: Props) {
  if (data.length < 2) return null

  const range = max - min || 1
  const step = width / (data.length - 1)

  const pts = data.map((v, i) => {
    const x = (i * step).toFixed(1)
    const y = Math.max(0, Math.min(height, height - ((v - min) / range) * height)).toFixed(1)
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={width} height={height} className="inline-block opacity-60 shrink-0">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}
