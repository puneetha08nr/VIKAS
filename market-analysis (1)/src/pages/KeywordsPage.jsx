// Keywords page extracted from App.jsx so the App can route between pages.
const { useState: useKwState, useMemo: useKwMemo, useEffect: useKwEffect, useRef: useKwRef } = React;

const MockApi = {
  _runs: {},
  async _post(seed) {
    const run_id = "run_" + Math.random().toString(36).slice(2, 9);
    this._runs[run_id] = { run_id, status: "running", started: Date.now(), seed };
    return { run_id };
  },
  async research(seed_keyword) { return this._post(seed_keyword); },
  async validateAll() {
    const r = await this._post("validate-all");
    this._runs[r.run_id].kind = "validate-all";
    return { ...r, keyword_count: 5 };
  },
  async getRun(run_id) {
    const r = this._runs[run_id];
    if (!r) return { status: "failed", error: "run not found" };
    if (Date.now() - r.started > 2400) r.status = "success";
    return r;
  },
};
function pollRun(run_id, { onSuccess, onFailed, intervalMs = 600 }) {
  const tick = async () => {
    try {
      const r = await MockApi.getRun(run_id);
      if (r.status === "success") onSuccess(r);
      else if (r.status === "failed") onFailed(r);
      else setTimeout(tick, intervalMs);
    } catch (e) { onFailed({ error: e.message }); }
  };
  tick();
}

