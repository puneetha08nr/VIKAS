function ContentPage() {
  const [filter, setFilter] = React.useState("review");
  const items = CONTENT_ITEMS.filter(i => filter === "all" ? true : i.status === filter);
  const counts = {
    all: CONTENT_ITEMS.length,
    review: CONTENT_ITEMS.filter(i => i.status === "review").length,
    approved: CONTENT_ITEMS.filter(i => i.status === "approved").length,
    published: CONTENT_ITEMS.filter(i => i.status === "published").length,
    draft: CONTENT_ITEMS.filter(i => i.status === "draft").length,
  };

  const tabs = [
    { id:"review",    label:"Needs review", count: counts.review },
    { id:"approved",  label:"Approved",     count: counts.approved },
    { id:"published", label:"Published",    count: counts.published },
    { id:"draft",     label:"Drafts",       count: counts.draft },
    { id:"all",       label:"All",          count: counts.all },
  ];

  return (
    <React.Fragment>
      <Topbar
        title="Content"
        subtitle="Review queue from content_director. Nothing publishes without approval."
        actions={
          <React.Fragment>
            <button className="btn btn-secondary btn-sm">
              <Icons.Refresh size={13}/> Refresh
            </button>
            <button className="btn btn-primary">
              <Icons.Sparkle size={14}/> Generate from keyword
            </button>
          </React.Fragment>
        }
      />
      <div className="page">
        <div style={{
          display:"grid", gridTemplateColumns:"repeat(4, 1fr)", gap:12, marginBottom: 20,
        }}>
          <div className="kpi-card">
            <div className="kpi-label"><Icons.FileText size={13}/>In review queue</div>
            <div className="kpi-value tabnum">{counts.review}</div>
            <div className="kpi-foot">avg wait 4h 12m</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label"><Icons.Check size={13}/>Approved this week</div>
            <div className="kpi-value tabnum">14<span className="kpi-delta up">▲ 22%</span></div>
            <div className="kpi-foot">vs. last week</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label"><Icons.Activity size={13}/>Avg brand voice</div>
            <div className="kpi-value tabnum">88</div>
            <div className="kpi-foot">brand_voice_keeper</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label"><Icons.TrendUp size={13}/>Drafts → publish</div>
            <div className="kpi-value tabnum">2.4d</div>
            <div className="kpi-foot">median cycle time</div>
          </div>
        </div>

        <div className="toolbar">
          <div className="toolbar-left" style={{gap:4}}>
            {tabs.map(t => (
              <button key={t.id}
                className={"filter-chip " + (filter === t.id ? "active" : "")}
                onClick={() => setFilter(t.id)}
              >
                {t.label}
                <span className="tabnum" style={{
                  marginLeft:4,
                  fontSize:11,
                  opacity:0.7,
                }}>{t.count}</span>
              </button>
            ))}
          </div>
          <div className="toolbar-right">
            <button className="btn btn-secondary btn-sm"><Icons.Filter size={13}/> Filter</button>
          </div>
        </div>

        <div className="table-wrap">
          <table className="kw">
            <thead>
              <tr>
                <th>Title</th>
                <th>Format</th>
                <th>Status</th>
                <th>Keyword</th>
                <th>Brand voice</th>
                <th>SEO</th>
                <th className="col-num">Words</th>
                <th>Updated</th>
                <th className="col-actions"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => (
                <tr key={it.id}>
                  <td style={{maxWidth: 360}}>
                    <div className="kw-name truncate">{it.title}</div>
                    <div className="kw-meta">via <span className="mono">{it.agent}</span> · by {it.author}</div>
                  </td>
                  <td><FormatChip format={it.format}/></td>
                  <td><ContentStatusBadge status={it.status}/></td>
                  <td><span style={{fontSize:12.5}}>{it.keyword}</span></td>
                  <td><ScoreBar value={it.brandVoice}/></td>
                  <td>{it.seo != null ? <ScoreBar value={it.seo}/> : <span style={{color:"var(--text-subtle)"}}>—</span>}</td>
                  <td className="col-num tabnum">{it.wordCount.toLocaleString()}</td>
                  <td><span style={{color:"var(--text-muted)", fontSize:12}}>{it.updatedAt}</span></td>
                  <td className="col-actions">
                    {it.status === "review" ? (
                      <div style={{display:"flex", gap:4}}>
                        <button className="btn btn-secondary btn-sm" style={{padding:"0 8px"}}>
                          <Icons.Check size={12}/>
                        </button>
                        <button className="row-actions"><Icons.MoreH size={14}/></button>
                      </div>
                    ) : (
                      <button className="row-actions"><Icons.MoreH size={14}/></button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </React.Fragment>
  );
}

window.ContentPage = ContentPage;
