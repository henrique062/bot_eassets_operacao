import os

css = """
/* ========================================================================= */
/* SMART REPORT STYLES                                                       */
/* ========================================================================= */

.smart-report-container {
    display: flex;
    gap: 24px;
    height: calc(100vh - 140px);
    overflow: hidden;
}

.smart-report-sidebar {
    width: 320px;
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.sidebar-header {
    padding: 20px;
    border-bottom: 1px solid var(--border-color);
}

.sidebar-header h3 {
    margin: 0 0 16px 0;
    font-size: 1.1rem;
    color: var(--text-main);
}

.btn-primary {
    width: 100%;
    padding: 12px;
    background: linear-gradient(135deg, var(--accent-purple), var(--accent-blue));
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
    text-align: center;
}

.btn-primary:hover:not(:disabled) {
    box-shadow: 0 4px 15px rgba(147, 51, 234, 0.4);
    transform: translateY(-2px);
}

.btn-primary.loading {
    opacity: 0.7;
    cursor: not-allowed;
}

.reports-list {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
}

.report-item {
    padding: 16px;
    border-radius: 8px;
    background: var(--bg-color);
    border: 1px solid var(--border-color);
    margin-bottom: 8px;
    cursor: pointer;
    transition: all 0.2s;
}

.report-item:hover {
    border-color: var(--accent-purple);
    transform: translateY(-2px);
}

.report-item.active {
    border-color: var(--accent-purple);
    background: rgba(147, 51, 234, 0.1);
}

.report-item-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}

.report-id {
    font-weight: 700;
    color: var(--accent-purple);
}

.report-date {
    font-size: 0.85rem;
    color: var(--text-muted);
}

.report-item-status {
    display: flex;
}

.status-badge {
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
}

.status-badge.valid { background: rgba(34, 197, 94, 0.2); color: #4ade80; }
.status-badge.invalid { background: rgba(239, 68, 68, 0.2); color: #f87171; }
.status-badge.pending { background: rgba(148, 163, 184, 0.2); color: #94a3b8; }

.smart-report-content {
    flex: 1;
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    padding: 32px;
    overflow-y: auto;
}

.report-header-info {
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 16px;
    margin-bottom: 24px;
}

.report-header-info h2 {
    margin: 0 0 8px 0;
    font-size: 1.8rem;
    color: var(--text-main);
}

.report-meta {
    margin: 0;
    color: var(--text-muted);
    font-size: 0.95rem;
}

.empty-state {
    text-align: center;
    padding: 40px 20px;
    color: var(--text-muted);
    font-size: 0.95rem;
}

.loading-spinner {
    text-align: center;
    padding: 40px 20px;
    color: var(--text-muted);
}
"""

css_path = os.path.join(os.path.dirname(__file__), 'src', 'index.css')
with open(css_path, "a", encoding="utf-8") as f:
    f.write("\n" + css)
    
print("CSS appended to index.css")
