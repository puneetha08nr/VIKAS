function Sparkline({ data, width = 84, height = 24, color = "#534AB7", filled = true }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const stepX = width / (data.length - 1);
  const points = data.map((v, i) => {
    const x = i * stepX;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return [x, y];
  });
  const path = points.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(" ");
  const area = `${path} L${width},${height} L0,${height} Z`;
  const last = points[points.length - 1];
  return (
    <svg width={width} height={height} style={{display:"block"}}>
      {filled ? <path d={area} fill={color} fillOpacity="0.10" /> : null}
      <path d={path} fill="none" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
      <circle cx={last[0]} cy={last[1]} r="1.8" fill={color}/>
    </svg>
  );
}

function KpiSparkArea({ data, color }) {
  return <Sparkline data={data} width={84} height={28} color={color} />;
}

function KpiStrip({ items }) {
  return (
    <div className="kpi-strip">
      {items.map((it, i) => (
        <div className="kpi-card" key={i}>
          <div style={{display:"flex", justifyContent:"space-between", alignItems:"flex-start"}}>
            <div style={{minWidth:0, flex:1}}>
              <div className="kpi-label">{it.icon}{it.label}</div>
              <div className="kpi-value tabnum">
                {it.value}
                {it.delta != null ? (
                  <span className={"kpi-delta " + (it.delta >= 0 ? "up" : "down")}>
                    {it.delta >= 0 ? "▲" : "▼"} {Math.abs(it.delta)}{it.deltaSuffix || "%"}
                  </span>
                ) : null}
              </div>
              <div className="kpi-foot">{it.foot}</div>
            </div>
            {it.spark ? <KpiSparkArea data={it.spark} color={it.sparkColor || "#534AB7"} /> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

window.Sparkline = Sparkline;
window.KpiStrip = KpiStrip;
