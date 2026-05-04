// Lightweight toast system. Usage: window.toast.show({kind, title, message})
function ToastHost() {
  const [items, setItems] = React.useState([]);
  React.useEffect(() => {
    window.toast = {
      show: (t) => {
        const id = Math.random().toString(36).slice(2);
        setItems((prev) => [...prev, { id, ...t }]);
        const ttl = t.ttl || 4500;
        if (ttl > 0) setTimeout(() => setItems((prev) => prev.filter(x => x.id !== id)), ttl);
        return id;
      },
      dismiss: (id) => setItems((prev) => prev.filter(x => x.id !== id)),
    };
  }, []);
  return (
    <div style={{
      position:"fixed", right:20, bottom:20, zIndex:200,
      display:"flex", flexDirection:"column", gap:8, pointerEvents:"none",
    }}>
      {items.map(t => (
        <div key={t.id} style={{
          minWidth:280, maxWidth:380,
          background:"#fff",
          border:"1px solid var(--border)",
          borderLeft: `3px solid ${
            t.kind === "error" ? "#DC2626"
            : t.kind === "success" ? "#16A34A"
            : t.kind === "loading" ? "#534AB7"
            : "#6B6B73"
          }`,
          borderRadius: 8,
          boxShadow: "0 8px 24px rgba(16,16,20,0.10)",
          padding:"10px 12px",
          display:"flex", gap:10, alignItems:"flex-start",
          pointerEvents:"auto",
        }}>
          {t.kind === "loading" && <Spinner color="#534AB7" />}
          {t.kind === "success" && (
            <span style={{
              width:18,height:18,borderRadius:"50%",background:"var(--green-bg)",
              color:"var(--green)",display:"inline-flex",alignItems:"center",justifyContent:"center",
              flexShrink:0, marginTop:1,
            }}><Icons.Check size={11} stroke={2.6}/></span>
          )}
          {t.kind === "error" && (
            <span style={{
              width:18,height:18,borderRadius:"50%",background:"var(--red-bg)",
              color:"var(--red)",display:"inline-flex",alignItems:"center",justifyContent:"center",
              flexShrink:0, marginTop:1, fontSize:12, fontWeight:600,
            }}>!</span>
          )}
          <div style={{flex:1, minWidth:0}}>
            {t.title && <div style={{fontSize:13, fontWeight:500, color:"var(--text)"}}>{t.title}</div>}
            {t.message && <div style={{fontSize:12, color:"var(--text-muted)", marginTop:2}}>{t.message}</div>}
          </div>
          <button
            onClick={() => setItems(prev => prev.filter(x => x.id !== t.id))}
            style={{
              border:"none", background:"transparent", cursor:"pointer",
              color:"var(--text-subtle)", padding:2, borderRadius:4,
            }}
          ><Icons.X size={12}/></button>
        </div>
      ))}
    </div>
  );
}

function Spinner({ color = "#534AB7", size = 14 }) {
  return (
    <span style={{
      width:size, height:size, flexShrink:0, marginTop:2,
      border:`2px solid ${color}33`,
      borderTopColor: color,
      borderRadius:"50%",
      display:"inline-block",
      animation:"spin 700ms linear infinite",
    }}/>
  );
}

// inject keyframes once
if (typeof document !== "undefined" && !document.getElementById("__toast_kf")) {
  const s = document.createElement("style");
  s.id = "__toast_kf";
  s.textContent = "@keyframes spin{to{transform:rotate(360deg)}}";
  document.head.appendChild(s);
}

window.ToastHost = ToastHost;
window.Spinner = Spinner;
