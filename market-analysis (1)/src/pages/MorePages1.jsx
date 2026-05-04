function CompetitorsPage() {
  const [open, setOpen] = React.useState(null);
  return (
    <React.Fragment>
      <Topbar
        title="Competitors"
        subtitle="competitor_monitor crawls these domains nightly. Threat scores from threat_scorer."
        actions={
          <React.Fragment>
            <button className="btn btn-secondary btn-sm"><Icons.Refresh size={13}/> Crawl now</button>
            <button className="btn btn-primary"><Icons.Plus size={14}/> Add competitor</button>
          </React.Fragment>
        }
      />
      <div className="page">
        <div style={{display:"grid", gridTemplateColumns:"repeat(4, 1fr)", gap:12, marginBottom:20}}>
          <div className="kpi-card">
            <div className="kpi-label"><Icons.Users size={13}/>Tracked domains</div>
            <div className="kpi-value tabnum">{COMPETITORS.length}</div>
            <div className="kpi-foot">last crawl 1h ago</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label"><Icons.FileText size={13}/>New posts (7d)</div>
            <div className="kpi-value tabnum">{COMPETITORS.reduce((a,c)=>a+c.newPosts,0)}<span className="kpi-delta up">▲ 18%</span></div>
            <div className="kpi-foot">across all competitors</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label"><Icons.Activity size={13}/>Avg threat</div>
            <div className="kpi-value tabnum">{Math.round(COMPETITORS.reduce((a,c)=>a+c.threat,0)/COMPETITORS.length)}</div>
            <div className="kpi-foot">threat_scorer</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label"><Icons.Tag size={13}/>Keyword overlap</div>
            <div className="kpi-value tabnum">{COMPETITORS.reduce((a,c)=>a+c.overlap,0).toLocaleString()}</div>
            <div className="kpi-foot">keyword_overlap</div>
          </div>
        </div>

        <div className="table-wrap">
          <table className="kw">
            <thead>
              <tr>
                <th>Domain</th>
                <th>Threat score</th>
                <th className="col-num">Pages indexed</th>
                <th className="col-num">Keyword overlap</th>
                <th className="col-num">New posts (7d)</th>
                <th>Last crawl</th>
                <th className="col-actions"></th>
              </tr>
            </thead>
            <tbody>
              {COMPETITORS.map(c => (
                <tr key={c.id} onClick={() => setOpen(c)}>
                  <td>
                    <div style={{display:"flex", alignItems:"center", gap:8}}>
                      <span style={{
                        width:24, height:24, borderRadius:6,
                        background:"#F1F1F4",
                        color:"var(--text-muted)",
                        display:"inline-flex", alignItems:"center", justifyContent:"center",
                        fontSize:11, fontWeight:600,
                      }}>{c.domain.charAt(0).toUpperCase()}</span>
                      <span className="kw-name">{c.domain}</span>
                    </div>
                  </td>
                  <td><ScoreBar value={c.threat / 100}/></td>
                  <td className="col-num tabnum">{c.pages.toLocaleString()}</td>
                  <td className="col-num tabnum">{c.overlap}</td>
                  <td className="col-num tabnum">{c.newPosts > 0 ? <span style={{color:"var(--green)", fontWeight:500}}>+{c.newPosts}</span> : "—"}</td>
                  <td><span style={{color:"var(--text-muted)", fontSize:12}}>{c.lastCrawled}</span></td>
                  <td className="col-actions"><button className="row-actions"><Icons.MoreH size={14}/></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </React.Fragment>
  );
}

function AnalyticsPage() {
  const totalCost = AGENT_RUNS.reduce((a,r)=>a+r.cost, 0);
  const totalRuns = AGENT_RUNS.reduce((a,r)=>a+r.runs, 0);
  const avgSuccess = AGENT_RUNS.reduce((a,r)=>a+r.success,0)/AGENT_RUNS.length;
  return (
    <React.Fragment>
      <Topbar
        title="Analytics"
        subtitle="Agent performance, pipeline runs, and spend across the last 7 days."
        actions={
          <React.Fragment>
            <button className="btn btn-secondary btn-sm"><Icons.Download size={13}/> Export CSV</button>
            <button className="btn btn-secondary btn-sm">
              Last 7 days <Icons.ChevronDown size={12}/>
            </button>
          </React.Fragment>
        }
      />
      <div className="page">
        <div style={{display:"grid", gridTemplateColumns:"repeat(4, 1fr)", gap:12, marginBottom:20}}>
          <div className="kpi-card">
            <div className="kpi-label"><Icons.Activity size={13}/>Agent runs</div>
            <div className="kpi-value tabnum">{totalRuns.toLocaleString()}<span className="kpi-delta up">▲ 8%</span></div>
            <div className="kpi-foot">across {AGENT_RUNS.length} agents</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label"><Icons.Check size={13}/>Success rate</div>
            <div className="kpi-value tabnum">{avgSuccess.toFixed(1)}%</div>
            <div className="kpi-foot">target ≥ 95%</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label"><Icons.TrendDown size={13}/>Spend (7d)</div>
            <div className="kpi-value tabnum">${totalCost.toFixed(2)}<span className="kpi-delta down">▼ 4%</span></div>
            <div className="kpi-foot">$50/day cap</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label"><Icons.Sparkle size={13}/>Pipeline runs</div>
            <div className="kpi-value tabnum">7</div>
            <div className="kpi-foot">last: 6h ago, success</div>
          </div>
        </div>

        <PageCard title="Agent performance" subtitle="Tier, success, latency, and 7-day spend" padding={false}>
          <table className="kw">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Tier</th>
                <th className="col-num">Runs</th>
                <th>Success</th>
                <th className="col-num">p50 latency</th>
                <th className="col-num">Spend (7d)</th>
                <th>Last run</th>
              </tr>
            </thead>
            <tbody>
              {AGENT_RUNS.map(r => (
                <tr key={r.agent}>
                  <td><span className="mono" style={{fontSize:12.5, fontWeight:500}}>{r.agent}</span></td>
                  <td>
                    <span className={"badge " + (r.tier === "advanced" ? "red" : r.tier === "standard" ? "purple" : "neutral")}>
                      {r.tier}
                    </span>
                  </td>
                  <td className="col-num tabnum">{r.runs}</td>
                  <td><ScoreBar value={r.success/100}/></td>
                  <td className="col-num tabnum">{r.p50ms < 1000 ? `${r.p50ms}ms` : `${(r.p50ms/1000).toFixed(1)}s`}</td>
                  <td className="col-num tabnum">${r.cost.toFixed(2)}</td>
                  <td><span style={{color:"var(--text-muted)", fontSize:12}}>{r.lastRun}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </PageCard>
      </div>
    </React.Fragment>
  );
}

function KnowledgePage() {
  return (
    <React.Fragment>
      <Topbar
        title="Knowledge"
        subtitle="RAG corpus + brand voice. Used by every content agent at generation time."
        actions={
          <React.Fragment>
            <button className="btn btn-secondary btn-sm"><Icons.Refresh size={13}/> Re-index</button>
            <button className="btn btn-primary"><Icons.Plus size={14}/> Upload document</button>
          </React.Fragment>
        }
      />
      <div className="page">
        <div style={{display:"grid", gridTemplateColumns:"2fr 1fr", gap:16}}>
          <div>
            <PageCard title="Documents" subtitle="document_ingester chunks + embeds via pgvector" padding={false}>
              <table className="kw">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Type</th>
                    <th className="col-num">Chunks</th>
                    <th className="col-num">Size</th>
                    <th>Ingested</th>
                    <th className="col-actions"></th>
                  </tr>
                </thead>
                <tbody>
                  {KNOWLEDGE_DOCS.map(d => (
                    <tr key={d.id}>
                      <td><div className="kw-name">{d.title}</div></td>
                      <td><span className="badge neutral">{d.type}</span></td>
                      <td className="col-num tabnum">{d.chunks}</td>
                      <td className="col-num tabnum" style={{color:"var(--text-muted)"}}>{d.size}</td>
                      <td><span style={{color:"var(--text-muted)", fontSize:12}}>{d.ingestedAt}</span></td>
                      <td className="col-actions"><button className="row-actions"><Icons.MoreH size={14}/></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </PageCard>

            <PageCard title="Index health" subtitle="knowledge_chunks table">
              <div style={{display:"grid", gridTemplateColumns:"repeat(3, 1fr)", gap:12}}>
                <div className="stat-cell">
                  <div className="l">Total chunks</div>
                  <div className="v">614</div>
                </div>
                <div className="stat-cell">
                  <div className="l">Embedding dim</div>
                  <div className="v mono" style={{fontSize:14}}>vector(1536)</div>
                </div>
                <div className="stat-cell">
                  <div className="l">Index type</div>
                  <div className="v mono" style={{fontSize:14}}>hnsw</div>
                </div>
              </div>
            </PageCard>
          </div>

          <div>
            <PageCard title="Brand voice" subtitle="brand_voice_keeper enforces these rules">
              <div style={{display:"flex", flexDirection:"column", gap:14}}>
                <div>
                  <div className="section-title" style={{margin:"0 0 6px"}}>Tone</div>
                  <div style={{display:"flex", flexWrap:"wrap", gap:6}}>
                    {["confident","practical","witty","data-driven"].map(t => (
                      <span key={t} className="badge purple">{t}</span>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="section-title" style={{margin:"0 0 6px"}}>Banned phrases</div>
                  <div style={{display:"flex", flexWrap:"wrap", gap:6}}>
                    {["revolutionary","game-changer","leverage","synergy"].map(t => (
                      <span key={t} className="badge red">{t}</span>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="section-title" style={{margin:"0 0 6px"}}>Style rules</div>
                  <ul style={{margin:0, padding:"0 0 0 18px", fontSize:12.5, color:"var(--text)", lineHeight:1.6}}>
                    <li>Lowercase product name in body copy</li>
                    <li>Use Oxford commas</li>
                    <li>Write in second person where natural</li>
                  </ul>
                </div>
                <button className="btn btn-secondary btn-sm" style={{alignSelf:"flex-start"}}>
                  <Icons.Pencil size={13}/> Edit voice
                </button>
              </div>
            </PageCard>
          </div>
        </div>
      </div>
    </React.Fragment>
  );
}

window.CompetitorsPage = CompetitorsPage;
window.AnalyticsPage = AnalyticsPage;
window.KnowledgePage = KnowledgePage;
