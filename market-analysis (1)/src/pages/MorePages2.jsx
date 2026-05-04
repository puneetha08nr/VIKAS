function AutoModePage() {
  const [enabled, setEnabled] = React.useState(true);
  return (
    <React.Fragment>
      <Topbar
        title="Auto Mode"
        subtitle="Nightly pipeline at 02:00 UTC. Drafts go to review queue — never auto-publish."
        actions={
          <React.Fragment>
            <button className="btn btn-secondary btn-sm"><Icons.Activity size={13}/> View pipeline runs</button>
            <button className="btn btn-primary"><Icons.Sparkle size={14}/> Run now</button>
          </React.Fragment>
        }
      />
      <div className="page">
        <div style={{
          padding:"14px 18px",
          background: enabled ? "linear-gradient(0deg, rgba(83,74,183,0.05), rgba(83,74,183,0.05)), #fff" : "#fff",
          border: "1px solid " + (enabled ? "var(--primary-100)" : "var(--border)"),
          borderRadius: 8,
          display:"flex", alignItems:"center", gap:14, marginBottom:16,
        }}>
          <div style={{
            width:36, height:36, borderRadius:8,
            background: enabled ? "var(--primary)" : "#F1F1F4",
            color: enabled ? "#fff" : "var(--text-muted)",
            display:"inline-flex", alignItems:"center", justifyContent:"center",
            flexShrink:0,
          }}><Icons.Zap size={18}/></div>
          <div style={{flex:1, minWidth:0}}>
            <div style={{fontWeight:600, fontSize:14}}>Auto Mode is {enabled ? "enabled" : "paused"}</div>
            <div style={{color:"var(--text-muted)", fontSize:12.5, marginTop:2}}>
              {enabled
                ? "Next run in 6h 22m · last run drafted 4 articles, 6 LinkedIn posts, 1 newsletter"
                : "Resume to schedule the next nightly pipeline run."}
            </div>
          </div>
          <button
            className={enabled ? "btn btn-secondary btn-sm" : "btn btn-primary btn-sm"}
            onClick={() => setEnabled(!enabled)}
          >
            {enabled ? "Pause" : "Resume"}
          </button>
        </div>

        <div style={{display:"grid", gridTemplateColumns:"2fr 1fr", gap:16}}>
          <div>
            <PageCard title="Top opportunities for tonight" subtitle="opportunity_scorer composite ranking">
              <div style={{display:"flex", flexDirection:"column", gap:8}}>
                {OPPORTUNITIES.map(o => (
                  <div key={o.id} style={{
                    border:"1px solid var(--border)",
                    borderRadius:6,
                    padding:"10px 12px",
                    display:"grid",
                    gridTemplateColumns: "1.4fr repeat(4, 1fr) 80px",
                    gap:12,
                    alignItems:"center",
                  }}>
                    <div style={{minWidth:0}}>
                      <div style={{fontWeight:500, fontSize:13}}>{o.keyword}</div>
                      <div style={{marginTop:4}}><FormatChip format={o.format}/></div>
                    </div>
                    <div>
                      <div style={{fontSize:10.5, color:"var(--text-muted)", textTransform:"uppercase", letterSpacing:"0.04em"}}>Search</div>
                      <ScoreBar value={o.search}/>
                    </div>
                    <div>
                      <div style={{fontSize:10.5, color:"var(--text-muted)", textTransform:"uppercase", letterSpacing:"0.04em"}}>Gap</div>
                      <ScoreBar value={o.gap}/>
                    </div>
                    <div>
                      <div style={{fontSize:10.5, color:"var(--text-muted)", textTransform:"uppercase", letterSpacing:"0.04em"}}>Trend</div>
                      <ScoreBar value={o.trend}/>
                    </div>
                    <div>
                      <div style={{fontSize:10.5, color:"var(--text-muted)", textTransform:"uppercase", letterSpacing:"0.04em"}}>Engage</div>
                      <ScoreBar value={o.engagement}/>
                    </div>
                    <div style={{textAlign:"right"}}>
                      <div style={{fontSize:11, color:"var(--text-muted)"}}>Composite</div>
                      <div className="tabnum" style={{fontSize:18, fontWeight:600, color:"var(--primary)"}}>{Math.round(o.composite*100)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </PageCard>
          </div>

          <div>
            <PageCard title="Daily caps" subtitle="content_director respects these">
              <div style={{display:"flex", flexDirection:"column", gap:10}}>
                {[
                  { label: "Articles", used: 2, cap: 4 },
                  { label: "LinkedIn", used: 4, cap: 6 },
                  { label: "Twitter", used: 1, cap: 3 },
                  { label: "Newsletter", used: 0, cap: 1 },
                ].map(c => (
                  <div key={c.label}>
                    <div style={{display:"flex", justifyContent:"space-between", fontSize:12.5, marginBottom:4}}>
                      <span>{c.label}</span>
                      <span className="tabnum" style={{color:"var(--text-muted)"}}>{c.used} / {c.cap}</span>
                    </div>
                    <div style={{height:6, background:"#F1F1F4", borderRadius:999, overflow:"hidden"}}>
                      <div style={{
                        height:"100%",
                        width: (c.used/c.cap*100) + "%",
                        background:"var(--primary)",
                        borderRadius:999,
                      }}/>
                    </div>
                  </div>
                ))}
              </div>
            </PageCard>

            <PageCard title="Schedule" subtitle="Configurable per-org">
              <div style={{display:"flex", flexDirection:"column", gap:10, fontSize:13}}>
                <div style={{display:"flex", justifyContent:"space-between"}}>
                  <span style={{color:"var(--text-muted)"}}>Cadence</span>
                  <span style={{fontWeight:500}}>Nightly</span>
                </div>
                <div style={{display:"flex", justifyContent:"space-between"}}>
                  <span style={{color:"var(--text-muted)"}}>Run time</span>
                  <span className="mono">02:00 UTC</span>
                </div>
                <div style={{display:"flex", justifyContent:"space-between"}}>
                  <span style={{color:"var(--text-muted)"}}>Cost ceiling</span>
                  <span className="mono">$50/day</span>
                </div>
                <div style={{display:"flex", justifyContent:"space-between"}}>
                  <span style={{color:"var(--text-muted)"}}>Notify on</span>
                  <span style={{fontWeight:500}}>Failure + summary</span>
                </div>
              </div>
            </PageCard>
          </div>
        </div>
      </div>
    </React.Fragment>
  );
}

function SettingsPage() {
  const [tab, setTab] = React.useState("integrations");
  return (
    <React.Fragment>
      <Topbar
        title="Settings"
        subtitle="Organization, integrations, cost limits, and team."
        actions={null}
      />
      <div className="page">
        <div style={{
          display:"flex", gap:6, marginBottom:16,
          borderBottom:"1px solid var(--border)",
        }}>
          {[
            { id:"general",     label:"General" },
            { id:"integrations",label:"Integrations" },
            { id:"limits",      label:"Cost limits" },
            { id:"team",        label:"Team" },
          ].map(t => (
            <button key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                background:"transparent",
                border:"none",
                borderBottom: tab === t.id ? "2px solid var(--primary)" : "2px solid transparent",
                padding:"8px 12px",
                marginBottom:-1,
                fontSize:13,
                fontWeight:500,
                color: tab === t.id ? "var(--text)" : "var(--text-muted)",
                cursor:"pointer",
              }}
            >{t.label}</button>
          ))}
        </div>

        {tab === "integrations" && (
          <div style={{display:"grid", gridTemplateColumns:"repeat(2, 1fr)", gap:12}}>
            {INTEGRATIONS.map(i => (
              <div key={i.id} style={{
                background:"#fff",
                border:"1px solid var(--border)",
                borderRadius:8,
                padding:"14px 16px",
                display:"flex", alignItems:"center", gap:12,
              }}>
                <div style={{
                  width:36, height:36, borderRadius:8,
                  background:"#F1F1F4",
                  display:"inline-flex", alignItems:"center", justifyContent:"center",
                  color:"var(--text-muted)",
                }}><Icons.Globe size={18}/></div>
                <div style={{flex:1, minWidth:0}}>
                  <div style={{fontWeight:500, fontSize:13.5}}>{i.name}</div>
                  <div style={{fontSize:12, color:"var(--text-muted)", marginTop:2}}>
                    {i.account || "Not connected"}
                  </div>
                </div>
                {i.status === "connected" ? (
                  <span className="badge green"><span className="badge-dot" style={{background:"#16A34A"}}/>Connected</span>
                ) : (
                  <button className="btn btn-secondary btn-sm">Connect</button>
                )}
              </div>
            ))}
          </div>
        )}

        {tab === "general" && (
          <PageCard title="Organization">
            <div style={{display:"grid", gridTemplateColumns:"1fr 1fr", gap:14}}>
              <div className="field"><label>Name</label><input className="input" defaultValue="Acme Inc." /></div>
              <div className="field"><label>Slug</label><input className="input mono" defaultValue="acme" /></div>
              <div className="field"><label>Primary domain</label><input className="input" defaultValue="acme.co" /></div>
              <div className="field"><label>Timezone</label><select className="select"><option>UTC</option><option>America/Los_Angeles</option><option>Asia/Kolkata</option></select></div>
            </div>
          </PageCard>
        )}

        {tab === "limits" && (
          <PageCard title="Cost limits" subtitle="LLM router enforces these — kill on breach.">
            <div style={{display:"flex", flexDirection:"column", gap:14, maxWidth: 460}}>
              <div className="field"><label>Daily cap (org)</label><input className="input mono" defaultValue="$50.00" /><div className="hint">Pipeline halts when reached.</div></div>
              <div className="field"><label>Per-agent-run cap</label><input className="input mono" defaultValue="$5.00" /></div>
              <div className="field"><label>Notify when 80% reached</label>
                <div style={{display:"flex", alignItems:"center", gap:8, fontSize:13, color:"var(--text-muted)"}}>
                  <input type="checkbox" defaultChecked/> Slack #marketing-ops
                </div>
              </div>
            </div>
          </PageCard>
        )}

        {tab === "team" && (
          <PageCard title="Team members" action={<button className="btn btn-secondary btn-sm"><Icons.Plus size={13}/> Invite</button>} padding={false}>
            <table className="kw">
              <thead><tr><th>Member</th><th>Email</th><th>Role</th><th>Last active</th></tr></thead>
              <tbody>
                {[
                  { name:"Riya Gupta", initials:"RG", email:"riya@acme.co", role:"Owner", last:"now" },
                  { name:"Aman Rao",   initials:"AR", email:"aman@acme.co", role:"Editor", last:"2h ago" },
                  { name:"Mei Tan",    initials:"MT", email:"mei@acme.co",  role:"Reviewer", last:"1d ago" },
                ].map(m => (
                  <tr key={m.email}>
                    <td><div style={{display:"flex", alignItems:"center", gap:8}}><div className="avatar" style={{width:22, height:22, fontSize:10}}>{m.initials}</div><span style={{fontSize:13, fontWeight:500}}>{m.name}</span></div></td>
                    <td><span style={{fontSize:12.5, color:"var(--text-muted)"}}>{m.email}</span></td>
                    <td><span className="badge purple">{m.role}</span></td>
                    <td><span style={{fontSize:12, color:"var(--text-muted)"}}>{m.last}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PageCard>
        )}
      </div>
    </React.Fragment>
  );
}

window.AutoModePage = AutoModePage;
window.SettingsPage = SettingsPage;
