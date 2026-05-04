const { useState, useEffect } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "density": "comfortable",
  "showKpis": true,
  "sparkStyle": "area",
  "showEmpty": false,
  "accentHue": 257
}/*EDITMODE-END*/;

function App() {
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [page, setPage] = useState("keywords");

  useEffect(() => {
    const root = document.documentElement;
    const h = tweaks.accentHue;
    root.style.setProperty("--primary",     `oklch(0.50 0.18 ${h})`);
    root.style.setProperty("--primary-600", `oklch(0.44 0.18 ${h})`);
    root.style.setProperty("--primary-50",  `oklch(0.96 0.03 ${h})`);
    root.style.setProperty("--primary-100", `oklch(0.92 0.05 ${h})`);
  }, [tweaks.accentHue]);

  const renderPage = () => {
    switch (page) {
      case "keywords":    return <KeywordsPage tweaks={tweaks} />;
      case "content":     return <ContentPage />;
      case "competitors": return <CompetitorsPage />;
      case "analytics":   return <AnalyticsPage />;
      case "knowledge":   return <KnowledgePage />;
      case "auto":        return <AutoModePage />;
      case "settings":    return <SettingsPage />;
      default:            return <KeywordsPage tweaks={tweaks} />;
    }
  };

  return (
    <React.Fragment>
      <div className="app" data-screen-label={"Vikas — " + page}>
        <Sidebar active={page} onNavigate={setPage} />
        <div className="main">{renderPage()}</div>
      </div>
      <ToastHost />
      <TweaksPanel title="Tweaks">
        <TweakSection title="Layout">
          <TweakRadio label="Table density" value={tweaks.density}
            options={[{label:"Comfortable", value:"comfortable"},{label:"Compact", value:"compact"}]}
            onChange={(v) => setTweak("density", v)} />
          <TweakToggle label="Show KPI strip" checked={tweaks.showKpis} onChange={(v) => setTweak("showKpis", v)} />
          <TweakRadio label="Sparkline style" value={tweaks.sparkStyle}
            options={[{label:"Area", value:"area"},{label:"Line", value:"line"}]}
            onChange={(v) => setTweak("sparkStyle", v)} />
        </TweakSection>
        <TweakSection title="Theme">
          <TweakSlider label="Accent hue" min={0} max={360} step={1} value={tweaks.accentHue} onChange={(v) => setTweak("accentHue", v)} />
        </TweakSection>
        <TweakSection title="State">
          <TweakToggle label="Show Keywords empty state" checked={tweaks.showEmpty} onChange={(v) => setTweak("showEmpty", v)} />
        </TweakSection>
      </TweaksPanel>
    </React.Fragment>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
