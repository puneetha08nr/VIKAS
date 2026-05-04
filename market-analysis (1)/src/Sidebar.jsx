function Sidebar({ active = "keywords", onNavigate }) {
  const marketing = [
    { id: "keywords",    label: "Keywords",    icon: <Icons.Tag size={15}/>,    badge: "18" },
    { id: "content",     label: "Content",     icon: <Icons.FileText size={15}/>, badge: "7" },
    { id: "competitors", label: "Competitors", icon: <Icons.Users size={15}/> },
    { id: "analytics",   label: "Analytics",   icon: <Icons.Chart size={15}/> },
  ];
  const system = [
    { id: "knowledge", label: "Knowledge", icon: <Icons.Book size={15}/> },
    { id: "auto",      label: "Auto Mode", icon: <Icons.Zap size={15}/>, badge: "ON" },
    { id: "settings",  label: "Settings",  icon: <Icons.Settings size={15}/> },
  ];

  const renderItem = (item) => (
    <button
      key={item.id}
      className={"nav-item" + (active === item.id ? " active" : "")}
      title={item.label}
      onClick={() => onNavigate && onNavigate(item.id)}
    >
      <span className="nav-icon">{item.icon}</span>
      <span>{item.label}</span>
      {item.badge ? <span className="nav-badge">{item.badge}</span> : null}
    </button>
  );

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-row">
          <span className="sidebar-bolt"><Icons.Bolt size={13}/></span>
          <span>Vikas</span>
        </div>
        <div className="sidebar-org">Acme Inc.</div>
      </div>

      <div className="sidebar-section">
        <div className="sidebar-section-label">Marketing</div>
        <div className="nav">{marketing.map(renderItem)}</div>
      </div>

      <div className="sidebar-section">
        <div className="sidebar-section-label">System</div>
        <div className="nav">{system.map(renderItem)}</div>
      </div>

      <div className="sidebar-spacer" />

      <div className="sidebar-foot">
        <div className="sidebar-user">
          <div className="avatar">RG</div>
          <div className="sidebar-user-meta">
            <div className="sidebar-user-name">Riya Gupta</div>
            <div className="sidebar-user-mail">riya@acme.co</div>
          </div>
        </div>
        <button className="nav-item" style={{marginTop: 4}}>
          <span className="nav-icon"><Icons.LogOut size={15}/></span>
          <span>Log out</span>
        </button>
      </div>
    </aside>
  );
}

window.Sidebar = Sidebar;