function KeywordsPage({ tweaks }) {
  const [keywords, setKeywords] = useKwState(KEYWORDS);
  const [search, setSearch] = useKwState("");
  const [statusFilter, setStatusFilter] = useKwState("all");
  const [intentFilter, setIntentFilter] = useKwState("all");
  const [clusterFilter, setClusterFilter] = useKwState("all");
  const [selected, setSelected] = useKwState(new Set());
  const [openKeyword, setOpenKeyword] = useKwState(null);
  const [addOpen, setAddOpen] = useKwState(false);
  const [researchRun, setResearchRun] = useKwState(null);
  const [validateRun, setValidateRun] = useKwState(null);
  const tableRef = useKwRef(null);

  const stats = useKwMemo(() => {
    const by = (s) => keywords.filter(k => k.status === s).length;
    return { total: keywords.length, raw: by("raw"), validated: by("validated"), clustered: by("clustered"), archived: by("archived"), totalVol: keywords.reduce((a,k)=>a+k.volume,0) };
  }, [keywords]);

  const rows = useKwMemo(() => {
    let r = keywords;
    if (tweaks.showEmpty) return [];
    if (search.trim()) r = r.filter(k => k.keyword.toLowerCase().includes(search.toLowerCase()));
    if (statusFilter !== "all")  r = r.filter(k => k.status === statusFilter);
    if (intentFilter !== "all")  r = r.filter(k => k.intent === intentFilter);
    if (clusterFilter !== "all") r = r.filter(k => k.cluster === clusterFilter);
    return r;
  }, [keywords, search, statusFilter, intentFilter, clusterFilter, tweaks.showEmpty]);

  const toggle = (id) => { const n = new Set(selected); n.has(id) ? n.delete(id) : n.add(id); setSelected(n); };
  const toggleAll = () => rows.every(r => selected.has(r.id)) ? setSelected(new Set()) : setSelected(new Set(rows.map(r => r.id)));

  const handleResearch = async ({ seed_keyword }) => {
    const loadingId = window.toast.show({ kind:"loading", title:"Researching…", message:`Seed: "${seed_keyword}"`, ttl:0 });
    try {
      const { run_id } = await MockApi.research(seed_keyword);
      setResearchRun(run_id);
      pollRun(run_id, {
        onSuccess: () => {
          const newOnes = [
            { keyword: seed_keyword + " software",     volume: 1800, kd: 4.2, cpc: 6.1, intent: "commercial" },
            { keyword: seed_keyword + " for startups", volume: 720,  kd: 3.4, cpc: 4.4, intent: "commercial" },
            { keyword: "best " + seed_keyword,         volume: 2100, kd: 5.6, cpc: 7.9, intent: "transactional" },
            { keyword: seed_keyword + " platform",     volume: 1500, kd: 5.1, cpc: 6.8, intent: "commercial" },
          ].map((k, i) => ({ id: "n"+Date.now()+"_"+i, ...k, cluster: "c1", status: "raw", position: null, prevPosition: null, url: null, contentCount: 0, source_agent: "keyword_research", data_source: "llm_estimate", reason: "", trend: [800,820,860,880,900,940,980,1010,1050,1100,1130,1180] }));
          setKeywords(prev => [...newOnes, ...prev]);
          setResearchRun(null); setAddOpen(false);
          window.toast.dismiss(loadingId);
          window.toast.show({ kind:"success", title:`${newOnes.length} new keywords added`, message:"Status: raw. Run keyword_validator next." });
          requestAnimationFrame(() => tableRef.current?.scrollIntoView({ behavior:"smooth", block:"start" }));
        },
        onFailed: (r) => { setResearchRun(null); window.toast.dismiss(loadingId); window.toast.show({ kind:"error", title:"Research failed", message:r.error || "Unknown error" }); },
      });
    } catch (e) { setResearchRun(null); window.toast.dismiss(loadingId); window.toast.show({ kind:"error", title:"Research failed", message:e.message }); }
  };

  const handleValidateAll = async () => {
    if (stats.raw === 0 || validateRun) return;
    const rawCount = stats.raw;
    const loadingId = window.toast.show({ kind:"loading", title:`Validating ${rawCount} keyword${rawCount===1?"":"s"}…`, message:"keyword_validator running", ttl:0 });
    try {
      const { run_id } = await MockApi.validateAll();
      setValidateRun({ run_id, count: rawCount });
      pollRun(run_id, {
        onSuccess: () => {
          let v=0, a=0;
          setKeywords(prev => prev.map(k => {
            if (k.status !== "raw") return k;
            const archive = Math.random() < 0.3;
            if (archive) { a++; return { ...k, status:"archived", data_source:"dataforseo", reason:"Out of scope or low fit" }; }
            v++; return { ...k, status:"validated", data_source:"dataforseo", reason:"Strong intent + reachable difficulty" };
          }));
          setValidateRun(null); window.toast.dismiss(loadingId);
          window.toast.show({ kind:"success", title:`${v} validated, ${a} archived`, message:"Run gap_analyzer to cluster validated keywords." });
        },
        onFailed: (r) => { setValidateRun(null); window.toast.dismiss(loadingId); window.toast.show({ kind:"error", title:"Validation failed", message:r.error || "Unknown error" }); },
      });
    } catch (e) { setValidateRun(null); window.toast.dismiss(loadingId); window.toast.show({ kind:"error", title:"Validation failed", message:e.message }); }
  };

  const sp1=[120,132,128,142,138,156,168,172,165,178,184,192], sp2=[9,9,10,10,11,11,11,12,12,13,13,14], sp3=[890,920,940,980,1020,1080,1100,1140,1180,1220,1260,1290], sp4=[3,4,5,6,6,7,8,9,10,11,12,12];
  const kpiItems = [
    { label:"Raw",        icon:<Icons.Sparkle size={13}/>, value:stats.raw.toLocaleString(),       foot:stats.raw>0?"awaiting validation":"all caught up", spark:sp4, sparkColor:"#9A9AA3" },
    { label:"Validated",  icon:<Icons.Check size={13}/>,   value:stats.validated.toLocaleString(), foot:"ready for clustering", spark:sp1, sparkColor:"#534AB7" },
    { label:"Clustered",  icon:<Icons.Tag size={13}/>,     value:stats.clustered.toLocaleString(), delta:12, foot:"active in pipeline", spark:sp3, sparkColor:"#16A34A" },
    { label:"Total volume", icon:<Icons.Activity size={13}/>, value:(stats.totalVol/1000).toFixed(1)+"k", delta:4.2, foot:"monthly searches", spark:sp2, sparkColor:"#0EA5E9" },
  ];

  return (
    <React.Fragment>
      <Topbar title="Keywords" subtitle="Research, validate, and cluster keywords. Status flow: raw → validated → clustered."
        actions={
          <React.Fragment>
            <button className="btn btn-ghost btn-sm"><Icons.Download size={13}/> Export</button>
            {stats.raw > 0 && (
              <button className="btn btn-secondary btn-sm" onClick={handleValidateAll} disabled={!!validateRun}>
                {validateRun ? <React.Fragment><Spinner size={12}/> Validating {validateRun.count}…</React.Fragment>
                             : <React.Fragment><Icons.Check size={13}/> Validate all ({stats.raw})</React.Fragment>}
              </button>
            )}
            <button className="btn btn-primary" onClick={() => setAddOpen(true)} disabled={!!researchRun}>
              <Icons.Sparkle size={14}/> Research keywords
            </button>
          </React.Fragment>
        } />
      <div className="page">
        {tweaks.showKpis && <KpiStrip items={kpiItems} />}
        <div className="toolbar">
          <div className="toolbar-left">
            <div className="search-wrap">
              <Icons.Search size={13}/>
              <input className="search" placeholder="Search keywords…" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <span className="filter-chip" onClick={() => { const o=["all","raw","validated","clustered","archived"]; setStatusFilter(o[(o.indexOf(statusFilter)+1)%o.length]); }}>
              Status: <strong style={{fontWeight:600}}>{statusFilter==="all"?"Any":statusFilter}</strong><Icons.ChevronDown size={11}/>
            </span>
            <span className="filter-chip" onClick={() => { const o=["all","commercial","transactional","informational","navigational"]; setIntentFilter(o[(o.indexOf(intentFilter)+1)%o.length]); }}>
              Intent: <strong style={{fontWeight:600}}>{intentFilter==="all"?"Any":intentFilter}</strong><Icons.ChevronDown size={11}/>
            </span>
            <span className="filter-chip" onClick={() => { const o=["all", ...KW_CLUSTERS.map(c=>c.id)]; setClusterFilter(o[(o.indexOf(clusterFilter)+1)%o.length]); }}>
              Cluster: <strong style={{fontWeight:600}}>{clusterFilter==="all"?"Any":KW_CLUSTERS.find(c=>c.id===clusterFilter)?.name}</strong><Icons.ChevronDown size={11}/>
            </span>
            {(statusFilter!=="all" || intentFilter!=="all" || clusterFilter!=="all" || search) && (
              <button className="btn btn-ghost btn-sm" onClick={() => { setStatusFilter("all"); setIntentFilter("all"); setClusterFilter("all"); setSearch(""); }}>Clear</button>
            )}
          </div>
          <div className="toolbar-right">
            <span style={{color:"var(--text-muted)", fontSize:12.5}} className="tabnum">{rows.length} of {keywords.length}</span>
            <button className="btn btn-secondary btn-sm"><Icons.Filter size={13}/> View</button>
          </div>
        </div>
        <KeywordsTable tableRef={tableRef} rows={rows} selected={selected} onToggle={toggle} onToggleAll={toggleAll} onOpen={setOpenKeyword} density={tweaks.density} sparkStyle={tweaks.sparkStyle} />
        {selected.size > 0 && (
          <div className="bulkbar">
            <strong className="tabnum">{selected.size}</strong> selected
            <span className="divider"/>
            <button>Validate selected</button><button>Move to cluster…</button><button>Archive</button>
            <span className="divider"/>
            <button onClick={() => setSelected(new Set())} title="Clear"><Icons.X size={12}/></button>
          </div>
        )}
      </div>
      <KeywordDrawer keyword={openKeyword} onClose={() => setOpenKeyword(null)} />
      <AddKeywordModal open={addOpen} onClose={() => setAddOpen(false)} onAdd={handleResearch} busy={!!researchRun} />
    </React.Fragment>
  );
}

window.KeywordsPage = KeywordsPage;
