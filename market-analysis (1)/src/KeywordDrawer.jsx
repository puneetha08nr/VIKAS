function KeywordDrawer({ keyword, onClose }) {
  if (!keyword) return null;
  const cluster = KW_CLUSTERS.find(c => c.id === keyword.cluster);

  const related = KEYWORDS
    .filter(k => k.cluster === keyword.cluster && k.id !== keyword.id)
    .slice(0, 4);

  const agentRuns = [
    { agent: "keyword_research", when: "2h ago", cost: 0.12, status: "success" },
    { agent: "keyword_validator", when: "1h ago", cost: 0.04, status: "success" },
    { agent: "gap_analyzer",     when: "10m ago", cost: 0.31, status: "success" },
  ];

  return (
    <React.Fragment>
      <div className={"drawer-backdrop" + (keyword ? " open" : "")} onClick={onClose}/>
      <div className={"drawer" + (keyword ? " open" : "")}>
        <div className="drawer-head">
          <div style={{display:"flex", justifyContent:"space-between", alignItems:"flex-start", gap:12}}>
            <div style={{minWidth:0, flex:1}}>
              <div style={{display:"flex", alignItems:"center", gap:8, marginBottom:6}}>
                {keyword.status === "clustered" && cluster ? (
                  <React.Fragment>
                    <span style={{width:8, height:8, borderRadius:2, background: cluster.color}}/>
                    <span style={{fontSize:12, color:"var(--text-muted)"}}>{cluster.name}</span>
                  </React.Fragment>
                ) : (
                  <span style={{fontSize:12, color:"var(--text-muted)"}}>Not yet clustered</span>
                )}
              </div>
              <h2 style={{margin:0, fontSize:18, fontWeight:600, letterSpacing:"-0.015em"}}>
                {keyword.keyword}
              </h2>
              <div style={{display:"flex", gap:6, marginTop:8, flexWrap:"wrap"}}>
                <StatusBadge status={keyword.status}/>
                <IntentBadge intent={keyword.intent}/>
                <DataSourceBadge source={keyword.data_source}/>
              </div>
            </div>
            <button className="icon-btn-link" onClick={onClose}><Icons.X size={16}/></button>
          </div>
        </div>

        <div className="drawer-body">
          <div className="stat-grid">
            <div className="stat-cell">
              <div className="l">Volume</div>
              <div className="v">{keyword.volume.toLocaleString()}<span style={{fontSize:11, color:"var(--text-muted)", fontWeight:500, marginLeft:4}}>/mo</span></div>
            </div>
            <div className="stat-cell">
              <div className="l">Difficulty</div>
              <div className="v" style={{display:"flex", alignItems:"center", gap:8}}>
                <Difficulty value={keyword.kd} />
              </div>
            </div>
            <div className="stat-cell">
              <div className="l">CPC</div>
              <div className="v">${keyword.cpc.toFixed(2)}</div>
            </div>
            <div className="stat-cell">
              <div className="l">Position</div>
              <div className="v">
                {keyword.position != null ? (
                  <PositionDelta pos={keyword.position} prev={keyword.prevPosition}/>
                ) : (
                  <span style={{color:"var(--text-subtle)", fontSize:14, fontWeight:500}}>Not ranking</span>
                )}
              </div>
            </div>
          </div>

          {keyword.reason && (
            <React.Fragment>
              <div className="section-title">Validator reasoning</div>
              <div style={{
                padding:"10px 12px",
                background:"var(--primary-50)",
                borderRadius:6,
                color:"var(--text)",
                fontSize:12.5,
                lineHeight:1.5,
                borderLeft:"2px solid var(--primary)",
              }}>
                {keyword.reason}
                <div style={{color:"var(--text-muted)", fontSize:11, marginTop:6}} className="mono">
                  via keyword_validator
                </div>
              </div>
            </React.Fragment>
          )}

          <div className="section-title">Search volume — last 12 months</div>
          <div style={{border:"1px solid var(--border)", borderRadius:6, padding:12}}>
            <Sparkline data={keyword.trend} width={400} height={64} color="#534AB7"/>
            <div style={{display:"flex", justifyContent:"space-between", marginTop:6, color:"var(--text-subtle)", fontSize:11}} className="mono">
              <span>May '25</span>
              <span>Apr '26</span>
            </div>
          </div>

          {keyword.url ? (
            <React.Fragment>
              <div className="section-title">Linked content</div>
              <div className="panel-list">
                <div className="panel-item">
                  <div style={{minWidth:0}}>
                    <div className="ttl">{keyword.url}</div>
                    <div className="sub">Ranking #{keyword.position} · {keyword.contentCount} piece{keyword.contentCount === 1 ? "" : "s"}</div>
                  </div>
                  <button className="icon-btn-link"><Icons.ExternalLink size={14}/></button>
                </div>
              </div>
            </React.Fragment>
          ) : keyword.status === "validated" || keyword.status === "clustered" ? (
            <React.Fragment>
              <div className="section-title">Next step</div>
              <div className="panel-item" style={{
                border:"1px dashed var(--border-strong)",
                background:"var(--primary-50)",
              }}>
                <div>
                  <div className="ttl" style={{color:"var(--primary)"}}>No content yet</div>
                  <div className="sub" style={{color:"var(--primary-600)"}}>Dispatch content_director to draft an article, LinkedIn post, and newsletter.</div>
                </div>
                <button className="btn btn-primary btn-sm">
                  <Icons.Sparkle size={13}/> Generate
                </button>
              </div>
            </React.Fragment>
          ) : null}

          <div className="section-title">Related in cluster</div>
          <div className="panel-list">
            {related.map(r => (
              <div className="panel-item" key={r.id}>
                <div style={{minWidth:0}}>
                  <div className="ttl truncate">{r.keyword}</div>
                  <div className="sub tabnum">{r.volume.toLocaleString()} vol · KD {r.kd.toFixed(1)} · ${r.cpc.toFixed(2)}</div>
                </div>
                <StatusBadge status={r.status}/>
              </div>
            ))}
          </div>

          <div className="section-title">Recent agent runs</div>
          <div className="panel-list">
            {agentRuns.map((r, i) => (
              <div className="panel-item" key={i}>
                <div>
                  <div className="ttl mono" style={{fontSize:12.5}}>{r.agent}</div>
                  <div className="sub">{r.when} · ${r.cost.toFixed(2)}</div>
                </div>
                <span className="badge green"><span className="badge-dot" style={{background:"#16A34A"}}/>{r.status}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="drawer-foot">
          <button className="btn btn-secondary btn-sm">
            <Icons.Pencil size={13}/> Edit
          </button>
          <div style={{display:"flex", gap:6}}>
            {keyword.status === "raw" && (
              <button className="btn btn-secondary btn-sm">
                <Icons.Check size={13}/> Validate
              </button>
            )}
            <button className="btn btn-primary btn-sm">
              <Icons.Sparkle size={13}/> Generate content
            </button>
          </div>
        </div>
      </div>
    </React.Fragment>
  );
}

window.KeywordDrawer = KeywordDrawer;
