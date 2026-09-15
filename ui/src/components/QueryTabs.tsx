export type QueryTabInfo = { id: string; title: string };

export default function QueryTabs({
  tabs,
  activeId,
  onSelect,
  onNew,
  onClose,
}: {
  tabs: QueryTabInfo[];
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onClose: (id: string) => void;
}) {
  return (
    <div className="query-tabs" role="tablist" aria-label="Query tabs">
      {tabs.map((t) => (
        <div
          key={t.id}
          role="tab"
          tabIndex={0}
          aria-selected={t.id === activeId}
          aria-label={t.title}
          className={t.id === activeId ? "query-tab on" : "query-tab"}
          onClick={() => onSelect(t.id)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onSelect(t.id);
            }
          }}
        >
          <span>{t.title}</span>
          {tabs.length > 1 && (
            <button
              type="button"
              className="query-tab-close"
              aria-label={`Close ${t.title}`}
              onClick={(e) => {
                e.stopPropagation();
                onClose(t.id);
              }}
            >
              ×
            </button>
          )}
        </div>
      ))}
      <button type="button" className="query-tab add" onClick={onNew} aria-label="New query">
        +
      </button>
    </div>
  );
}
