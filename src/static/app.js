/**
 * Carfullfy SLA Escalation Engine — Client Application (Redesigned)
 * Author: Muddassir Khan | Bootcamp 2026
 *
 * Features:
 *  - Real-time ticket polling (3s) + SLA countdown (1s)
 *  - Dark / Light mode with localStorage persistence
 *  - Status filter tabs (All / Open / Claimed / Escalated)
 *  - Subject search / filter
 *  - Priority selector (Low / Medium / High / Critical)
 *  - Toast notification system with icons
 *  - Activity feed / audit log panel
 *  - Expandable ticket cards with full detail view
 *  - Animated stat cards with pop on change
 *  - Keyboard shortcut: N → focus new-ticket form
 */

'use strict';

const API_URL = ''; // Relative to host — served by Python server

// ── State ──────────────────────────────────────────────────────
let tickets          = [];
let activeFilter     = 'all';
let searchQuery      = '';
let selectedPriority = 'medium';
let lastRefreshAt    = null;
let lastStatValues   = { total: 0, open: 0, claimed: 0, escalated: 0 };

// ── DOM Refs ────────────────────────────────────────────────────
const ticketsContainer  = document.getElementById('tickets-container');
const createForm        = document.getElementById('create-ticket-form');
const subjectInput      = document.getElementById('ticket-subject');
const btnRefresh        = document.getElementById('btn-refresh');
const refreshIcon       = document.getElementById('refresh-icon');
const lastRefreshedEl   = document.getElementById('last-refreshed');

const valTotal          = document.getElementById('val-total');
const valOpen           = document.getElementById('val-open');
const valClaimed        = document.getElementById('val-claimed');
const valEscalated      = document.getElementById('val-escalated');
const statCards         = {
    total:     document.getElementById('stat-total'),
    open:      document.getElementById('stat-open'),
    claimed:   document.getElementById('stat-claimed'),
    escalated: document.getElementById('stat-escalated'),
};

const claimModal         = document.getElementById('claim-modal');
const claimForm          = document.getElementById('claim-ticket-form');
const claimTicketIdInput = document.getElementById('claim-ticket-id');
const agentNameInput     = document.getElementById('agent-name');
const btnCancelClaim     = document.getElementById('btn-cancel-claim');
const btnModalClose      = document.getElementById('btn-modal-close');

const btnDarkMode        = document.getElementById('btn-dark-mode');
const iconMoon           = document.getElementById('icon-moon');
const iconSun            = document.getElementById('icon-sun');

const filterTabs         = document.querySelectorAll('.filter-tab');
const searchInput        = document.getElementById('search-input');

const activityList       = document.getElementById('activity-list');
const btnClearActivity   = document.getElementById('btn-clear-activity');
const prioritySelector   = document.getElementById('priority-selector');
const toastContainer     = document.getElementById('toast-container');


/* =============================================================
   UTILITY HELPERS
   ============================================================= */

