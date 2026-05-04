function Topbar({ title, subtitle, actions }) {
  return (
    <div className="topbar">
      <div className="topbar-titleblock">
        <h1>{title}</h1>
        {subtitle ? <div className="topbar-subtitle">{subtitle}</div> : null}
      </div>
      <div className="topbar-actions">{actions}</div>
    </div>
  );
}
window.Topbar = Topbar;
