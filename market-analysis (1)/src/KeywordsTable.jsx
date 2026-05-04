function StatusBadge({ status }) {
  const map = {
    raw:        { cls: "neutral", label: "Raw",        dot: "#9A9AA3" },
    validated:  { cls: "purple",  label: "Validated",  dot: "#534AB7" },
    clustered:  { cls: "green",   label: "Clustered",  dot: "#16A34A" },
    archived:   { cls: "neutral", label: "Archived",   dot: "#6B6B73" },
  };
  const m = map[status] || map.raw;
  return (
    <span className={"badge " + m.cls} style={status === "archived" ? {opacity: 0.7} : null}>
      <span className="badge-dot" style={{background: m.dot}} />
      {m.label}
    </span>
  );
}

// Intent color spec:
// commercial=green, informational=blue, transactional=amber, navigational=gray
function IntentBadge({ intent }) {
  const map = {
    commercial:    "green",
    informational: "blue",
    transactional: "amber",
    navigational:  "neutral",
  };
  const cls = map[intent] || "neutral";
  const label = intent.charAt(0).toUpperCase() + intent.slice(1);
  return <span className={"badge " + cls}>{label}</span>;
}

// data_source: dataforseo (real) or llm_estimate (gray)
function DataSourceBadge({ source }) {
  if (source === "dataforseo") {
    return (
      <span className="badge green" title="Live data from DataForSEO">
        <span className="badge-dot" style={{background:"#16A34A"}}/>
        Real
      </span>
    );
  }
  return (
    <span className="badge neutral" title="LLM-generated estimate, pending validation">
      <span className="badge-dot" style={{background:"#9A9AA3"}}/>
      Estimate
    </span>
  );
}

// KD on 0–10 scale
// 0–4 green, 5–7 amber, 8–10 red
function Difficulty({ value }) {
  const cls = value <= 4 ? "kd-low" : value <= 7 ? "kd-mid" : "kd-high";
  const pct = Math.min(100, Math.max(4, value * 10));
  return (
    <span className="kd">
      <span className={"kd-bar " + cls}><span style={{width: pct + "%"}}/></span>
      <span className="tabnum">{value.toFixed(1)}</span>
    </span>
  );
}

function Check({ state, onClick }) {
  return (
    <span
      className={"ck " + (state === "checked" ? "checked" : state === "indet" ? "indet" : "")}
      onClick={(e) => { e.stopPropagation(); onClick && onClick(); }}
    >
      {state === "checked" ? <Icons.Check size={11} stroke={2.4}/> :
       state === "indet"   ? <Icons.Minus size={11} stroke={2.4}/> : null}
    </span>
  );
}

function PositionDelta({ pos, prev }) {
  if (pos == null) return <span style={{color: "var(--text-subtle)"}}>—</span>;
  const delta = prev != null ? prev - pos : 0;
  return (
    <span style={{display:"inline-flex", alignItems:"center", gap:6}}>
      <span className="tabnum" style={{fontWeight:500}}>#{pos}</span>
      {delta !== 0 && (
        <span className="tabnum" style={{
          fontSize: 11,
          color: delta > 0 ? "var(--green)" : "var(--red)",
          fontWeight: 500,
        }}>
          {delta > 0 ? "▲" : "▼"}{Math.abs(delta)}
        </span>
      )}
    </span>
  );
}

function KeywordsTable({ rows, selected, onToggle, onToggleAll, onOpen, density, sparkStyle, tableRef }) {
  const allChecked = rows.length > 0 && rows.every(r => selected.has(r.id));
  const anyChecked = rows.some(r => selected.has(r.id));
  const allState = allChecked ? "checked" : anyChecked ? "indet" : "none";

  const sparkColor = (r) => {
    const last = r.trend[r.trend.length - 1];
    const first = r.trend[0];
    if (last > first * 1.04) return "#16A34A";
    if (last < first * 0.96) return "#DC2626";
    return "#534AB7";
  };

  return (
    <div className={"table-wrap" + (density === "compact" ? " compact" : "")} ref={tableRef}>
      <table className="kw">
        <thead>
          <tr>
            <th className="col-checkbox">
              <Check state={allState} onClick={onToggleAll} />
            </th>
            <th className="sortable">Keyword</th>
            <th>Source</th>
            <th>Status</th>
            <th>Intent</th>
            <th className="col-num sortable">Volume</th>
            <th className="sortable">KD</th>
            <th className="col-num sortable">CPC</th>
            <th>Position</th>
            <th className="col-spark">12-mo trend</th>
            <th className="col-actions"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => {
            const cluster = KW_CLUSTERS.find(c => c.id === r.cluster);
            const isSel = selected.has(r.id);
            return (
              <tr key={r.id} className={isSel ? "selected" : ""} onClick={() => onOpen(r)}>
                <td className="col-checkbox">
                  <Check state={isSel ? "checked" : "none"} onClick={() => onToggle(r.id)} />
                </td>
                <td>
                  <div className="kw-name">{r.keyword}</div>
                  <div className="kw-meta">
                    {r.status === "clustered" && cluster ? (
                      <span style={{display:"inline-flex", alignItems:"center", gap:5}}>
                        <span style={{width: 6, height: 6, borderRadius: 1.5, background: cluster.color, display:"inline-block"}}/>
                        {cluster.name}
                      </span>
                    ) : r.contentCount > 0 ? `${r.contentCount} content piece${r.contentCount === 1 ? "" : "s"}` : "No content yet"}
                    {" · "}<span className="mono">{r.source_agent}</span>
                  </div>
                </td>
                <td><DataSourceBadge source={r.data_source}/></td>
                <td><StatusBadge status={r.status} /></td>
                <td><IntentBadge intent={r.intent} /></td>
                <td className="col-num tabnum">{r.volume.toLocaleString()}</td>
                <td><Difficulty value={r.kd} /></td>
                <td className="col-num tabnum">${r.cpc.toFixed(2)}</td>
                <td><PositionDelta pos={r.position} prev={r.prevPosition}/></td>
                <td className="col-spark">
                  <Sparkline data={r.trend} color={sparkColor(r)} filled={sparkStyle !== "line"} />
                </td>
                <td className="col-actions">
                  <button className="row-actions" onClick={(e) => e.stopPropagation()}>
                    <Icons.MoreH size={14}/>
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {rows.length === 0 && (
        <div className="empty">
          <div style={{display:"inline-flex", padding:10, borderRadius:10, background:"var(--primary-50)", color:"var(--primary)"}}>
            <Icons.Tag size={20}/>
          </div>
          <h3>No keywords match your filters</h3>
          <p>Try clearing filters, or let the keyword_research agent surface fresh opportunities.</p>
        </div>
      )}
    </div>
  );
}

window.KeywordsTable = KeywordsTable;
window.StatusBadge = StatusBadge;
window.IntentBadge = IntentBadge;
window.DataSourceBadge = DataSourceBadge;
window.Difficulty = Difficulty;
window.PositionDelta = PositionDelta;
