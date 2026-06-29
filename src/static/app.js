/**
 * Carfullfy SLA Escalation Engine — Client Application
 * Author: Muddassir Khan | Bootcamp 2026
 *
 * Features:
 *  - Real-time ticket polling (3s) + SLA countdown (1s)
 *  - Dark / Light mode with localStorage persistence
 *  - Status filter tabs (All / Open / Claimed / Escalated)
 *  - Subject search / filter
 *  - Priority selector (Low / Medium / High / Critical)
 *  - Toast notification system (replaces alert())
 *  - Activity feed / audit log panel
 *  - Expandable ticket cards with full detail view
 *  - "Last refreshed" indicator
 *  - Keyboard shortcut: N → focus new-ticket form
 *  - Stat cards animate when counts change
 */

'use strict';

const API_URL = ''; // Relative to host — served by Python server

// ── State ────────────────────────────────────────────────────
let tickets       = [];       // Master list from API
let activeFilter  = 'all';    // Current status filter
let searchQuery   = '';       // Current search string
let selectedPriority = 'medium'; // Currently selected priority
let lastRefreshAt = null;     // Date of last successful fetch
let lastStatValues = { total: 0, open: 0, claimed: 0, escalated: 0 };

// ── DOM refs ─────────────────────────────────────────────────
const ticketsContainer = document.getElementById('tickets-container');
const createForm       = document.getElementById('create-ticket-form');
const subjectInput     = document.getElementById('ticket-subject');
const btnRefresh       = document.getElementById('btn-refresh');
const refreshIcon      = document.getElementById('refresh-icon');
const lastRefreshedEl  = document.getElementById('last-refreshed');

// Stats
const valTotal     = document.getElementById('val-total');
const valOpen      = document.getElementById('val-open');
const valClaimed   = document.getElementById('val-claimed');
const valEscalated = document.getElementById('val-escalated');
const statCards    = {
    total:     document.getElementById('stat-total'),
    open:      document.getElementById('stat-open'),
    claimed:   document.getElementById('stat-claimed'),
    escalated: document.getElementById('stat-escalated'),
};

// Modal
const claimModal        = document.getElementById('claim-modal');
const claimForm         = document.getElementById('claim-ticket-form');
const claimTicketIdInput = document.getElementById('claim-ticket-id');
const agentNameInput    = document.getElementById('agent-name');
const btnCancelClaim    = document.getElementById('btn-cancel-claim');
const btnModalClose     = document.getElementById('btn-modal-close');

// Dark mode
const btnDarkMode = document.getElementById('btn-dark-mode');
const iconMoon    = document.getElementById('icon-moon');
const iconSun     = document.getElementById('icon-sun');

// Filter & search
const filterTabs  = document.querySelectorAll('.filter-tab');
const searchInput = document.getElementById('search-input');

// Activity feed
const activityList      = document.getElementById('activity-list');
const btnClearActivity  = document.getElementById('btn-clear-activity');

// Priority selector
const prioritySelector  = document.getElementById('priority-selector');

// Toast container
const toastContainer    = document.getElementById('toast-container');


/* =============================================================
   UTILITY HELPERS
   ============================================================= */

