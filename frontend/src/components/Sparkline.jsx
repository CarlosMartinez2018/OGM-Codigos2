// Mini-grafico SVG de barras a partir de un arreglo de numeros (0..max).
export default function Sparkline({ data = [], className = '' }) {
  const max = Math.max(1, ...data)
  return (
    <svg viewBox={`0 0 ${data.length * 4} 16`} className={className} preserveAspectRatio="none">
      {data.map((v, i) => (
        <rect key={i} x={i * 4} y={16 - (v / max) * 16} width="3" height={(v / max) * 16} rx="0.5" fill="currentColor" />
      ))}
    </svg>
  )
}
