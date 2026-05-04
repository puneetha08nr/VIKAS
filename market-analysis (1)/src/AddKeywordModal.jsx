function AddKeywordModal({ open, onClose, onAdd, busy }) {
  const [seed, setSeed] = React.useState("");

  React.useEffect(() => {
    if (!open) setSeed("");
  }, [open]);

  const submit = () => {
    if (!seed.trim() || busy) return;
    onAdd({ seed_keyword: seed.trim() });
  };

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit();
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className={"modal-backdrop" + (open ? " open" : "")} onClick={() => !busy && onClose()}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Research keywords</h2>
          <p>POSTs to <span className="mono">/api/v1/keywords/research</span>. Returns ~10 new keywords as <strong>raw</strong>.</p>
        </div>
        <div className="modal-body">
          <div className="field">
            <label>Seed keyword</label>
            <input
              className="input"
              placeholder="e.g. ai marketing automation"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              autoFocus
              disabled={busy}
            />
            <div className="hint">Suggestions from your knowledge base:</div>
            <div className="suggest-row">
              {AI_SUGGESTIONS.map(s => (
                <button key={s} className="suggest-pill" onClick={() => setSeed(s)} disabled={busy}>
                  <Icons.Sparkle size={11}/> {s}
                </button>
              ))}
            </div>
          </div>

          <div style={{
            padding:"10px 12px",
            border:"1px solid var(--border)",
            borderRadius:6,
            background:"#FAFAFB",
            fontSize:12.5,
            color:"var(--text-muted)",
          }}>
            <div style={{fontWeight:500, color:"var(--text)", fontSize:13}}>What happens next</div>
            <ol style={{margin:"6px 0 0 18px", padding:0, lineHeight:1.6}}>
              <li><span className="mono">keyword_research</span> agent expands seed → ~10 raw keywords</li>
              <li>You then run <span className="mono">keyword_validator</span> → validated or archived</li>
              <li><span className="mono">gap_analyzer</span> groups validated → clusters</li>
            </ol>
          </div>
        </div>
        <div className="modal-foot">
          <div style={{color:"var(--text-muted)", fontSize:12, alignSelf:"center"}}>
            <span className="mono">⌘ ↵</span> to submit
          </div>
          <div style={{display:"flex", gap:8}}>
            <button className="btn btn-secondary btn-sm" onClick={onClose} disabled={busy}>Cancel</button>
            <button className="btn btn-primary btn-sm" onClick={submit} disabled={!seed.trim() || busy}>
              {busy ? <React.Fragment><Spinner size={12} color="#fff"/> Researching…</React.Fragment>
                    : <React.Fragment><Icons.Sparkle size={13}/> Run keyword_research</React.Fragment>}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

window.AddKeywordModal = AddKeywordModal;
