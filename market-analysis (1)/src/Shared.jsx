// Shared bits: ScoreBar, FormatChip, page Card layout
function ScoreBar({ value, label }) {
  const pct = Math.round(value * 100);
  const color = pct >= 85 ? "#16A34A" : pct >= 70 ? "#D97706" : "#DC2626";
  return (
    <span style={{display:"inline-flex", alignItems:"center", gap:6, fontSize:12}}>
      <span style={{
        width:48, height:4, borderRadius:999, background:"#EDEDF0", overflow:"hidden",
      }}>
        <span style={{display:"block", width: pct + "%", height:"100%", background: color, borderRadius:999}}/>
      </span>
      <span className="tabnum" style={{color:"var(--text)", fontVariantNumeric:"tabular-nums"}}>{pct}</span>
      {label ? <span style={{color:"var(--text-subtle)", fontSize:11}}>{label}</span> : null}
    </span>
  );
}

const FORMAT_LABELS = {
  article:    { label: "Article",    color: "#534AB7" },
  linkedin:   { label: "LinkedIn",   color: "#0A66C2" },
  twitter:    { label: "Twitter/X",  color: "#0F1419" },
  newsletter: { label: "Newsletter", color: "#D97706" },
  video:      { label: "Video",      color: "#DC2626" },
  lead_magnet:{ label: "Lead Magnet",color: "#0EA5E9" },
};
function FormatChip({ format }) {
  const f = FORMAT_LABELS[format] || { label: format, color: "#6B6B73" };
  return (
    <span style={{
      display:"inline-flex", alignItems:"center", gap:5,
      fontSize:11, color:"var(--text)",
      padding:"1px 7px", borderRadius:999,
      background:"#F1F1F4",
    }}>
      <span style={{width:6, height:6, borderRadius:"50%", background:f.color}}/>
      {f.label}
    </span>
  );
}

function ContentStatusBadge({ status }) {
  const map = {
    draft:     { cls:"neutral", label:"Draft",    dot:"#9A9AA3" },
    review:    { cls:"amber",   label:"Review",   dot:"#D97706" },
    approved:  { cls:"purple",  label:"Approved", dot:"#534AB7" },
    published: { cls:"green",   label:"Published",dot:"#16A34A" },
  };
  const m = map[status] || map.draft;
  return <span className={"badge " + m.cls}><span className="badge-dot" style={{background:m.dot}}/>{m.label}</span>;
}

function PageCard({ title, subtitle, action, children, padding = true }) {
  return (
    <div style={{
      background:"#fff",
      border:"1px solid var(--border)",
      borderRadius:8,
      marginBottom: 16,
      overflow:"hidden",
    }}>
      {(title || action) && (
        <div style={{
          padding:"12px 16px",
          borderBottom: children ? "1px solid var(--border)" : "0",
          display:"flex", alignItems:"center", justifyContent:"space-between", gap:12,
        }}>
          <div>
            {title && <div style={{fontSize:14, fontWeight:600}}>{title}</div>}
            {subtitle && <div style={{fontSize:12, color:"var(--text-muted)", marginTop:2}}>{subtitle}</div>}
          </div>
          {action}
        </div>
      )}
      <div style={padding ? {padding:"14px 16px"} : {}}>{children}</div>
    </div>
  );
}

window.ScoreBar = ScoreBar;
window.FormatChip = FormatChip;
window.ContentStatusBadge = ContentStatusBadge;
window.PageCard = PageCard;
