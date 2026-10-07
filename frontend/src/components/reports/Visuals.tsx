
// Defined at module scope so React keeps the same component identity between renders

export const Sparkline = ({ points }: { points: number[] }) => {
  if (!points || points.length === 0) return null;
  const maxVal = Math.max(...points);
  const minVal = Math.min(...points);
  const range = maxVal - minVal || 1;
  const width = 80;
  const height = 24;
  const padding = 2;

  const coordinates = points.map((p, idx) => {
    const x = (idx / (points.length - 1)) * (width - padding * 2) + padding;
    const y = height - ((p - minVal) / range) * (height - padding * 2) - padding;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        fill="none"
        stroke="#0052cc"
        strokeWidth="1.5"
        points={coordinates}
      />
    </svg>
  );
};

export const BarcodeSVG = ({ value }: { value: string }) => {
  const code = value || '8901072007823';
  const lines = [];
  let currentX = 10;
  for (let i = 0; i < code.length * 3; i++) {
    const width = (i % 3 === 0) ? 2 : ((i % 5 === 0) ? 4 : 1);
    const color = (i % 2 === 0) ? '#000000' : 'transparent';
    lines.push(
      <rect key={i} x={currentX} y="2" width={width} height="32" fill={color} />
    );
    currentX += width;
  }
  return (
    <div className="flex flex-col items-center">
      <svg width={currentX + 10} height="44" className="overflow-visible">
        {lines}
        <text x={currentX / 2} y="42" fontSize="7" textAnchor="middle" fill="#5c5f60" fontFamily="monospace">{code}</text>
      </svg>
    </div>
  );
};