/** XSS-safe HTML escaping */
function escapeHTML(str) {
    if (!str) return '';
    return String(str).replace(/[&<>'"]/g,
        tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
}

/** Parse ISO date string as UTC */
function parseUTCDate(dateStr) {
    if (!dateStr) return null;
    const s = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z';
    return new Date(s);
}

/** Format as hh:mm:ss local time */
function formatTime(date) {
    if (!date) return '—';
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/** Format as relative time ago (max 60 minutes) */
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
    const stored = localStorage.getItem('carfullfy-theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const dark = stored === 'dark' || (!stored && prefersDark);
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

/**
 * Show a toast notification.
 * @param {'success'|'error'|'info'|'warning'} type
 * @param {string} title
 * @param {string} [message]
 * @param {number} [duration=4000] ms
 */
function showToast(type, title, message = '', duration = 4000) {
    const icons = {
        success: `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,
        error:   `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
        info:    `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
        warning: `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.style.setProperty('--toast-duration', `${duration}ms`);
    toast.innerHTML = `
        ${icons[type] || icons.info}
        <div class="toast-body">
            <div class="toast-title">${escapeHTML(title)}</div>
            ${message ? `<div class="toast-message">${escapeHTML(message)}</div>` : ''}
        </div>
        <button class="toast-close" aria-label="Dismiss notification">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </button>
    `;

    toastContainer.appendChild(toast);

    const dismiss = () => {
        toast.classList.add('leaving');
        setTimeout(() => toast.remove(), 280);
    };

    toast.querySelector('.toast-close').addEventListener('click', dismiss);
    setTimeout(dismiss, duration);
}


/* =============================================================
   ACTIVITY FEED
   ============================================================= */

const activityLog = [];

/**
 * Add an event to the activity feed.
 * @param {'created'|'claimed'|'escalated'} type
 * @param {string} subject  - ticket subject (truncated)
 * @param {string} [detail] - extra context (e.g. agent name)
 */
function logActivity(type, subject, detail = '') {
    const now = new Date();
    activityLog.unshift({ type, subject, detail, time: now });

    // Remove empty state
    const emptyEl = activityList.querySelector('.activity-empty');
    if (emptyEl) emptyEl.remove();

    const labels = { created: 'Ticket created', claimed: 'Ticket claimed', escalated: 'SLA breached' };
    const detailText = detail ? ` by <strong>${escapeHTML(detail)}</strong>` : '';

    const li = document.createElement('li');
    li.className = 'activity-item';
    li.innerHTML = `
        <span class="activity-dot ${type}"></span>
        <div style="flex:1;min-width:0">
            <div class="activity-text">
                <strong>${escapeHTML(labels[type] || type)}</strong>${detailText}
                <div style="color:var(--text-muted);margin-top:0.1rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                    ${escapeHTML(subject.length > 42 ? subject.substring(0, 42) + '…' : subject)}
                </div>
            </div>
            <div class="activity-time">${formatTime(now)}</div>
        </div>
    `;

    activityList.insertBefore(li, activityList.firstChild);

    // Keep max 30 items in DOM
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
            // Trigger pop animation
            const card = statCards[key];
            card.classList.remove('pop');
            void card.offsetWidth; // reflow to restart animation
            card.classList.add('pop');
            setTimeout(() => card.classList.remove('pop'), 450);
        }
    });

    lastStatValues = { ...newStats };
}


/* =============================================================
   FILTER & SEARCH
   ============================================================= */

// Filter tabs
filterTabs.forEach(tab => {
    tab.addEventListener('click', () => {
        filterTabs.forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');
        activeFilter = tab.getAttribute('data-filter');
        renderTickets();
    });
});

// Search
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

// Track previously-seen IDs for activity log diffing
const seenTicketIds = new Set();
const prevStatuses  = {};

async function fetchTickets() {
    try {
        const response = await fetch(`${API_URL}/tickets`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        // Detect new & status-changed tickets for activity log
        data.forEach(t => {
            if (!seenTicketIds.has(t.id)) {
                seenTicketIds.add(t.id);
                if (tickets.length > 0) {
                    // Only log if app is already initialised (avoid flood on first load)
                    logActivity('created', t.subject);
                }
            } else if (prevStatuses[t.id] && prevStatuses[t.id] !== t.status) {
                if (t.status === 'claimed')   logActivity('claimed',   t.subject, t.claimed_by);
                if (t.status === 'escalated') logActivity('escalated', t.subject);
            }
            prevStatuses[t.id] = t.status;
        });

        // On first load, seed seenIds & prevStatuses without logging
        if (tickets.length === 0 && data.length > 0) {
            data.forEach(t => seenTicketIds.add(t.id));
        }

        tickets = data;
        lastRefreshAt = new Date();

        // Compute stats
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

function showErrorState() {
    ticketsContainer.innerHTML = `
        <div class="empty-state">
            <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#EF4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <h3>Connection Failed</h3>
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
                <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                <h3>${isSearch || isFilter ? 'No matching tickets' : 'No Support Tickets'}</h3>
                <p>${isSearch ? `No results for "${searchQuery}".` : isFilter ? `No ${activeFilter} tickets right now.` : 'Submit a new query using the form to begin SLA monitoring.'}</p>
            </div>
        `;
        return;
    }

    // Remember which cards are expanded
    const expandedIds = new Set(
        [...ticketsContainer.querySelectorAll('.ticket-card.expanded')]
            .map(el => el.getAttribute('data-id'))
    );

    ticketsContainer.innerHTML = '';

    filtered.forEach(ticket => {
        const card = document.createElement('div');
        card.className = `ticket-card status-${ticket.status}`;
        card.setAttribute('data-id', ticket.id);
        card.setAttribute('role', 'article');
        card.setAttribute('aria-label', `Ticket: ${ticket.subject}`);

        const isExpanded = expandedIds.has(ticket.id);
        if (isExpanded) card.classList.add('expanded');

        const createdDate   = parseUTCDate(ticket.created_at);
        const deadlineDate  = parseUTCDate(ticket.sla_deadline);
        const claimedDate   = parseUTCDate(ticket.claimed_at);
        const escalatedDate = parseUTCDate(ticket.escalated_at);

        // ── Badge HTML ───────────────────────────────────────
        const priorityLabel = ticket.priority || 'medium';
        const priorityBadgeHtml = `<span class="priority-badge ${priorityLabel}">${priorityLabel}</span>`;

        let statusBadgeHtml = '';
        if (ticket.status === 'open')      statusBadgeHtml = `<span class="badge badge-open">Open</span>`;
        else if (ticket.status === 'claimed')   statusBadgeHtml = `<span class="badge badge-claimed">Claimed</span>`;
        else if (ticket.status === 'escalated') statusBadgeHtml = `<span class="badge badge-escalated">Escalated</span>`;

        // ── SLA progress HTML ────────────────────────────────
        let slaHtml = '';
        if (ticket.status === 'open') {
            slaHtml = `
                <div class="sla-progress-container">
                    <div class="sla-header">
                        <span>SLA Countdown</span>
                        <span class="sla-countdown-timer" id="timer-${ticket.id}">Calculating…</span>
                    </div>
                    <div class="sla-progress-bar">
                        <div class="sla-progress-fill green" id="bar-${ticket.id}" style="width:100%"></div>
                    </div>
                    <div class="sla-deadline-abs">Deadline: ${formatTime(deadlineDate)}</div>
                </div>
            `;
        } else if (ticket.status === 'claimed') {
            let claimedText = `Claimed by <strong>${escapeHTML(ticket.claimed_by || '—')}</strong>`;
            if (claimedDate && createdDate) {
                const diffSec = Math.round((claimedDate - createdDate) / 1000);
                claimedText += ` in ${diffSec}s`;
            }
            slaHtml = `
                <div class="sla-progress-container">
                    <div class="sla-header">
                        <span>Claim Details</span>
                        <span style="color:var(--claimed)">✓ Resolved</span>
                    </div>
                    <div class="sla-progress-bar">
                        <div class="sla-progress-fill" style="width:100%;background:var(--claimed)"></div>
                    </div>
                    <div class="sla-deadline-abs">${claimedText} at ${formatTime(claimedDate)}</div>
                </div>
            `;
        } else if (ticket.status === 'escalated') {
            slaHtml = `
                <div class="sla-progress-container">
                    <div class="sla-header" style="color:var(--escalated)">
                        <span>⚠ SLA Breached</span>
                        <span>Escalated</span>
                    </div>
                    <div class="sla-progress-bar">
                        <div class="sla-progress-fill red" style="width:100%"></div>
                    </div>
                    <div class="sla-deadline-abs" style="color:var(--escalated)">Escalated to management at ${formatTime(escalatedDate)}</div>
                </div>
            `;
        }

        // ── Claim button ─────────────────────────────────────
        const actionHtml = ticket.status === 'open' ? `
            <div class="ticket-actions">
                <button class="btn-claim" data-id="${ticket.id}" aria-label="Claim ticket: ${escapeHTML(ticket.subject)}">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                    Claim Ticket
                </button>
            </div>
        ` : '';

        // ── Expanded detail view ──────────────────────────────
        const detailsHtml = `
            <div class="ticket-details">
                <div class="ticket-details-grid">
                    <div class="detail-item">
                        <span class="detail-label">Full UUID</span>
                        <span class="detail-value mono" title="Click to copy" onclick="navigator.clipboard.writeText('${ticket.id}').then(()=>showToast('info','Copied!','UUID copied to clipboard',2000))" style="cursor:pointer">${escapeHTML(ticket.id)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Status</span>
                        <span class="detail-value" style="text-transform:capitalize">${escapeHTML(ticket.status)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Created At</span>
                        <span class="detail-value">${formatTime(createdDate)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">SLA Deadline</span>
                        <span class="detail-value">${formatTime(deadlineDate)}</span>
                    </div>
                    ${ticket.claimed_by ? `
                    <div class="detail-item">
                        <span class="detail-label">Claimed By</span>
                        <span class="detail-value">${escapeHTML(ticket.claimed_by)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">Claimed At</span>
                        <span class="detail-value">${formatTime(claimedDate)}</span>
                    </div>
                    ` : ''}
                    ${ticket.escalated_at ? `
                    <div class="detail-item">
                        <span class="detail-label">Escalated At</span>
                        <span class="detail-value" style="color:var(--escalated)">${formatTime(escalatedDate)}</span>
                    </div>
                    ` : ''}
                    <div class="detail-item">
                        <span class="detail-label">Priority</span>
                        <span class="detail-value" style="text-transform:capitalize">${priorityLabel}</span>
                    </div>
                </div>
            </div>
        `;

        // ── Assemble card ─────────────────────────────────────
        card.innerHTML = `
            <div class="ticket-top">
                <div class="ticket-title">${escapeHTML(ticket.subject)}</div>
                <div class="ticket-badges">
                    ${priorityBadgeHtml}
                    ${statusBadgeHtml}
                </div>
            </div>

            <div class="ticket-meta">
                <div class="meta-item">
                    <span class="ticket-id-badge" title="Click to copy UUID" onclick="event.stopPropagation();navigator.clipboard.writeText('${ticket.id}').then(()=>showToast('info','Copied!','UUID copied to clipboard',2000))">
                        ${ticket.id.substring(0, 8)}…
                    </span>
                </div>
                <div class="meta-item">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    <span>${formatTime(createdDate)}</span>
                </div>
            </div>

            ${slaHtml}
            ${actionHtml}
            ${detailsHtml}
            <div class="expand-hint">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" id="chevron-${ticket.id}"><polyline points="6 9 12 15 18 9"/></svg>
                <span id="expand-label-${ticket.id}">${isExpanded ? 'Click to collapse' : 'Click to expand'}</span>
            </div>
        `;

        // Update chevron direction for expanded cards
        if (isExpanded) {
            const chevron = card.querySelector(`#chevron-${ticket.id}`);
            if (chevron) chevron.style.transform = 'rotate(180deg)';
        }

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
            // Don't expand if clicking a button or the id badge
            if (e.target.closest('button') || e.target.closest('.ticket-id-badge')) return;
            const wasExpanded = card.classList.contains('expanded');
            card.classList.toggle('expanded');
            const id = card.getAttribute('data-id');
            const chevron = card.querySelector(`#chevron-${id}`);
            const label   = card.querySelector(`#expand-label-${id}`);
            if (chevron) chevron.style.transform = wasExpanded ? '' : 'rotate(180deg)';
            if (label)   label.textContent = wasExpanded ? 'Click to expand' : 'Click to collapse';
        });
    });

    // Immediately update SLA timers
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
            timerEl.textContent      = 'Breaching SLA…';
            timerEl.style.color      = 'var(--escalated)';
            barEl.style.width        = '0%';
            barEl.className          = 'sla-progress-fill red';
        } else {
            timerEl.textContent = `${remainSec}s remaining`;
            const pct = Math.max(0, Math.min(100, (remainingMs / totalMs) * 100));
            barEl.style.width = `${pct}%`;

            if (remainSec > 30) {
                timerEl.style.color = 'var(--text-muted)';
                barEl.className     = 'sla-progress-fill green';
            } else if (remainSec > 10) {
                timerEl.style.color = 'var(--open)';
                barEl.className     = 'sla-progress-fill orange';
            } else {
                timerEl.style.color = 'var(--escalated)';
                barEl.className     = 'sla-progress-fill red';
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
            const ticket = await res.json();
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

// Close on backdrop click
claimModal.addEventListener('click', e => {
    if (e.target === claimModal) closeClaimModal();
});

// Close on Escape
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
   MANUAL REFRESH BUTTON
   ============================================================= */

btnRefresh.addEventListener('click', () => {
    refreshIcon.classList.add('spin-animation');
    fetchTickets().then(() => {
        setTimeout(() => refreshIcon.classList.remove('spin-animation'), 800);
    });
});


/* =============================================================
   KEYBOARD SHORTCUT — N to focus new ticket form
   ============================================================= */

document.addEventListener('keydown', e => {
    // Don't intercept if user is typing in an input/textarea
    const tag = e.target.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        subjectInput.focus();
        subjectInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
});


/* =============================================================
   LAST REFRESHED INDICATOR
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