function escapeHTML(str) {
    if (!str) return '';
    return String(str).replace(/[&<>'"]/g,
        tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
}

function parseUTCDate(dateStr) {
    if (!dateStr) return null;
    const s = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z';
    return new Date(s);
}

function formatTime(date) {
    if (!date) return '—';
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function timeAgo(date) {
    if (!date) return '';
    const diffSec = Math.round((Date.now() - date.getTime()) / 1000);
    if (diffSec < 5)  return 'just now';
    if (diffSec < 60) return `${diffSec}s ago`;
    const m = Math.round(diffSec / 60);
    return `${m}m ago`;
}


/* =============================================================
   DARK MODE
   ============================================================= */

function applyTheme(dark) {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    iconMoon.style.display = dark ? 'none' : '';
    iconSun.style.display  = dark ? ''     : 'none';
}

function initTheme() {
    const stored      = localStorage.getItem('carfullfy-theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const dark        = stored === 'dark' || (!stored && prefersDark);
    applyTheme(dark);
}

btnDarkMode.addEventListener('click', () => {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const newDark = !isDark;
    applyTheme(newDark);
    localStorage.setItem('carfullfy-theme', newDark ? 'dark' : 'light');
});


/* =============================================================
   TOAST NOTIFICATIONS
   ============================================================= */

const TOAST_ICONS = {
    success: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,
    error:   `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
    info:    `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
    warning: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
};

function showToast(type, title, message = '', duration = 4000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <div class="toast-icon">${TOAST_ICONS[type] || TOAST_ICONS.info}</div>
        <div class="toast-body">
            <div class="toast-title">${escapeHTML(title)}</div>
            ${message ? `<div class="toast-msg">${escapeHTML(message)}</div>` : ''}
        </div>
        <button class="toast-close" aria-label="Dismiss">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </button>
    `;

    toastContainer.appendChild(toast);

    const dismiss = () => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    };

    toast.querySelector('.toast-close').addEventListener('click', dismiss);
    setTimeout(dismiss, duration);
}


/* =============================================================
   ACTIVITY FEED
   ============================================================= */

const activityLog = [];

function logActivity(type, subject, detail = '') {
    const now = new Date();
    activityLog.unshift({ type, subject, detail, time: now });

    const emptyEl = activityList.querySelector('.activity-empty');
    if (emptyEl) emptyEl.remove();

    const labels = { created: 'Ticket created', claimed: 'Ticket claimed', escalated: 'SLA breached' };
    const detailText = detail ? ` by <strong>${escapeHTML(detail)}</strong>` : '';

    const li = document.createElement('li');
    li.className = 'activity-item';
    li.innerHTML = `
        <span class="activity-dot ${type}"></span>
        <div style="flex:1;min-width:0">
            <div style="font-size:0.73rem;color:var(--text-primary);font-weight:600;line-height:1.3">
                ${escapeHTML(labels[type] || type)}${detailText}
            </div>
            <div style="font-size:0.68rem;color:var(--text-muted);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                ${escapeHTML(subject.length > 40 ? subject.substring(0, 40) + '…' : subject)}
            </div>
        </div>
        <span class="activity-time">${formatTime(now)}</span>
    `;

    activityList.insertBefore(li, activityList.firstChild);

    const items = activityList.querySelectorAll('.activity-item');
    if (items.length > 30) items[items.length - 1].remove();
}

btnClearActivity.addEventListener('click', () => {
    activityList.innerHTML = '<li class="activity-empty">No recent activity.</li>';
    activityLog.length = 0;
});


/* =============================================================
   STATS
   ============================================================= */

function updateStats(newStats) {
    const keys = ['total', 'open', 'claimed', 'escalated'];
    const els  = { total: valTotal, open: valOpen, claimed: valClaimed, escalated: valEscalated };

    keys.forEach(key => {
        const val = newStats[key];
        if (val !== lastStatValues[key]) {
            els[key].textContent = val;
            const card = statCards[key];
            card.classList.remove('pop');
            void card.offsetWidth;
            card.classList.add('pop');
            setTimeout(() => card.classList.remove('pop'), 450);
        }
    });

    lastStatValues = { ...newStats };
}


/* =============================================================
   FILTER & SEARCH
   ============================================================= */

filterTabs.forEach(tab => {
    tab.addEventListener('click', () => {
        filterTabs.forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
        activeFilter = tab.getAttribute('data-filter');
        renderTickets();
    });
});

searchInput.addEventListener('input', () => {
    searchQuery = searchInput.value.trim().toLowerCase();
    renderTickets();
});

function getFilteredTickets() {
    return tickets.filter(t => {
        const matchesFilter = activeFilter === 'all' || t.status === activeFilter;
        const matchesSearch = !searchQuery ||
            t.subject.toLowerCase().includes(searchQuery) ||
            t.id.toLowerCase().includes(searchQuery);
        return matchesFilter && matchesSearch;
    });
}


/* =============================================================
   PRIORITY SELECTOR
   ============================================================= */

prioritySelector.querySelectorAll('.priority-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        prioritySelector.querySelectorAll('.priority-btn').forEach(b => {
            b.classList.remove('active');
            b.setAttribute('aria-pressed', 'false');
        });
        btn.classList.add('active');
        btn.setAttribute('aria-pressed', 'true');
        selectedPriority = btn.getAttribute('data-priority');
    });
});


/* =============================================================
   FETCH TICKETS
   ============================================================= */

const seenTicketIds = new Set();
const prevStatuses  = {};

async function fetchTickets() {
    try {
        const response = await fetch(`${API_URL}/tickets`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        data.forEach(t => {
            if (!seenTicketIds.has(t.id)) {
                seenTicketIds.add(t.id);
                if (tickets.length > 0) {
                    logActivity('created', t.subject);
                }
            } else if (prevStatuses[t.id] && prevStatuses[t.id] !== t.status) {
                if (t.status === 'claimed')   logActivity('claimed',   t.subject, t.claimed_by);
                if (t.status === 'escalated') logActivity('escalated', t.subject);
            }
            prevStatuses[t.id] = t.status;
        });

        if (tickets.length === 0 && data.length > 0) {
            data.forEach(t => seenTicketIds.add(t.id));
        }

        tickets = data;
        lastRefreshAt = new Date();

        const stats = {
            total:     tickets.length,
            open:      tickets.filter(t => t.status === 'open').length,
            claimed:   tickets.filter(t => t.status === 'claimed').length,
            escalated: tickets.filter(t => t.status === 'escalated').length,
        };

        updateStats(stats);
        renderTickets();
        updateLastRefreshed();

    } catch (err) {
        console.error('Error fetching tickets:', err);
        showErrorState();
    }
}

function updateLastRefreshed() {
    if (!lastRefreshAt) return;
    lastRefreshedEl.textContent = `Last updated: ${timeAgo(lastRefreshAt)}`;
}


/* =============================================================
   RENDER TICKETS
   ============================================================= */

function getStatusIcon(status) {
    if (status === 'open')      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
    if (status === 'claimed')   return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
    if (status === 'escalated') return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
    return '';
}

function showErrorState() {
    ticketsContainer.innerHTML = `
        <div class="empty-state">
            <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="var(--rose)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <p style="font-weight:700;color:var(--text-primary);font-size:0.9rem">Connection Failed</p>
            <p>Could not reach the API. Make sure the Python server is running at <strong>http://127.0.0.1:8000</strong></p>
        </div>
    `;
    lastRefreshedEl.textContent = 'Connection error';
}

function renderTickets() {
    const filtered = getFilteredTickets();

    if (filtered.length === 0) {
        const isSearch = searchQuery.length > 0;
        const isFilter = activeFilter !== 'all';
        ticketsContainer.innerHTML = `
            <div class="empty-state">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.4"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <p style="font-weight:600;color:var(--text-secondary)">${isSearch || isFilter ? 'No matching tickets' : 'No Support Tickets'}</p>
                <p>${isSearch ? `No results for "${escapeHTML(searchQuery)}".` : isFilter ? `No ${activeFilter} tickets right now.` : 'Submit a new query using the form to begin SLA monitoring.'}</p>
            </div>
        `;
        return;
    }

    // Remember expanded cards
    const expandedIds = new Set(
        [...ticketsContainer.querySelectorAll('.ticket-card.expanded')]
            .map(el => el.getAttribute('data-id'))
    );

    ticketsContainer.innerHTML = '';

    filtered.forEach((ticket, idx) => {
        const card = document.createElement('div');
        card.className = `ticket-card status-${ticket.status}`;
        card.setAttribute('data-id', ticket.id);
        card.setAttribute('role', 'article');
        card.style.animationDelay = `${idx * 40}ms`;

        const isExpanded = expandedIds.has(ticket.id);
        if (isExpanded) card.classList.add('expanded');

        const createdDate   = parseUTCDate(ticket.created_at);
        const deadlineDate  = parseUTCDate(ticket.sla_deadline);
        const claimedDate   = parseUTCDate(ticket.claimed_at);
        const escalatedDate = parseUTCDate(ticket.escalated_at);

        const priorityLabel = ticket.priority || 'medium';

        // ── Build SLA section ────────────────────────────────
        let slaSection = '';
        if (ticket.status === 'open') {
            slaSection = `
                <div class="sla-bar-wrap">
                    <div class="sla-bar-label">
                        <span>SLA Countdown</span>
                        <span class="sla-time" id="timer-${ticket.id}">Calculating…</span>
                    </div>
                    <div class="sla-bar-track">
                        <div class="sla-bar-fill safe" id="bar-${ticket.id}" style="width:100%"></div>
                    </div>
                </div>
            `;
        } else if (ticket.status === 'claimed') {
            let diffText = '';
            if (claimedDate && createdDate) {
                const diffSec = Math.round((claimedDate - createdDate) / 1000);
                diffText = ` in ${diffSec}s`;
            }
            slaSection = `
                <div class="ticket-resolved-banner">
                    <div class="banner-bar"></div>
                    <div class="banner-label">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                        Claim Details
                    </div>
                    <div class="banner-detail">Claimed by <strong>${escapeHTML(ticket.claimed_by || '—')}</strong>${diffText} at ${formatTime(claimedDate)}</div>
                </div>
            `;
        } else if (ticket.status === 'escalated') {
            slaSection = `
                <div class="ticket-escalated-banner">
                    <div class="banner-bar"></div>
                    <div class="banner-label">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                        SLA Breached — Escalated to Management
                    </div>
                    <div class="banner-detail">Escalated at ${formatTime(escalatedDate)}</div>
                </div>
            `;
        }

        // ── Build action row ─────────────────────────────────
        const actionRow = ticket.status === 'open' ? `
            <div class="ticket-action-row">
                <button class="btn-claim" data-id="${ticket.id}" aria-label="Claim ticket: ${escapeHTML(ticket.subject)}">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                    Claim Ticket
                </button>
                <span class="ticket-expand-hint">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" id="chevron-${ticket.id}" style="transition:transform 0.2s ease${isExpanded ? ';transform:rotate(180deg)' : ''}"><polyline points="6 9 12 15 18 9"/></svg>
                    <span id="expand-label-${ticket.id}">${isExpanded ? 'Collapse' : 'Expand'}</span>
                </span>
            </div>
        ` : `
            <div class="ticket-action-row">
                <span></span>
                <span class="ticket-expand-hint">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" id="chevron-${ticket.id}" style="transition:transform 0.2s ease${isExpanded ? ';transform:rotate(180deg)' : ''}"><polyline points="6 9 12 15 18 9"/></svg>
                    <span id="expand-label-${ticket.id}">${isExpanded ? 'Collapse' : 'Expand'}</span>
                </span>
            </div>
        `;

        // ── Build expanded detail ────────────────────────────
        const detailDrawer = `
            <div class="ticket-detail" style="display:${isExpanded ? 'flex' : 'none'};flex-direction:column;gap:4px" id="detail-${ticket.id}">
                <dl style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
                    <div>
                        <dt>Full UUID</dt>
                        <dd style="font-family:'Courier New',monospace;font-size:0.68rem;cursor:pointer;color:var(--blue)"
                            title="Click to copy"
                            onclick="navigator.clipboard.writeText('${ticket.id}').then(()=>showToast('info','Copied!','UUID copied to clipboard',2000))">
                            ${escapeHTML(ticket.id)}
                        </dd>
                    </div>
                    <div>
                        <dt>Priority</dt>
                        <dd style="text-transform:capitalize">${escapeHTML(priorityLabel)}</dd>
                    </div>
                    <div>
                        <dt>Created At</dt>
                        <dd>${formatTime(createdDate)}</dd>
                    </div>
                    <div>
                        <dt>SLA Deadline</dt>
                        <dd>${formatTime(deadlineDate)}</dd>
                    </div>
                    ${ticket.claimed_by ? `
                    <div>
                        <dt>Claimed By</dt>
                        <dd>${escapeHTML(ticket.claimed_by)}</dd>
                    </div>
                    <div>
                        <dt>Claimed At</dt>
                        <dd>${formatTime(claimedDate)}</dd>
                    </div>
                    ` : ''}
                    ${ticket.escalated_at ? `
                    <div style="grid-column:span 2">
                        <dt>Escalated At</dt>
                        <dd style="color:var(--rose)">${formatTime(escalatedDate)}</dd>
                    </div>
                    ` : ''}
                </dl>
            </div>
        `;

        // ── Assemble card ────────────────────────────────────
        card.innerHTML = `
            <div class="ticket-top">
                <div class="ticket-status-icon ${ticket.status}">${getStatusIcon(ticket.status)}</div>
                <div class="ticket-main">
                    <div class="ticket-subject">${escapeHTML(ticket.subject)}</div>
                    <div class="ticket-meta">
                        <span class="ticket-id-badge"
                            title="Click to copy UUID"
                            onclick="event.stopPropagation();navigator.clipboard.writeText('${ticket.id}').then(()=>showToast('info','Copied!','UUID copied to clipboard',2000))">
                            ${ticket.id.substring(0, 8)}…
                        </span>
                        <span class="ticket-time">
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                            ${formatTime(createdDate)}
                        </span>
                    </div>
                </div>
                <div class="ticket-badges">
                    <span class="badge badge-priority ${priorityLabel}">${priorityLabel}</span>
                    <span class="badge badge-status ${ticket.status}">${ticket.status}</span>
                </div>
            </div>
            ${slaSection}
            ${actionRow}
            ${detailDrawer}
        `;

        ticketsContainer.appendChild(card);
    });

    // Wire up claim buttons
    ticketsContainer.querySelectorAll('.btn-claim').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            openClaimModal(e.currentTarget.getAttribute('data-id'));
        });
    });

    // Wire up card expand/collapse
    ticketsContainer.querySelectorAll('.ticket-card').forEach(card => {
        card.addEventListener('click', e => {
            if (e.target.closest('button') || e.target.closest('.ticket-id-badge') || e.target.closest('dd[onclick]')) return;
            const id       = card.getAttribute('data-id');
            const detail   = document.getElementById(`detail-${id}`);
            const chevron  = document.getElementById(`chevron-${id}`);
            const label    = document.getElementById(`expand-label-${id}`);
            const expanded = card.classList.toggle('expanded');
            if (detail)  detail.style.display = expanded ? 'flex' : 'none';
            if (chevron) chevron.style.transform = expanded ? 'rotate(180deg)' : '';
            if (label)   label.textContent = expanded ? 'Collapse' : 'Expand';
        });
    });

    updateActiveTimers();
}


/* =============================================================
   SLA COUNTDOWN TIMERS
   ============================================================= */

function updateActiveTimers() {
    const now = new Date();

    tickets.forEach(ticket => {
        if (ticket.status !== 'open') return;

        const timerEl = document.getElementById(`timer-${ticket.id}`);
        const barEl   = document.getElementById(`bar-${ticket.id}`);
        if (!timerEl || !barEl) return;

        const created  = parseUTCDate(ticket.created_at);
        const deadline = parseUTCDate(ticket.sla_deadline);
        if (!created || !deadline) return;

        const totalMs     = deadline - created;
        const remainingMs = deadline - now;
        const remainSec   = Math.ceil(remainingMs / 1000);

        if (remainSec <= 0) {
            timerEl.textContent = 'Breaching SLA…';
            timerEl.className   = 'sla-time critical';
            barEl.style.width   = '100%';
            barEl.className     = 'sla-bar-fill breached';
        } else {
            timerEl.textContent = `${remainSec}s remaining`;
            const pct = Math.max(0, Math.min(100, (remainingMs / totalMs) * 100));
            barEl.style.width = `${pct}%`;

            if (remainSec > 30) {
                timerEl.className = 'sla-time';
                barEl.className   = 'sla-bar-fill safe';
            } else if (remainSec > 10) {
                timerEl.className = 'sla-time urgent';
                barEl.className   = 'sla-bar-fill warning';
            } else {
                timerEl.className = 'sla-time critical';
                barEl.className   = 'sla-bar-fill danger';
            }
        }
    });
}


/* =============================================================
   CREATE TICKET
   ============================================================= */

createForm.addEventListener('submit', async e => {
    e.preventDefault();
    const subject = subjectInput.value.trim();
    if (!subject) return;

    const btnCreate = document.getElementById('btn-create');
    btnCreate.disabled = true;
    btnCreate.querySelector('span').textContent = 'Creating…';

    try {
        const payload = { subject, priority: selectedPriority };
        const res = await fetch(`${API_URL}/tickets`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (res.ok) {
            subjectInput.value = '';
            showToast('success', 'Ticket Created', `"${subject.substring(0, 40)}" — SLA timer started.`);
            logActivity('created', subject);
            await fetchTickets();
        } else {
            const err = await res.json().catch(() => ({}));
            showToast('error', 'Creation Failed', err.error || 'Could not create ticket. Please try again.');
        }
    } catch (err) {
        console.error('Create ticket error:', err);
        showToast('error', 'Network Error', 'Could not reach the API server.');
    } finally {
        btnCreate.disabled = false;
        btnCreate.querySelector('span').textContent = 'Create Ticket';
    }
});


/* =============================================================
   CLAIM MODAL
   ============================================================= */

function openClaimModal(ticketId) {
    claimTicketIdInput.value = ticketId;
    agentNameInput.value     = '';
    claimModal.classList.add('active');
    setTimeout(() => agentNameInput.focus(), 50);
}

function closeClaimModal() {
    claimModal.classList.remove('active');
}

btnCancelClaim.addEventListener('click', closeClaimModal);
btnModalClose.addEventListener('click', closeClaimModal);
claimModal.addEventListener('click', e => { if (e.target === claimModal) closeClaimModal(); });
document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && claimModal.classList.contains('active')) closeClaimModal();
});

claimForm.addEventListener('submit', async e => {
    e.preventDefault();
    const ticketId = claimTicketIdInput.value;
    const agent    = agentNameInput.value.trim();
    if (!ticketId || !agent) return;

    const btnConfirm = claimForm.querySelector('[type="submit"]');
    btnConfirm.disabled = true;

    try {
        const res = await fetch(`${API_URL}/tickets/${ticketId}/claim`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ agent }),
        });

        if (res.ok) {
            const ticket = await res.json();
            closeClaimModal();
            showToast('success', 'Ticket Claimed', `Assigned to ${agent} successfully.`);
            logActivity('claimed', ticket.subject || ticketId, agent);
            await fetchTickets();
        } else {
            const err = await res.json().catch(() => ({}));
            showToast('error', 'Claim Failed', err.error || 'Could not claim this ticket.');
        }
    } catch (err) {
        console.error('Claim ticket error:', err);
        showToast('error', 'Network Error', 'Could not reach the API server.');
    } finally {
        btnConfirm.disabled = false;
    }
});


/* =============================================================
   REFRESH BUTTON
   ============================================================= */

btnRefresh.addEventListener('click', () => {
    refreshIcon.style.animation = 'spin 0.8s linear infinite';
    fetchTickets().then(() => {
        setTimeout(() => { refreshIcon.style.animation = ''; }, 800);
    });
});


/* =============================================================
   KEYBOARD SHORTCUT — N to focus new ticket input
   ============================================================= */

document.addEventListener('keydown', e => {
    const tag = e.target.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        subjectInput.focus();
        subjectInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
});


/* =============================================================
   LAST REFRESHED INDICATOR UPDATER
   ============================================================= */

setInterval(() => {
    if (lastRefreshAt) updateLastRefreshed();
}, 10000);


/* =============================================================
   INITIALISATION
   ============================================================= */

function init() {
    initTheme();
    fetchTickets();

    // Poll API every 3 seconds
    setInterval(fetchTickets, 3000);

    // Tick SLA countdowns every second
    setInterval(updateActiveTimers, 1000);
}

window.addEventListener('DOMContentLoaded', init);
