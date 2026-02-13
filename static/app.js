// MediaPulse Frontend v5
let currentPlayer = null;
let currentPlayerId = null;
let pollInterval = null;
let charts = {};
let alertFilter = { severity: null, unread: false };
let pagination = { press: 0, social: 0, activity: 0 };
const PAGE_SIZE = 50;
const STANDARD_SCAN_DAYS = 7;
let dateRange = { from: null, to: null, preset: 'all' };

// -- Launch scan from setup panel --
async function launchScan() {
    const name = document.getElementById('inp-name').value.trim();
    if (!name) return alert('Introduce el nombre del jugador');

    const data = {
        name,
        twitter: document.getElementById('inp-twitter').value.trim() || null,
        instagram: document.getElementById('inp-instagram').value.trim() || null,
        club: document.getElementById('inp-club').value.trim() || null,
        transfermarkt_id: document.getElementById('inp-tm').value.trim() || null,
        tiktok: document.getElementById('inp-tiktok')?.value.trim() || null,
    };

    document.getElementById('setup-panel').classList.add('hidden');
    document.getElementById('scan-progress').classList.remove('hidden');

    try {
        const resp = await fetch('/api/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) throw new Error(await resp.text());
        pollScanStatus();
    } catch (e) {
        document.getElementById('scan-message').textContent = 'Error: ' + e.message;
    }
}

// -- Re-scan from header button --
async function startScan() {
    if (!currentPlayer) return;
    document.getElementById('dashboard').classList.add('hidden');
    document.getElementById('scan-progress').classList.remove('hidden');
    document.getElementById('scan-message').textContent = 'Iniciando escaneo...';

    try {
        const resp = await fetch('/api/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentPlayer),
        });
        if (!resp.ok) throw new Error(await resp.text());
        pollScanStatus();
    } catch (e) {
        document.getElementById('scan-message').textContent = 'Error: ' + e.message;
    }
}

// -- Player Switcher --
async function showPlayerSwitcher() {
    const modal = document.getElementById('player-modal');
    modal.classList.remove('hidden');

    const players = await fetch('/api/players').then(r => r.json());
    const list = document.getElementById('player-list');
    list.innerHTML = players.map(p => `
        <div class="flex items-center justify-between p-3 rounded-lg bg-dark-900 cursor-pointer hover:bg-dark-600 transition ${p.id === currentPlayerId ? 'border border-accent' : ''}"
             onclick="switchToPlayer(${p.id})">
            <div class="flex items-center gap-3">
                ${p.photo_url
                    ? `<img src="${p.photo_url}" class="w-8 h-8 rounded-full object-cover">`
                    : `<div class="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center text-accent text-xs font-bold">${(p.name || '').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()}</div>`
                }
                <div>
                    <div class="text-sm font-medium text-white">${p.name}</div>
                    <div class="text-xs text-gray-500">${p.club || ''} ${p.twitter ? '| @' + p.twitter : ''}</div>
                </div>
            </div>
            ${p.id === currentPlayerId ? '<span class="text-xs text-accent">Actual</span>' : ''}
        </div>
    `).join('');
}

function hidePlayerSwitcher() {
    document.getElementById('player-modal').classList.add('hidden');
}

async function switchToPlayer(playerId) {
    hidePlayerSwitcher();
    await loadDashboard(playerId);
}

async function addAndScanPlayer() {
    const name = document.getElementById('modal-name').value.trim();
    if (!name) return alert('Introduce el nombre');

    const data = {
        name,
        twitter: document.getElementById('modal-twitter').value.trim() || null,
        instagram: document.getElementById('modal-instagram').value.trim() || null,
        club: document.getElementById('modal-club').value.trim() || null,
        transfermarkt_id: document.getElementById('modal-tm').value.trim() || null,
        tiktok: document.getElementById('modal-tiktok')?.value.trim() || null,
    };

    hidePlayerSwitcher();
    document.getElementById('dashboard').classList.add('hidden');
    document.getElementById('scan-progress').classList.remove('hidden');
    document.getElementById('scan-message').textContent = 'Iniciando escaneo...';

    try {
        const resp = await fetch('/api/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) throw new Error(await resp.text());
        pollScanStatus();
    } catch (e) {
        document.getElementById('scan-message').textContent = 'Error: ' + e.message;
    }
}

// -- PDF Export --
function exportPDF() {
    if (!currentPlayerId) return;
    window.open(`/api/export/pdf?player_id=${currentPlayerId}`, '_blank');
}

// -- CSV Export --
function exportCSV(type) {
    if (!currentPlayerId) return;
    window.open(`/api/export/csv?player_id=${currentPlayerId}&type=${type}`, '_blank');
}

// -- Poll scan status --
function pollScanStatus() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(async () => {
        try {
            const resp = await fetch('/api/scan/status');
            const status = await resp.json();
            document.getElementById('scan-message').textContent = status.progress || '...';

            if (!status.running && status.player_id) {
                clearInterval(pollInterval);
                pollInterval = null;
                await loadDashboard(status.player_id);
            }
        } catch (e) {
            console.error('Poll error:', e);
        }
    }, 2000);
}

// -- Load dashboard --
async function loadDashboard(playerId) {
    currentPlayerId = playerId;
    document.getElementById('scan-progress').classList.add('hidden');
    document.getElementById('setup-panel').classList.add('hidden');
    document.getElementById('dashboard').classList.remove('hidden');
    document.getElementById('btn-scan').classList.remove('hidden');
    document.getElementById('btn-export').classList.remove('hidden');
    document.getElementById('btn-switch').classList.remove('hidden');
    document.getElementById('btn-portfolio').classList.remove('hidden');
    document.getElementById('player-header').classList.remove('hidden');

    // Load player info
    const playerResp = await fetch(`/api/player/${playerId}`);
    currentPlayer = await playerResp.json();
    if (currentPlayer) {
        document.getElementById('header-name').textContent = currentPlayer.name;
        document.getElementById('header-club').textContent = [
            currentPlayer.club,
            currentPlayer.twitter ? '@' + currentPlayer.twitter : '',
        ].filter(Boolean).join(' | ');

        // Player photo
        const photoContainer = document.getElementById('header-photo-container');
        const initialsEl = document.getElementById('header-initials');
        if (currentPlayer.photo_url) {
            document.getElementById('header-photo').src = currentPlayer.photo_url;
            photoContainer.classList.remove('hidden');
            initialsEl.classList.add('hidden');
        } else {
            photoContainer.classList.add('hidden');
            const initials = (currentPlayer.name || '').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
            initialsEl.textContent = initials;
            initialsEl.classList.remove('hidden');
        }

        // Transfermarkt info
        const tmInfo = document.getElementById('header-tm-info');
        if (currentPlayer.market_value || currentPlayer.contract_until) {
            tmInfo.classList.remove('hidden');
            document.getElementById('header-market-value').textContent = currentPlayer.market_value || '';
            document.getElementById('header-contract').textContent = currentPlayer.contract_until ? `Contrato: ${currentPlayer.contract_until}` : '';
        } else {
            tmInfo.classList.add('hidden');
        }
    }

    // Show loading skeletons
    showSkeletons();

    // Reset pagination
    pagination = { press: 0, social: 0, activity: 0 };

    // Initialize date range to "all" on first load (user can narrow it)
    dateRange = { from: null, to: null, preset: 'all' };
    const dateFromEl = document.getElementById('date-from');
    const dateToEl = document.getElementById('date-to');
    if (dateFromEl) dateFromEl.value = '';
    if (dateToEl) dateToEl.value = '';
    document.querySelectorAll('.date-range-btn').forEach(b => b.classList.remove('active'));
    const allBtn = document.querySelector('[data-range="all"]');
    if (allBtn) allBtn.classList.add('active');

    const dp = buildDateParams();

    // Load scheduler status + last scan + costs
    loadSchedulerStatus();
    loadLastScan(playerId);
    loadCosts();

    // Load all data in parallel
    const [summary, report, press, social, activity, alerts, stats, scans, imageIndex, weeklyReports,
           sentByPlatform, activityPeaks, topInfluencers, idxHistory, intelligence] = await Promise.all([
        fetch(`/api/summary?player_id=${playerId}${dp}`).then(r => r.json()),
        fetch(`/api/report?player_id=${playerId}`).then(r => r.json()).catch(() => null),
        fetch(`/api/press?player_id=${playerId}${dp}`).then(r => r.json()),
        fetch(`/api/social?player_id=${playerId}${dp}`).then(r => r.json()),
        fetch(`/api/activity?player_id=${playerId}${dp}`).then(r => r.json()),
        fetch(`/api/alerts?player_id=${playerId}`).then(r => r.json()),
        fetch(`/api/stats?player_id=${playerId}${dp}`).then(r => r.json()),
        fetch(`/api/scans?player_id=${playerId}`).then(r => r.json()).catch(() => []),
        fetch(`/api/player/${playerId}/image-index`).then(r => r.json()).catch(() => null),
        fetch(`/api/player/${playerId}/weekly-reports?limit=5`).then(r => r.json()).catch(() => []),
        fetch(`/api/player/${playerId}/sentiment-by-platform`).then(r => r.json()).catch(() => []),
        fetch(`/api/player/${playerId}/activity-peaks`).then(r => r.json()).catch(() => null),
        fetch(`/api/player/${playerId}/top-influencers`).then(r => r.json()).catch(() => []),
        fetch(`/api/player/${playerId}/image-index-history`).then(r => r.json()).catch(() => []),
        fetch(`/api/player/${playerId}/intelligence`).then(r => r.json()).catch(() => null),
    ]);

    // Store data for search/filter
    window._currentData = { press, social, activity, alerts };

    // Alert badge + browser tab notification
    const unreadAlerts = alerts.filter(a => !a.read);
    const badge = document.getElementById('alert-badge');
    if (unreadAlerts.length > 0) {
        badge.textContent = unreadAlerts.length;
        badge.classList.remove('hidden');
        document.title = `(${unreadAlerts.length}) MediaPulse`;
    } else {
        badge.classList.add('hidden');
        document.title = 'MediaPulse';
    }

    // Risk badge on intelligence tab
    const riskBadge = document.getElementById('risk-badge');
    if (intelligence && intelligence.risk_score !== undefined) {
        const rs = Math.round(intelligence.risk_score);
        riskBadge.textContent = rs;
        riskBadge.classList.remove('hidden');
        const rbColor = rs >= 70 ? 'bg-red-500 text-white' : rs >= 40 ? 'bg-yellow-500 text-black' : 'bg-green-600 text-white';
        riskBadge.className = `ml-1 text-xs px-1.5 py-0.5 rounded-full ${rbColor}`;
    } else {
        riskBadge.classList.add('hidden');
    }

    // Render Image Index
    renderImageIndex(imageIndex, idxHistory);

    // Render executive summary
    renderExecutiveSummary(report);

    // Render summary cards with deltas
    renderSummaryCards(summary, report?.delta);

    // Render topics & brands (word cloud)
    renderTopicsAndBrands(report);

    // Render tabs
    renderPress(press, stats);
    renderSocial(social, stats, sentByPlatform, topInfluencers);
    renderActivity(activity, stats, activityPeaks);
    renderAlerts(alerts);
    renderHistorial(scans);
    renderHistorico(stats);
    renderInteligencia(intelligence);
    renderInforme(weeklyReports, imageIndex);

    switchTab('prensa');
}

// -- Scheduler Status --
async function loadSchedulerStatus() {
    try {
        const resp = await fetch('/api/scheduler/status');
        const status = await resp.json();
        const indicator = document.getElementById('scheduler-indicator');
        if (status.enabled && status.running) {
            indicator.classList.remove('hidden');
            document.getElementById('scheduler-text').textContent = `Auto ${status.schedule}`;
        } else {
            indicator.classList.add('hidden');
        }
    } catch (e) {}
}

// -- Last Scan Info --
async function loadLastScan(playerId) {
    try {
        const resp = await fetch(`/api/last-scan?player_id=${playerId}`);
        const scan = await resp.json();
        const indicator = document.getElementById('scheduler-indicator');
        if (scan && scan.finished_at) {
            const txt = document.getElementById('scheduler-text');
            const existing = txt.textContent;
            const ago = timeAgo(scan.finished_at);
            txt.textContent = existing.includes('Auto') ? `${existing} | Ultimo: ${ago}` : `Ultimo: ${ago}`;
            indicator.classList.remove('hidden');
        }
    } catch (e) {}
}

// -- Cost Indicator --
async function loadCosts() {
    try {
        const costs = await fetch('/api/costs').then(r => r.json());
        const el = document.getElementById('cost-indicator');
        if (el && costs) {
            el.textContent = `$${costs.estimated_month_usd.toFixed(2)} este mes`;
            el.title = `Total: $${costs.estimated_total_usd.toFixed(2)} | ${costs.total_scans} escaneos | ${costs.total_items} items`;
            el.classList.remove('hidden');
        }
    } catch (e) {}
}

function timeAgo(dateStr) {
    const d = new Date(dateStr);
    const now = new Date();
    const diff = Math.floor((now - d) / 1000);
    if (diff < 60) return 'hace segundos';
    if (diff < 3600) return `hace ${Math.floor(diff/60)}m`;
    if (diff < 86400) return `hace ${Math.floor(diff/3600)}h`;
    return `hace ${Math.floor(diff/86400)}d`;
}

// -- Executive Summary --
function renderExecutiveSummary(report) {
    const el = document.getElementById('executive-summary');
    if (!report || !report.executive_summary) {
        el.classList.add('hidden');
        return;
    }
    el.classList.remove('hidden');
    document.getElementById('exec-summary-text').textContent = report.executive_summary;
    document.getElementById('report-date').textContent = formatDate(report.created_at);
}

// -- Topics & Brands (Word Cloud) --
function renderTopicsAndBrands(report) {
    const row = document.getElementById('topics-brands-row');
    if (!report) { row.classList.add('hidden'); return; }

    const topics = report.topics || {};
    const brands = report.brands || {};

    if (Object.keys(topics).length === 0 && Object.keys(brands).length === 0) {
        row.classList.add('hidden');
        return;
    }

    row.classList.remove('hidden');

    const topicColors = {
        fichaje: '#1d9bf0', rendimiento: '#00ba7c', lesion: '#f4212e', vida_personal: '#a855f7',
        polemica: '#ef4444', sponsors: '#f59e0b', aficion: '#06b6d4', entrenador: '#8b5cf6',
        seleccion: '#10b981', tactica: '#6366f1', cantera: '#14b8a6', economia: '#f97316', otro: '#6b7280',
    };

    // Word cloud: scale font from 13px to 32px based on frequency
    const maxCount = Math.max(...Object.values(topics), 1);
    const minFont = 13, maxFont = 32;
    document.getElementById('topics-container').innerHTML = Object.entries(topics).map(([t, c]) => {
        const color = topicColors[t] || '#6b7280';
        const ratio = c / maxCount;
        const fontSize = Math.round(minFont + ratio * (maxFont - minFont));
        const opacity = 0.5 + ratio * 0.5;
        return `<span class="word-cloud-item" style="color:${color};font-size:${fontSize}px;opacity:${opacity};padding:2px 8px;display:inline-block;cursor:default;" title="${t}: ${c} menciones">${t}</span>`;
    }).join('') || '<span class="text-gray-600 text-sm">Sin temas</span>';

    const maxBrand = Math.max(...Object.values(brands), 1);
    document.getElementById('brands-container').innerHTML = Object.entries(brands).map(([b, c]) => {
        const ratio = c / maxBrand;
        const fontSize = Math.round(minFont + ratio * (maxFont - minFont));
        return `<span class="word-cloud-item" style="color:#e1306c;font-size:${fontSize}px;opacity:${0.5 + ratio * 0.5};padding:2px 8px;display:inline-block;" title="${b}: ${c} menciones">${b}</span>`;
    }).join('') || '<span class="text-gray-600 text-sm">Ninguna detectada</span>';
}

// -- Summary Cards with Deltas --
function renderSummaryCards(s, delta) {
    delta = delta || {};

    function deltaHtml(key) {
        const v = delta[key];
        if (v === undefined || v === null) return '';
        const arrow = v > 0 ? '+' : '';
        const color = v > 0 ? '#00ba7c' : v < 0 ? '#f4212e' : '#666';
        const display = typeof v === 'number' && !Number.isInteger(v) ? v.toFixed(2) : v;
        return `<span style="color:${color};font-size:10px;margin-left:4px;">(${arrow}${display})</span>`;
    }

    const cards = [
        { label: 'Noticias', value: s.press_count, delta: deltaHtml('press_count'), icon: 'N', color: 'accent', tab: 'prensa', tooltip: 'Total de noticias en prensa digital que mencionan al jugador' },
        { label: 'Sent. Prensa', value: sentimentText(s.press_sentiment), delta: deltaHtml('press_sentiment'), icon: 'S', color: sentimentColor(s.press_sentiment), tab: 'prensa', tooltip: 'Sentimiento medio de la prensa (-1.0 negativo a +1.0 positivo)' },
        { label: 'Menciones', value: s.mentions_count, delta: deltaHtml('mentions_count'), icon: 'M', color: 'accent', tab: 'redes', tooltip: 'Menciones en redes: X, Reddit, YouTube, TikTok, Instagram, Telegram' },
        { label: 'Sent. Redes', value: sentimentText(s.social_sentiment), delta: deltaHtml('social_sentiment'), icon: 'R', color: sentimentColor(s.social_sentiment), tab: 'redes', tooltip: 'Sentimiento medio en redes sociales (-1.0 a +1.0)' },
        { label: 'Posts Jugador', value: s.posts_count, delta: '', icon: 'P', color: 'accent', tab: 'actividad', tooltip: 'Publicaciones propias del jugador en sus cuentas' },
        { label: 'Engagement', value: s.avg_engagement ? (s.avg_engagement * 100).toFixed(2) + '%' : 'Sin datos', delta: '', icon: 'E', color: 'accent', tab: 'actividad', tooltip: s.avg_engagement ? 'Tasa de interaccion media: (likes+comentarios+shares)/vistas' : 'Sin datos. Configura handles del jugador para rastrear sus publicaciones.' },
        { label: 'Sent. Jugador', value: sentimentText(s.player_sentiment), delta: '', icon: 'J', color: sentimentColor(s.player_sentiment), tab: 'actividad', tooltip: 'Sentimiento de las publicaciones propias del jugador' },
        { label: 'Alertas', value: s.alerts_count, delta: '', icon: '!', color: s.alerts_count > 0 ? 'negative' : 'positive', tab: 'alertas', tooltip: 'Alertas activas: fichajes, lesiones, polemica, inactividad' },
    ];

    document.getElementById('summary-cards').innerHTML = cards.map((c, i) => {
        const isEmpty = (c.value === 0 || c.value === 'Sin datos' || c.value === '-');
        return `
        <div class="bg-dark-700 rounded-xl p-3 sm:p-4 border border-gray-800 fade-in cursor-pointer hover:border-gray-600 transition ${isEmpty ? 'opacity-60' : ''}" style="animation-delay: ${i * 50}ms" onclick="switchTab('${c.tab}')" data-tooltip="${c.tooltip}" data-tooltip-pos="below">
            <div class="flex items-center justify-between mb-1 sm:mb-2">
                <span class="text-[10px] sm:text-xs text-gray-500 uppercase tracking-wider">${c.label}</span>
            </div>
            <div class="text-lg sm:text-2xl font-bold text-white">${c.value ?? '-'}${c.delta}</div>
        </div>
    `}).join('');
}

// -- Press Tab --
function renderPress(items, stats) {
    const container = document.getElementById('tab-prensa');
    const sentDist = buildSentimentDist(stats.press_sentiment);
    const sourcesDist = stats.press_sources || [];

    container.innerHTML = `
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
            <div class="lg:col-span-2 order-2 lg:order-1">
                <div class="bg-dark-700 rounded-xl border border-gray-800">
                    <div class="p-3 sm:p-4 border-b border-gray-800">
                        <div class="flex items-center justify-between mb-2">
                            <h3 class="font-semibold text-white text-sm sm:text-base">Noticias (${items.length})</h3>
                            <button onclick="exportCSV('press')" class="text-xs text-accent hover:underline touch-target">CSV</button>
                        </div>
                        <input type="text" placeholder="Buscar en noticias..." class="w-full bg-dark-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:border-accent focus:outline-none" oninput="filterList(this.value, 'press')">
                    </div>
                    <div class="item-list max-h-[500px] sm:max-h-[600px] overflow-y-auto" id="press-list">
                        ${items.length === 0 ? '<div class="p-8 text-center text-gray-600">Sin noticias</div>' :
                        items.map(item => `
                            <div class="p-3 sm:p-4 card-hover search-item" data-search="${escapeHtml((item.source || '') + ' ' + (item.title || '') + ' ' + (item.sentiment_label || '')).toLowerCase()}">
                                <div class="flex items-start justify-between gap-2 sm:gap-3">
                                    <div class="flex-1 min-w-0">
                                        <div class="flex items-center gap-1 sm:gap-2 mb-1 flex-wrap">
                                            <span class="text-[10px] sm:text-xs px-2 py-0.5 rounded-full bg-dark-500 text-gray-400">${item.source || ''}</span>
                                            <span class="text-[10px] sm:text-xs px-2 py-0.5 rounded-full badge-${item.sentiment_label || 'neutro'}">${item.sentiment_label || 'neutro'}</span>
                                        </div>
                                        <a href="${item.url}" target="_blank" class="text-xs sm:text-sm text-white hover:text-accent transition line-clamp-2">${item.title}</a>
                                        <div class="text-[10px] sm:text-xs text-gray-600 mt-1">${formatDate(item.published_at)}</div>
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                        ${items.length >= PAGE_SIZE ? `<div class="p-4 text-center"><button onclick="loadMorePress()" class="text-sm text-accent hover:underline touch-target">Cargar mas...</button></div>` : ''}
                    </div>
                </div>
            </div>
            <div class="space-y-3 sm:space-y-4 order-1 lg:order-2">
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-3 sm:p-4">
                    <h4 class="text-sm font-semibold text-white mb-3">Sentimiento Prensa</h4>
                    <canvas id="chart-press-sentiment" height="180"></canvas>
                </div>
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-3 sm:p-4">
                    <h4 class="text-sm font-semibold text-white mb-3">Fuentes</h4>
                    <canvas id="chart-press-sources" height="180"></canvas>
                </div>
            </div>
        </div>
    `;

    createDoughnutChart('chart-press-sentiment', sentDist);
    if (sourcesDist.length) {
        createBarChart('chart-press-sources', sourcesDist.map(s => s.source), sourcesDist.map(s => s.count), '#1d9bf0');
    }
}

// -- Social Tab --
function renderSocial(items, stats, sentByPlatform, topInfluencers) {
    const container = document.getElementById('tab-redes');
    const sentDist = buildSentimentDist(stats.social_sentiment);
    sentByPlatform = sentByPlatform || [];
    topInfluencers = topInfluencers || [];

    const platformColors = {
        prensa: '#4285f4', twitter: '#1d9bf0', reddit: '#ff4500', instagram: '#e1306c',
        youtube: '#ff0000', tiktok: '#00f2ea', telegram: '#26a5e4',
    };

    container.innerHTML = `
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
            <div class="lg:col-span-2 order-2 lg:order-1">
                <div class="bg-dark-700 rounded-xl border border-gray-800">
                    <div class="p-3 sm:p-4 border-b border-gray-800">
                        <div class="flex items-center justify-between mb-1">
                            <h3 class="font-semibold text-white text-sm sm:text-base">Menciones en Redes (${items.length})</h3>
                            <button onclick="exportCSV('social')" class="text-xs text-accent hover:underline touch-target">CSV</button>
                        </div>
                        <p class="text-[10px] sm:text-xs text-gray-500 mb-2">Lo que se dice del jugador en redes sociales y foros</p>
                        <input type="text" placeholder="Buscar en menciones..." class="w-full bg-dark-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:border-accent focus:outline-none mb-2" oninput="filterList(this.value, 'social')">
                        <div class="flex gap-1 flex-wrap">
                            <button onclick="filterPlatform(null)" class="platform-filter-btn active text-xs px-2 py-1.5 rounded-full border border-gray-700 text-gray-400 touch-target" data-platform="all">Todas</button>
                            ${['twitter','reddit','youtube','instagram','tiktok','telegram'].map(p => {
                                const count = items.filter(i => i.platform === p).length;
                                return count > 0 ? `<button onclick="filterPlatform('${p}')" class="platform-filter-btn text-xs px-2 py-1.5 rounded-full border border-gray-700 touch-target" data-platform="${p}" style="color:${platformColors[p] || '#71767b'}">${platformIcon(p)} ${count}</button>` : '';
                            }).join('')}
                        </div>
                    </div>
                    <div class="item-list max-h-[500px] sm:max-h-[600px] overflow-y-auto" id="social-list">
                        ${items.length === 0 ? '<div class="p-8 text-center text-gray-600">Sin menciones</div>' :
                        items.map(item => `
                            <div class="p-3 sm:p-4 card-hover search-item" data-search="${escapeHtml((item.author || '') + ' ' + (item.text || '') + ' ' + (item.platform || '')).toLowerCase()}">
                                <div class="flex items-start gap-2 sm:gap-3">
                                    <span class="text-base sm:text-lg platform-${item.platform} flex-shrink-0">${platformIcon(item.platform)}</span>
                                    <div class="flex-1 min-w-0">
                                        <div class="flex items-center gap-1 sm:gap-2 mb-1 flex-wrap">
                                            <span class="text-[10px] sm:text-xs font-medium text-gray-400">@${item.author || 'anon'}</span>
                                            <span class="text-[10px] sm:text-xs px-2 py-0.5 rounded-full badge-${item.sentiment_label || 'neutro'}">${item.sentiment_label || 'neutro'}</span>
                                        </div>
                                        <p class="text-xs sm:text-sm text-gray-300 line-clamp-3">${escapeHtml(item.text || '')}</p>
                                        <div class="flex items-center gap-2 sm:gap-4 mt-2 text-[10px] sm:text-xs text-gray-600 flex-wrap">
                                            <span>${fmtNum(item.likes)} ${item.platform === 'youtube' ? 'vistas' : 'me gusta'}</span>
                                            <span>${fmtNum(item.retweets)} ${item.platform === 'reddit' ? 'comentarios' : item.platform === 'youtube' ? '' : 'RT'}</span>
                                            <span>${formatDate(item.created_at)}</span>
                                            ${item.url ? `<a href="${item.url}" target="_blank" class="text-accent hover:underline">Ver</a>` : ''}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
            <div class="space-y-3 sm:space-y-4 order-1 lg:order-2">
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-3 sm:p-4">
                    <h4 class="text-sm font-semibold text-white mb-3">Sentimiento por Plataforma</h4>
                    <canvas id="chart-sent-platform" height="180"></canvas>
                </div>
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-3 sm:p-4">
                    <h4 class="text-sm font-semibold text-white mb-3">Sentimiento General</h4>
                    <canvas id="chart-social-sentiment" height="150"></canvas>
                </div>
                ${topInfluencers.length > 0 ? `
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-3 sm:p-4">
                    <h4 class="text-sm font-semibold text-white mb-3">Top Influencers</h4>
                    <div class="space-y-2">
                        ${topInfluencers.slice(0, 8).map((inf, i) => {
                            const sentColor = (inf.avg_sentiment || 0) > 0.2 ? '#00ba7c' : (inf.avg_sentiment || 0) < -0.2 ? '#f4212e' : '#ffd166';
                            return `
                            <div class="flex items-center justify-between py-1.5 ${i > 0 ? 'border-t border-gray-800/50' : ''}">
                                <div class="flex items-center gap-2 min-w-0">
                                    <span class="text-xs platform-${inf.platform}">${platformIcon(inf.platform)}</span>
                                    <span class="text-xs text-gray-300 truncate">@${escapeHtml(inf.author)}</span>
                                </div>
                                <div class="flex items-center gap-2 flex-shrink-0">
                                    <span class="text-[10px] text-gray-500">${inf.mentions}x</span>
                                    <span class="text-[10px]" style="color:${sentColor}">${(inf.avg_sentiment || 0).toFixed(2)}</span>
                                    <span class="text-[10px] text-gray-600">${fmtNum(inf.total_likes)} me gusta</span>
                                </div>
                            </div>`;
                        }).join('')}
                    </div>
                </div>` : ''}
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-3 sm:p-4">
                    <h4 class="text-sm font-semibold text-white mb-3">Por Plataforma</h4>
                    ${renderPlatformBreakdown(items)}
                </div>
            </div>
        </div>
    `;

    // Sentiment by platform bar chart
    if (sentByPlatform.length > 0) {
        const labels = sentByPlatform.map(s => s.platform);
        const values = sentByPlatform.map(s => s.avg_sentiment ? +s.avg_sentiment.toFixed(2) : 0);
        const colors = sentByPlatform.map(s => platformColors[s.platform] || '#71767b');
        const ctx = document.getElementById('chart-sent-platform');
        if (ctx) {
            if (charts['chart-sent-platform']) charts['chart-sent-platform'].destroy();
            charts['chart-sent-platform'] = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels,
                    datasets: [{
                        data: values,
                        backgroundColor: colors.map(c => c + '60'),
                        borderColor: colors,
                        borderWidth: 1,
                        borderRadius: 4,
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: '#71767b', font: { size: 10 } }, grid: { display: false } },
                        y: { min: -1, max: 1, ticks: { color: '#71767b' }, grid: { color: '#1a1a1a' } }
                    }
                }
            });
        }
    }

    createDoughnutChart('chart-social-sentiment', sentDist);
}

// -- Activity Tab --
function renderActivity(items, stats, activityPeaks) {
    const container = document.getElementById('tab-actividad');
    const topPosts = [...items].sort((a, b) => (b.likes || 0) - (a.likes || 0)).slice(0, 5);
    activityPeaks = activityPeaks || { hours: [], days: [] };

    container.innerHTML = `
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
            <div class="lg:col-span-2 order-2 lg:order-1">
                <div class="bg-dark-700 rounded-xl border border-gray-800">
                    <div class="p-3 sm:p-4 border-b border-gray-800">
                        <div class="flex items-center justify-between mb-1">
                            <h3 class="font-semibold text-white text-sm sm:text-base">Sus Redes (${items.length} posts)</h3>
                            <button onclick="exportCSV('activity')" class="text-xs text-accent hover:underline touch-target">CSV</button>
                        </div>
                        <p class="text-[10px] sm:text-xs text-gray-500 mb-2">Publicaciones propias del jugador en Twitter, Instagram y TikTok</p>
                        <input type="text" placeholder="Buscar en posts..." class="w-full bg-dark-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:border-accent focus:outline-none" oninput="filterList(this.value, 'activity')">
                    </div>
                    <div class="item-list max-h-[500px] sm:max-h-[600px] overflow-y-auto" id="activity-list">
                        ${items.length === 0 ? '<div class="p-8 text-center"><p class="text-gray-500 text-sm mb-2">Sin datos de actividad del jugador</p><p class="text-gray-600 text-xs">Configura los handles de Twitter, Instagram o TikTok para rastrear sus publicaciones.</p></div>' :
                        items.map(item => `
                            <div class="p-3 sm:p-4 card-hover search-item" data-search="${escapeHtml((item.text || '') + ' ' + (item.platform || '') + ' ' + (item.media_type || '')).toLowerCase()}">
                                <div class="flex items-start gap-2 sm:gap-3">
                                    <span class="text-base sm:text-lg platform-${item.platform} flex-shrink-0">${platformIcon(item.platform)}</span>
                                    <div class="flex-1 min-w-0">
                                        <div class="flex items-center gap-1 sm:gap-2 mb-1 flex-wrap">
                                            <span class="text-[10px] sm:text-xs px-2 py-0.5 rounded-full bg-dark-500 text-gray-400">${item.media_type || 'text'}</span>
                                            <span class="text-[10px] sm:text-xs px-2 py-0.5 rounded-full badge-${item.sentiment_label || 'neutro'}">${item.sentiment_label || 'neutro'}</span>
                                        </div>
                                        <p class="text-xs sm:text-sm text-gray-300 line-clamp-3">${escapeHtml(item.text || '')}</p>
                                        <div class="flex items-center gap-2 sm:gap-4 mt-2 text-[10px] sm:text-xs text-gray-600 flex-wrap">
                                            <span>${fmtNum(item.likes)} me gusta</span>
                                            <span>${fmtNum(item.comments)} comentarios</span>
                                            <span>${fmtNum(item.shares)} compartidos</span>
                                            ${item.views ? `<span>${fmtNum(item.views)} vistas</span>` : ''}
                                            ${item.engagement_rate ? `<span class="text-accent">${(item.engagement_rate * 100).toFixed(2)}% eng</span>` : ''}
                                            ${item.url ? `<a href="${item.url}" target="_blank" class="text-accent hover:underline">Ver</a>` : ''}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
            <div class="space-y-3 sm:space-y-4 order-1 lg:order-2">
                ${activityPeaks.hours?.length ? `
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-4">
                    <h4 class="text-sm font-semibold text-white mb-3">Horas de Publicacion</h4>
                    <canvas id="chart-peak-hours" height="120"></canvas>
                    ${activityPeaks.peak_hour !== null ? `<p class="text-[10px] text-gray-500 mt-2 text-center">Hora pico: <span class="text-accent font-bold">${activityPeaks.peak_hour}:00</span></p>` : ''}
                </div>
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-4">
                    <h4 class="text-sm font-semibold text-white mb-3">Dias de Publicacion</h4>
                    <canvas id="chart-peak-days" height="120"></canvas>
                    ${activityPeaks.peak_day ? `<p class="text-[10px] text-gray-500 mt-2 text-center">Dia pico: <span class="text-accent font-bold">${activityPeaks.peak_day}</span></p>` : ''}
                </div>` : ''}
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-4">
                    <h4 class="text-sm font-semibold text-white mb-3">Top Posts</h4>
                    <div class="space-y-3">
                        ${topPosts.map((p, i) => `
                            <div class="flex items-center gap-3">
                                <span class="text-lg font-bold text-gray-600">${i + 1}</span>
                                <div class="flex-1 min-w-0">
                                    <p class="text-xs text-gray-400 truncate">${escapeHtml((p.text || '').slice(0, 80))}</p>
                                    <span class="text-xs text-accent">${fmtNum(p.likes)} me gusta</span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-4">
                    <h4 class="text-sm font-semibold text-white mb-3">Tipo de Contenido</h4>
                    <canvas id="chart-content-type" height="200"></canvas>
                </div>
            </div>
        </div>
    `;

    // Peak hours chart
    if (activityPeaks.hours?.length) {
        const hourLabels = activityPeaks.hours.map(h => h.hour + 'h');
        const hourValues = activityPeaks.hours.map(h => h.count);
        const maxHour = Math.max(...hourValues);
        const hourColors = hourValues.map(v => v === maxHour && v > 0 ? '#1d9bf0' : '#1d9bf040');
        const hCtx = document.getElementById('chart-peak-hours');
        if (hCtx) {
            if (charts['chart-peak-hours']) charts['chart-peak-hours'].destroy();
            charts['chart-peak-hours'] = new Chart(hCtx, {
                type: 'bar',
                data: { labels: hourLabels, datasets: [{ data: hourValues, backgroundColor: hourColors, borderRadius: 2 }] },
                options: { responsive: true, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#71767b', font: { size: 8 } }, grid: { display: false } }, y: { ticks: { color: '#71767b', font: { size: 9 } }, grid: { color: '#1a1a1a' } } } }
            });
        }
    }

    // Peak days chart
    if (activityPeaks.days?.length) {
        const dayLabels = activityPeaks.days.map(d => d.day);
        const dayValues = activityPeaks.days.map(d => d.count);
        const maxDay = Math.max(...dayValues);
        const dayColors = dayValues.map(v => v === maxDay && v > 0 ? '#00ba7c' : '#00ba7c40');
        const dCtx = document.getElementById('chart-peak-days');
        if (dCtx) {
            if (charts['chart-peak-days']) charts['chart-peak-days'].destroy();
            charts['chart-peak-days'] = new Chart(dCtx, {
                type: 'bar',
                data: { labels: dayLabels, datasets: [{ data: dayValues, backgroundColor: dayColors, borderRadius: 4 }] },
                options: { responsive: true, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#71767b', font: { size: 10 } }, grid: { display: false } }, y: { ticks: { color: '#71767b' }, grid: { color: '#1a1a1a' } } } }
            });
        }
    }

    const typeCounts = {};
    items.forEach(i => { typeCounts[i.media_type || 'text'] = (typeCounts[i.media_type || 'text'] || 0) + 1; });
    if (Object.keys(typeCounts).length) {
        createDoughnutChart('chart-content-type', {
            labels: Object.keys(typeCounts),
            values: Object.values(typeCounts),
            colors: ['#1d9bf0', '#e1306c', '#ffd166', '#00ba7c', '#a855f7', '#00f2ea'],
        });
    }
}

// -- Alerts Tab --
function renderAlerts(items) {
    const container = document.getElementById('tab-alertas');

    // Apply filters
    let filtered = items;
    if (alertFilter.severity) {
        filtered = filtered.filter(a => a.severity === alertFilter.severity);
    }
    if (alertFilter.unread) {
        filtered = filtered.filter(a => !a.read);
    }

    const severities = ['alta', 'media', 'baja'];

    container.innerHTML = `
        <div class="bg-dark-700 rounded-xl border border-gray-800">
            <div class="p-3 sm:p-4 border-b border-gray-800">
                <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                    <h3 class="font-semibold text-white text-sm sm:text-base">Alertas (${filtered.length})</h3>
                    <div class="flex items-center gap-1 sm:gap-2 flex-wrap alerts-filter-bar">
                        <button onclick="toggleAlertFilter('unread')" class="filter-btn touch-target ${alertFilter.unread ? 'active' : ''}">No leidas</button>
                        ${severities.map(s => `
                            <button onclick="toggleAlertFilter('${s}')" class="filter-btn touch-target ${alertFilter.severity === s ? 'active' : ''}">${s}</button>
                        `).join('')}
                        ${alertFilter.severity || alertFilter.unread ? '<button onclick="clearAlertFilters()" class="filter-btn touch-target text-red-400">Limpiar</button>' : ''}
                    </div>
                </div>
            </div>
            <div class="item-list">
                ${filtered.length === 0 ? '<div class="p-8 text-center text-gray-600">Sin alertas - todo tranquilo</div>' :
                filtered.map(item => {
                    let sourcesHtml = '';
                    try {
                        const data = typeof item.data_json === 'string' ? JSON.parse(item.data_json) : item.data_json;
                        if (data) {
                            const titles = data.titles || data.samples || [];
                            const urls = data.urls || [];
                            const platformsList = data.platforms_list || [];
                            if (titles.length > 0) {
                                sourcesHtml = '<div class="mt-3 pt-3 border-t border-gray-800 space-y-1.5">' +
                                    '<div class="text-[10px] text-gray-600 uppercase tracking-wider mb-1">Fuentes</div>' +
                                    titles.slice(0, 5).map((t, idx) => {
                                        const url = urls[idx] || '';
                                        const src = platformsList[idx] || (data.sources && Array.isArray(data.sources) ? data.sources[0] : '') || '';
                                        const badge = src ? `<span class="text-[10px] px-1.5 py-0.5 rounded bg-dark-500 text-gray-500 mr-1.5 flex-shrink-0">${escapeHtml(src)}</span>` : '';
                                        if (url) {
                                            return `<div class="flex items-start gap-1">${badge}<a href="${escapeHtml(url)}" target="_blank" class="text-xs text-gray-400 hover:text-accent transition truncate">${escapeHtml(t)}</a></div>`;
                                        }
                                        return `<div class="flex items-start gap-1">${badge}<span class="text-xs text-gray-500 truncate">${escapeHtml(t)}</span></div>`;
                                    }).join('') +
                                    (titles.length > 5 ? `<div class="text-[10px] text-gray-600">... y ${titles.length - 5} mas</div>` : '') +
                                '</div>';
                            }
                        }
                    } catch(e) {}

                    return `
                    <div class="p-4 card-hover alert-${item.severity || 'baja'} ${item.read ? 'alert-read' : 'alert-unread'}" id="alert-${item.id}">
                        <div class="flex items-start gap-3">
                            <span class="text-xl flex-shrink-0">${item.severity === 'alta' ? '&#9888;' : item.severity === 'media' ? '&#9432;' : '&#8505;'}</span>
                            <div class="flex-1 min-w-0">
                                <div class="flex items-center gap-2 mb-2 flex-wrap">
                                    <span class="text-sm font-semibold text-white">${escapeHtml(item.title)}</span>
                                    <span class="text-xs px-2 py-0.5 rounded-full ${
                                        item.severity === 'alta' ? 'bg-red-500/20 text-red-400' :
                                        item.severity === 'media' ? 'bg-yellow-500/20 text-yellow-400' :
                                        'bg-blue-500/20 text-blue-400'
                                    }">${item.severity}</span>
                                    ${!item.read ? '<span class="w-2 h-2 rounded-full bg-accent"></span>' : ''}
                                </div>
                                <p class="text-xs text-gray-400 leading-relaxed">${escapeHtml(item.message)}</p>
                                ${sourcesHtml}
                                <div class="flex items-center gap-3 mt-2">
                                    <span class="text-[10px] text-gray-600">${formatDate(item.created_at)}</span>
                                    ${!item.read ? `<button onclick="markAlertRead(${item.id})" class="text-xs text-accent hover:underline touch-target">Marcar leida</button>` : ''}
                                    <button onclick="dismissAlert(${item.id})" class="text-xs text-red-400 hover:underline touch-target">Descartar</button>
                                </div>
                            </div>
                        </div>
                    </div>
                `}).join('')}
            </div>
        </div>
    `;
}

async function markAlertRead(alertId) {
    try {
        await fetch(`/api/alerts/${alertId}/read`, { method: 'PATCH' });
        const el = document.getElementById(`alert-${alertId}`);
        if (el) {
            el.classList.remove('alert-unread');
            el.classList.add('alert-read');
        }
        // Refresh alerts count
        const alerts = await fetch(`/api/alerts?player_id=${currentPlayerId}`).then(r => r.json());
        const unread = alerts.filter(a => !a.read).length;
        const badge = document.getElementById('alert-badge');
        if (unread > 0) { badge.textContent = unread; badge.classList.remove('hidden'); }
        else { badge.classList.add('hidden'); }
        renderAlerts(alerts);
    } catch (e) { console.error('Mark read error:', e); }
}

async function dismissAlert(alertId) {
    if (!confirm('Descartar esta alerta permanentemente?')) return;
    try {
        await fetch(`/api/alerts/${alertId}`, { method: 'DELETE' });
        const alerts = await fetch(`/api/alerts?player_id=${currentPlayerId}`).then(r => r.json());
        const unread = alerts.filter(a => !a.read).length;
        const badge = document.getElementById('alert-badge');
        if (unread > 0) { badge.textContent = unread; badge.classList.remove('hidden'); }
        else { badge.classList.add('hidden'); }
        renderAlerts(alerts);
    } catch (e) { console.error('Dismiss error:', e); }
}

function toggleAlertFilter(type) {
    if (type === 'unread') {
        alertFilter.unread = !alertFilter.unread;
    } else {
        alertFilter.severity = alertFilter.severity === type ? null : type;
    }
    // Re-render with current data
    fetch(`/api/alerts?player_id=${currentPlayerId}`).then(r => r.json()).then(renderAlerts);
}

function clearAlertFilters() {
    alertFilter = { severity: null, unread: false };
    fetch(`/api/alerts?player_id=${currentPlayerId}`).then(r => r.json()).then(renderAlerts);
}

// -- Historial Tab (Scan History) --
function renderHistorial(scans) {
    const container = document.getElementById('tab-historial');

    container.innerHTML = `
        <div class="bg-dark-700 rounded-xl border border-gray-800">
            <div class="p-3 sm:p-4 border-b border-gray-800 flex items-center justify-between">
                <h3 class="font-semibold text-white text-sm sm:text-base">Historial (${scans.length})</h3>
                <button id="compare-btn" onclick="runComparison()" class="text-sm bg-accent text-white px-3 py-1 rounded-lg touch-target" style="display:none">Comparar</button>
            </div>
            ${scans.length === 0 ? '<div class="p-8 text-center text-gray-600">Sin escaneos previos</div>' : `
            <div class="overflow-x-auto -mx-px">
                <table class="w-full text-xs sm:text-sm min-w-[500px]">
                    <thead>
                        <tr class="text-left text-[10px] sm:text-xs text-gray-500 uppercase tracking-wider border-b border-gray-800">
                            <th class="p-2 sm:p-3 w-8">Comp</th>
                            <th class="p-2 sm:p-3">Fecha</th>
                            <th class="p-2 sm:p-3">Estado</th>
                            <th class="p-2 sm:p-3 text-center">Prensa</th>
                            <th class="p-2 sm:p-3 text-center">Menciones</th>
                            <th class="p-2 sm:p-3 text-center">Posts</th>
                            <th class="p-2 sm:p-3 text-center">Alertas</th>
                            <th class="p-2 sm:p-3 hidden sm:table-cell">Duracion</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${scans.map(scan => {
                            const duration = scan.started_at && scan.finished_at
                                ? formatDuration(new Date(scan.finished_at) - new Date(scan.started_at))
                                : '-';
                            const statusColor = scan.status === 'completed' ? 'text-green-400' :
                                scan.status === 'running' ? 'text-accent' : 'text-red-400';
                            return `
                            <tr class="scan-history-row border-b border-gray-800/50">
                                <td class="p-2 sm:p-3"><input type="checkbox" class="compare-checkbox w-4 h-4" value="${scan.id}" onchange="toggleCompare(${scan.id})" ${compareSelection.includes(scan.id) ? 'checked' : ''}></td>
                                <td class="p-2 sm:p-3 text-gray-300">${formatDateTime(scan.started_at)}</td>
                                <td class="p-2 sm:p-3 ${statusColor}">${scan.status || '-'}</td>
                                <td class="p-2 sm:p-3 text-center text-white font-medium">${scan.press_count || 0}</td>
                                <td class="p-2 sm:p-3 text-center text-white font-medium">${scan.mentions_count || 0}</td>
                                <td class="p-2 sm:p-3 text-center text-white font-medium">${scan.posts_count || 0}</td>
                                <td class="p-2 sm:p-3 text-center text-white font-medium">${scan.alerts_count || 0}</td>
                                <td class="p-2 sm:p-3 text-gray-500 hidden sm:table-cell">${duration}</td>
                            </tr>`;
                        }).join('')}
                    </tbody>
                </table>
            </div>`}
        </div>
    `;
}

// -- Historico Tab (Charts) --
function renderHistorico(stats) {
    const container = document.getElementById('tab-historico');
    container.innerHTML = `
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-6">
            <div class="bg-dark-700 rounded-xl border border-gray-800 p-3 sm:p-4">
                <h4 class="text-xs sm:text-sm font-semibold text-white mb-3">Volumen Prensa</h4>
                <canvas id="chart-hist-press" height="180"></canvas>
            </div>
            <div class="bg-dark-700 rounded-xl border border-gray-800 p-3 sm:p-4">
                <h4 class="text-xs sm:text-sm font-semibold text-white mb-3">Volumen Menciones</h4>
                <canvas id="chart-hist-mentions" height="180"></canvas>
            </div>
            <div class="bg-dark-700 rounded-xl border border-gray-800 p-3 sm:p-4">
                <h4 class="text-xs sm:text-sm font-semibold text-white mb-3">Sent. Prensa</h4>
                <canvas id="chart-hist-press-sent" height="180"></canvas>
            </div>
            <div class="bg-dark-700 rounded-xl border border-gray-800 p-3 sm:p-4">
                <h4 class="text-xs sm:text-sm font-semibold text-white mb-3">Sent. Redes</h4>
                <canvas id="chart-hist-social-sent" height="180"></canvas>
            </div>
        </div>
    `;

    if (stats.press_daily?.length) {
        createLineChart('chart-hist-press', stats.press_daily.map(d => d.day), stats.press_daily.map(d => d.count), '#1d9bf0', 'Noticias');
    }
    if (stats.mentions_daily?.length) {
        createLineChart('chart-hist-mentions', stats.mentions_daily.map(d => d.day), stats.mentions_daily.map(d => d.count), '#e1306c', 'Menciones');
    }
    if (stats.press_daily?.length) {
        createLineChart('chart-hist-press-sent', stats.press_daily.map(d => d.day), stats.press_daily.map(d => d.avg_sentiment), '#00ba7c', 'Sentimiento', -1, 1);
    }
    if (stats.mentions_daily?.length) {
        createLineChart('chart-hist-social-sent', stats.mentions_daily.map(d => d.day), stats.mentions_daily.map(d => d.avg_sentiment), '#ffd166', 'Sentimiento', -1, 1);
    }
}

// -- Load More (pagination) --
async function loadMorePress() {
    pagination.press += PAGE_SIZE;
    const items = await fetch(`/api/press?player_id=${currentPlayerId}&limit=${PAGE_SIZE}&offset=${pagination.press}`).then(r => r.json());
    const list = document.getElementById('press-list');
    if (!list) return;
    // Remove previous "load more" button
    const oldBtn = list.querySelector('.text-center:last-child');
    if (oldBtn && oldBtn.querySelector('button')) oldBtn.remove();
    // Append new items
    const html = items.map(item => `
        <div class="p-4 card-hover">
            <div class="flex items-start justify-between gap-3">
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 mb-1">
                        <span class="text-xs px-2 py-0.5 rounded-full bg-dark-500 text-gray-400">${item.source || ''}</span>
                        <span class="text-xs px-2 py-0.5 rounded-full badge-${item.sentiment_label || 'neutro'}">${item.sentiment_label || 'neutro'}</span>
                    </div>
                    <a href="${item.url}" target="_blank" class="text-sm text-white hover:text-accent transition line-clamp-2">${item.title}</a>
                    <div class="text-xs text-gray-600 mt-1">${formatDate(item.published_at)}</div>
                </div>
            </div>
        </div>
    `).join('');
    list.insertAdjacentHTML('beforeend', html);
    if (items.length >= PAGE_SIZE) {
        list.insertAdjacentHTML('beforeend', '<div class="p-4 text-center"><button onclick="loadMorePress()" class="text-sm text-accent hover:underline">Cargar mas...</button></div>');
    }
}

// -- Scan Comparison --
let compareSelection = [];

function toggleCompare(scanLogId) {
    const idx = compareSelection.indexOf(scanLogId);
    if (idx >= 0) {
        compareSelection.splice(idx, 1);
    } else if (compareSelection.length < 2) {
        compareSelection.push(scanLogId);
    }
    // Update UI
    document.querySelectorAll('.compare-checkbox').forEach(cb => {
        cb.checked = compareSelection.includes(parseInt(cb.value));
    });
    const btn = document.getElementById('compare-btn');
    if (btn) btn.style.display = compareSelection.length === 2 ? 'inline-block' : 'none';
}

async function runComparison() {
    if (compareSelection.length !== 2) return;
    try {
        const resp = await fetch(`/api/compare?scan_id_a=${compareSelection[0]}&scan_id_b=${compareSelection[1]}`);
        const data = await resp.json();
        showComparisonModal(data.a, data.b);
    } catch (e) {
        console.error('Comparison error:', e);
    }
}

function showComparisonModal(a, b) {
    const existing = document.getElementById('compare-modal');
    if (existing) existing.remove();

    const sa = a.summary_snapshot || {};
    const sb = b.summary_snapshot || {};

    function cmpCell(key, label) {
        const va = sa[key] ?? '-';
        const vb = sb[key] ?? '-';
        const diff = (typeof va === 'number' && typeof vb === 'number') ? vb - va : null;
        const diffHtml = diff !== null ?
            `<span style="color:${diff > 0 ? '#00ba7c' : diff < 0 ? '#f4212e' : '#666'}">${diff > 0 ? '+' : ''}${typeof diff === 'number' && !Number.isInteger(diff) ? diff.toFixed(2) : diff}</span>` : '';
        return `<tr><td class="p-2 text-gray-500">${label}</td><td class="p-2 text-white text-center">${typeof va === 'number' && !Number.isInteger(va) ? va.toFixed(2) : va}</td><td class="p-2 text-white text-center">${typeof vb === 'number' && !Number.isInteger(vb) ? vb.toFixed(2) : vb}</td><td class="p-2 text-center">${diffHtml}</td></tr>`;
    }

    const modal = document.createElement('div');
    modal.id = 'compare-modal';
    modal.className = 'fixed inset-0 bg-black/60 z-50 flex items-end sm:items-center justify-center';
    modal.innerHTML = `
        <div class="bg-dark-700 rounded-t-2xl sm:rounded-2xl p-4 sm:p-6 border border-gray-800 w-full sm:max-w-lg sm:mx-4 max-h-[85vh] overflow-y-auto">
            <div class="flex items-center justify-between mb-4">
                <h3 class="text-lg font-bold text-white">Comparacion de Escaneos</h3>
                <button onclick="document.getElementById('compare-modal').remove()" class="text-gray-500 hover:text-white text-xl">&times;</button>
            </div>
            <table class="w-full text-sm">
                <thead><tr class="text-xs text-gray-500 uppercase"><th class="p-2 text-left">Metrica</th><th class="p-2 text-center">Scan A</th><th class="p-2 text-center">Scan B</th><th class="p-2 text-center">Diff</th></tr></thead>
                <tbody>
                    ${cmpCell('press_count', 'Noticias')}
                    ${cmpCell('mentions_count', 'Menciones')}
                    ${cmpCell('posts_count', 'Posts')}
                    ${cmpCell('alerts_count', 'Alertas')}
                    ${cmpCell('press_sentiment', 'Sent. Prensa')}
                    ${cmpCell('social_sentiment', 'Sent. Redes')}
                    ${cmpCell('avg_engagement', 'Engagement')}
                </tbody>
            </table>
        </div>
    `;
    document.body.appendChild(modal);
    compareSelection = [];
}

// -- Image Index --
function renderImageIndex(idx, history) {
    const card = document.getElementById('image-index-card');
    if (!idx || idx.index === undefined) { card.classList.add('hidden'); return; }
    card.classList.remove('hidden');

    const score = idx.index;
    const color = score >= 70 ? '#00ba7c' : score >= 40 ? '#ffd166' : '#f4212e';
    const label = score >= 70 ? 'POSITIVO' : score >= 40 ? 'NEUTRO' : 'NEGATIVO';

    const components = [
        { name: 'Volumen', value: idx.volume, weight: '20%', tooltip: 'Volumen de noticias y menciones. Mas cobertura = mejor score.' },
        { name: 'Sent. Prensa', value: idx.press_sentiment, weight: '25%', tooltip: 'Score de sentimiento en prensa. 100=todo positivo, 0=todo negativo.' },
        { name: 'Sent. Redes', value: idx.social_sentiment, weight: '25%', tooltip: 'Score de sentimiento en redes. 100=todo positivo, 0=todo negativo.' },
        { name: 'Engagement', value: idx.engagement, weight: '15%', tooltip: 'Interaccion del publico con los posts del jugador.' },
        { name: 'Sin Controversia', value: idx.no_controversy, weight: '15%', tooltip: 'Ausencia de polemica. 100=sin controversia, 0=mucha polemica.' },
    ];

    // Build sparkline SVG from history
    let sparkHtml = '';
    if (history && history.length > 1) {
        const vals = history.map(h => h.image_index);
        const min = Math.min(...vals) - 5;
        const max = Math.max(...vals) + 5;
        const range = max - min || 1;
        const w = 160, h = 40;
        const points = vals.map((v, i) => `${(i / (vals.length - 1)) * w},${h - ((v - min) / range) * h}`).join(' ');
        sparkHtml = `
            <div class="flex-shrink-0 ml-4" title="Tendencia del indice">
                <svg width="${w}" height="${h + 4}" class="overflow-visible">
                    <polyline points="${points}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>
                    <circle cx="${w}" cy="${h - ((vals[vals.length-1] - min) / range) * h}" r="3" fill="${color}"/>
                </svg>
                <div class="text-[9px] text-gray-600 text-center mt-1">${history.length} escaneos</div>
            </div>`;
    }

    card.innerHTML = `
        <div class="bg-dark-700 rounded-xl border border-gray-800 p-4 sm:p-5">
            <div class="flex flex-col sm:flex-row items-center gap-4 sm:gap-6">
                <div class="text-center flex-shrink-0">
                    <div class="relative w-20 h-20 sm:w-24 sm:h-24">
                        <svg viewBox="0 0 100 100" class="w-20 h-20 sm:w-24 sm:h-24 transform -rotate-90">
                            <circle cx="50" cy="50" r="42" fill="none" stroke="#222" stroke-width="8"/>
                            <circle cx="50" cy="50" r="42" fill="none" stroke="${color}" stroke-width="8"
                                stroke-dasharray="${score * 2.64} 264" stroke-linecap="round"/>
                        </svg>
                        <div class="absolute inset-0 flex items-center justify-center">
                            <span class="text-xl sm:text-2xl font-bold" style="color:${color}">${score}</span>
                        </div>
                    </div>
                    <div class="text-xs font-bold mt-1" style="color:${color}">${label}</div>
                    <div class="text-[10px] text-gray-600 uppercase tracking-wider">Indice de Imagen</div>
                </div>
                <div class="flex-1 grid grid-cols-3 sm:grid-cols-5 gap-2 sm:gap-3 image-index-components">
                    ${components.map(c => {
                        const cColor = c.value >= 70 ? '#00ba7c' : c.value >= 40 ? '#ffd166' : '#f4212e';
                        return `
                        <div class="text-center" data-tooltip="${c.tooltip}">
                            <div class="text-base sm:text-lg font-bold" style="color:${cColor}">${Math.round(c.value)}</div>
                            <div class="text-[10px] text-gray-500">${c.name}</div>
                            <div class="text-[9px] text-gray-700">${c.weight}</div>
                        </div>`;
                    }).join('')}
                </div>
                ${sparkHtml}
            </div>
        </div>
    `;
}

// -- Informe Tab (Weekly Reports) --
function renderInteligencia(intel) {
    const container = document.getElementById('tab-inteligencia');
    if (!intel || !intel.narrativas) {
        container.innerHTML = `
            <div class="bg-dark-700 rounded-xl border border-gray-800 p-6 text-center">
                <p class="text-gray-500 text-sm">No hay datos de inteligencia disponibles.</p>
                <p class="text-gray-600 text-xs mt-2">Lanza un escaneo para generar el analisis de inteligencia.</p>
            </div>`;
        return;
    }

    const rs = Math.round(intel.risk_score || 0);
    const riskColor = rs >= 70 ? '#f4212e' : rs >= 40 ? '#ffd166' : '#00ba7c';
    const riskLabel = rs >= 70 ? 'ALTO RIESGO' : rs >= 40 ? 'RIESGO MEDIO' : 'BAJO RIESGO';

    const sevOrder = { critico: 0, alto: 1, medio: 2, bajo: 3 };
    const sevColors = { critico: '#f4212e', alto: '#f97316', medio: '#ffd166', bajo: '#00ba7c' };
    const sevLabels = { critico: 'CRITICO', alto: 'ALTO', medio: 'MEDIO', bajo: 'BAJO' };
    const trendIcons = { escalando: '&#9650;', estable: '&#9654;', declinando: '&#9660;' };
    const trendClasses = { escalando: 'trend-escalando', estable: 'trend-estable', declinando: 'trend-declinando' };
    const catLabels = {
        reputacion_personal: 'Reputacion Personal', legal: 'Legal', rendimiento: 'Rendimiento',
        fichaje: 'Fichaje', lesion: 'Lesion', disciplina: 'Disciplina',
        comercial: 'Comercial', imagen_publica: 'Imagen Publica',
    };

    // Sort narrativas by severity
    const narrativas = (intel.narrativas || []).sort((a, b) => (sevOrder[a.severidad] ?? 9) - (sevOrder[b.severidad] ?? 9));
    const signals = intel.signals || [];

    // Build risk history sparkline
    let riskSparkHtml = '';
    if (intel.risk_history && intel.risk_history.length > 1) {
        const vals = intel.risk_history.map(h => h.risk_score);
        const mn = Math.min(...vals) - 5, mx = Math.max(...vals) + 5;
        const rng = mx - mn || 1;
        const sw = 140, sh = 36;
        const pts = vals.map((v, i) => `${(i / (vals.length - 1)) * sw},${sh - ((v - mn) / rng) * sh}`).join(' ');
        riskSparkHtml = `
            <div class="flex-shrink-0 w-full sm:w-auto" title="Tendencia de riesgo">
                <svg viewBox="0 0 ${sw + 6} ${sh + 6}" class="w-full sm:w-[140px] max-w-[200px] overflow-visible" preserveAspectRatio="xMidYMid meet">
                    <polyline points="${pts}" fill="none" stroke="${riskColor}" stroke-width="2" stroke-linejoin="round"/>
                    <circle cx="${sw}" cy="${sh - ((vals[vals.length-1] - mn) / rng) * sh}" r="3" fill="${riskColor}"/>
                </svg>
                <div class="text-[9px] text-gray-600 text-center mt-1">${intel.risk_history.length} escaneos</div>
            </div>`;
    }

    // Count by severity
    const sevCounts = { critico: 0, alto: 0, medio: 0, bajo: 0 };
    narrativas.forEach(n => { if (sevCounts[n.severidad] !== undefined) sevCounts[n.severidad]++; });

    container.innerHTML = `
        <div class="space-y-4">
            <!-- Risk Score Header -->
            <div class="bg-dark-700 rounded-xl border border-gray-800 p-4 sm:p-5">
                <div class="flex flex-col sm:flex-row items-center gap-4 sm:gap-6">
                    <div class="text-center flex-shrink-0">
                        <div class="relative w-20 h-20 sm:w-24 sm:h-24">
                            <svg viewBox="0 0 100 100" class="w-20 h-20 sm:w-24 sm:h-24 transform -rotate-90">
                                <circle cx="50" cy="50" r="42" fill="none" stroke="#222" stroke-width="8"/>
                                <circle cx="50" cy="50" r="42" fill="none" stroke="${riskColor}" stroke-width="8"
                                    stroke-dasharray="${rs * 2.64} 264" stroke-linecap="round"/>
                            </svg>
                            <div class="absolute inset-0 flex items-center justify-center">
                                <span class="text-xl sm:text-2xl font-bold" style="color:${riskColor}">${rs}</span>
                            </div>
                        </div>
                        <div class="text-xs font-bold mt-1" style="color:${riskColor}">${riskLabel}</div>
                        <div class="text-[10px] text-gray-600 uppercase tracking-wider">Riesgo Global</div>
                    </div>
                    <div class="flex-1 min-w-0">
                        <p class="text-sm text-gray-300 leading-relaxed mb-3">${escapeHtml(intel.resumen || '')}</p>
                        ${intel.recomendacion ? `
                            <div class="bg-accent/10 border border-accent/30 rounded-lg p-3">
                                <div class="text-[10px] text-accent uppercase tracking-wider font-semibold mb-1">Recomendacion Principal</div>
                                <p class="text-sm text-white">${escapeHtml(intel.recomendacion)}</p>
                            </div>` : ''}
                    </div>
                    ${riskSparkHtml}
                </div>
                <!-- Severity summary row -->
                <div class="flex gap-3 mt-4 pt-3 border-t border-gray-800 justify-center flex-wrap">
                    ${Object.entries(sevCounts).map(([sev, count]) => `
                        <div class="flex items-center gap-1.5">
                            <span class="w-2.5 h-2.5 rounded-full" style="background:${sevColors[sev]}"></span>
                            <span class="text-xs text-gray-400">${sevLabels[sev]}: <strong class="text-white">${count}</strong></span>
                        </div>
                    `).join('')}
                </div>
            </div>

            <!-- Stats & Trends Row -->
            ${intel.stats || intel.trends ? `
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                ${intel.stats ? (() => {
                    const cs = intel.stats.current_season || {};
                    const hasCurrent = (cs.appearances || 0) > 0;
                    return `
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-4">
                    <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Rendimiento Deportivo</h3>
                    ${hasCurrent ? `
                    <div class="text-[10px] text-accent uppercase tracking-wider mb-2 font-semibold">Temporada ${intel.stats.season || 'actual'}</div>
                    <div class="grid grid-cols-2 gap-2 text-center mb-3">
                        <div><div class="text-lg font-bold text-white">${cs.appearances || 0}</div><div class="text-[10px] text-gray-500">Partidos</div></div>
                        <div><div class="text-lg font-bold text-green-400">${cs.goals || 0}</div><div class="text-[10px] text-gray-500">Goles</div></div>
                    </div>
                    <div class="text-[10px] text-gray-600 uppercase tracking-wider mb-2 pt-2 border-t border-gray-800">Carrera</div>` : ''}
                    <div class="grid grid-cols-3 gap-2 text-center">
                        <div><div class="text-base font-bold text-white">${intel.stats.appearances || 0}</div><div class="text-[10px] text-gray-500">Partidos</div></div>
                        <div><div class="text-base font-bold text-green-400">${intel.stats.goals || 0}</div><div class="text-[10px] text-gray-500">Goles</div></div>
                        <div><div class="text-base font-bold text-blue-400">${intel.stats.assists || 0}</div><div class="text-[10px] text-gray-500">Asist.</div></div>
                        <div><div class="text-base font-bold text-gray-300">${intel.stats.minutes ? (intel.stats.minutes).toLocaleString() : 0}'</div><div class="text-[10px] text-gray-500">Minutos</div></div>
                        <div><div class="text-base font-bold text-yellow-400">${intel.stats.yellows || 0}</div><div class="text-[10px] text-gray-500">Amarillas</div></div>
                        <div><div class="text-base font-bold text-red-400">${intel.stats.reds || 0}</div><div class="text-[10px] text-gray-500">Rojas</div></div>
                    </div>
                    ${intel.stats.competitions && intel.stats.competitions.length > 0 ? `
                    <div class="mt-3 pt-3 border-t border-gray-800 max-h-32 overflow-y-auto">
                        ${intel.stats.competitions.slice(0, 8).map(c => `
                            <div class="flex justify-between text-xs text-gray-400 mb-1">
                                <span>${escapeHtml(c.name)}</span>
                                <span class="text-white">${c.appearances} pj, ${c.goals} g</span>
                            </div>
                        `).join('')}
                    </div>` : ''}
                </div>`;
                })() : ''}
                ${intel.trends ? `
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-4">
                    <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Google Trends (30 dias)</h3>
                    <div class="grid grid-cols-3 gap-3 text-center mb-3">
                        <div>
                            <div class="text-lg font-bold text-white">${intel.trends.average_interest || 0}</div>
                            <div class="text-[10px] text-gray-500 uppercase">Interes Medio</div>
                        </div>
                        <div>
                            <div class="text-lg font-bold text-accent">${intel.trends.peak_interest || 0}</div>
                            <div class="text-[10px] text-gray-500 uppercase">Pico</div>
                        </div>
                        <div>
                            <div class="text-lg font-bold ${intel.trends.trend_direction === 'up' ? 'text-red-400' : intel.trends.trend_direction === 'down' ? 'text-green-400' : 'text-yellow-400'}">
                                ${intel.trends.trend_direction === 'up' ? '&#9650; Subiendo' : intel.trends.trend_direction === 'down' ? '&#9660; Bajando' : '&#9654; Estable'}
                            </div>
                            <div class="text-[10px] text-gray-500 uppercase">Tendencia</div>
                        </div>
                    </div>
                    ${intel.trends.timeline && intel.trends.timeline.length > 2 ? (() => {
                        const vals = intel.trends.timeline.map(t => t.value);
                        const mn = Math.min(...vals), mx = Math.max(...vals);
                        const rng = (mx - mn) || 1;
                        const sw = 200, sh = 50;
                        const pts = vals.map((v, i) => (i / (vals.length - 1)) * sw + ',' + (sh - ((v - mn) / rng) * sh)).join(' ');
                        const trendCol = intel.trends.trend_direction === 'up' ? '#f4212e' : intel.trends.trend_direction === 'down' ? '#00ba7c' : '#ffd166';
                        return '<div class="flex justify-center"><svg viewBox="0 0 ' + (sw+6) + ' ' + (sh+6) + '" class="w-full max-w-[280px] overflow-visible" preserveAspectRatio="xMidYMid meet"><polyline points="' + pts + '" fill="none" stroke="' + trendCol + '" stroke-width="2" stroke-linejoin="round"/><circle cx="' + sw + '" cy="' + (sh - ((vals[vals.length-1] - mn) / rng) * sh) + '" r="3" fill="' + trendCol + '"/></svg></div>';
                    })() : ''}
                    <div class="text-[10px] text-gray-600 text-center mt-1">${intel.trends.data_points || 0} puntos de datos</div>
                </div>` : ''}
            </div>` : ''}

            <!-- Narrativas -->
            ${narrativas.length > 0 ? `
            <div>
                <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Narrativas Detectadas (${narrativas.length})</h3>
                <div class="space-y-3">
                    ${narrativas.map(n => {
                        const sc = sevColors[n.severidad] || '#71767b';
                        const sl = sevLabels[n.severidad] || 'N/A';
                        const tc = trendClasses[n.tendencia] || '';
                        const ti = trendIcons[n.tendencia] || '';
                        const cat = catLabels[n.categoria] || n.categoria;
                        const fuentes = (n.fuentes || []).join(', ');
                        return `
                        <div class="severity-${n.severidad} bg-dark-700 rounded-xl border border-gray-800 p-4 fade-in">
                            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                                <div class="flex items-center gap-2 flex-wrap">
                                    <span class="severity-label sev-${n.severidad}">${sl}</span>
                                    <span class="cat-badge cat-${n.categoria}">${escapeHtml(cat)}</span>
                                    ${n.tendencia ? `<span class="${tc} text-xs font-semibold">${ti} ${n.tendencia}</span>` : ''}
                                </div>
                                <div class="flex items-center gap-2 text-xs text-gray-500">
                                    <span>${n.num_items || 0} items</span>
                                    ${fuentes ? `<span>| ${escapeHtml(fuentes)}</span>` : ''}
                                </div>
                            </div>
                            <h4 class="text-sm font-semibold text-white mb-1">${escapeHtml(n.titulo || '')}</h4>
                            <p class="text-xs text-gray-400 leading-relaxed">${escapeHtml(n.descripcion || '')}</p>
                            ${n.recomendacion ? `
                                <div class="mt-2 pt-2 border-t border-gray-800">
                                    <span class="text-[10px] text-accent uppercase tracking-wider font-semibold">Rec:</span>
                                    <span class="text-xs text-gray-300 ml-1">${escapeHtml(n.recomendacion)}</span>
                                </div>` : ''}
                        </div>`;
                    }).join('')}
                </div>
            </div>` : ''}

            <!-- Senales Tempranas -->
            ${signals.length > 0 ? `
            <div>
                <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Senales Tempranas (${signals.length})</h3>
                <div class="space-y-2">
                    ${signals.map(s => {
                        const cat = catLabels[s.categoria] || s.categoria || '';
                        return `
                        <div class="bg-dark-700 rounded-xl border border-gray-800 p-3 flex flex-col sm:flex-row sm:items-start gap-2">
                            <div class="flex items-center gap-2 flex-shrink-0">
                                <span class="text-yellow-400 text-lg">&#9888;</span>
                                ${cat ? `<span class="cat-badge cat-${s.categoria}">${escapeHtml(cat)}</span>` : ''}
                                ${s.probabilidad ? `<span class="text-[10px] text-gray-500">${s.probabilidad}%</span>` : ''}
                            </div>
                            <div class="flex-1 min-w-0">
                                <p class="text-sm text-gray-300">${escapeHtml(s.descripcion || '')}</p>
                                ${s.evidencia ? `<p class="text-xs text-gray-500 mt-1">Evidencia: ${escapeHtml(s.evidencia)}</p>` : ''}
                                ${s.accion_sugerida ? `<p class="text-xs text-accent mt-1">Accion: ${escapeHtml(s.accion_sugerida)}</p>` : ''}
                            </div>
                        </div>`;
                    }).join('')}
                </div>
            </div>` : ''}

            <!-- Report metadata -->
            ${intel.created_at ? `
            <div class="text-right text-[10px] text-gray-600 mt-2">
                Analisis generado: ${formatDateTime(intel.created_at)} | Tokens: ${intel.tokens_used || '?'}
            </div>` : ''}
        </div>
    `;
}

function renderInforme(weeklyReports, imageIndex) {
    const container = document.getElementById('tab-informe');

    const recColors = {
        'COMPRAR': '#00ba7c', 'RENOVAR': '#1d9bf0', 'MONITORIZAR': '#ffd166',
        'PRECAUCION': '#f97316', 'VENDER': '#f4212e',
    };

    container.innerHTML = `
        <div class="space-y-3 sm:space-y-4">
            <div class="bg-dark-700 rounded-xl border border-gray-800 p-4 sm:p-5">
                <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
                    <h3 class="font-semibold text-white text-sm sm:text-base">Informe Semanal</h3>
                    <div class="flex gap-2">
                        ${weeklyReports.length > 0 ? `<button onclick="window.open('/api/player/${currentPlayerId}/weekly-report-pdf','_blank')" class="bg-dark-600 hover:bg-dark-500 text-gray-300 px-3 py-2 rounded-lg text-xs sm:text-sm border border-gray-700 touch-target">PDF</button>` : ''}
                        <button onclick="generateWeeklyReport()" id="btn-gen-report" class="bg-accent hover:bg-blue-600 text-white px-3 sm:px-4 py-2 rounded-lg text-xs sm:text-sm font-medium transition touch-target flex-1 sm:flex-none">
                            Generar Informe
                        </button>
                    </div>
                </div>
                ${weeklyReports.length === 0 ? '<p class="text-gray-600 text-sm">Aun no hay informes generados. Pulsa "Generar Informe" para crear uno.</p>' : ''}
            </div>
            ${weeklyReports.map(r => {
                const rec = r.recommendation || 'MONITORIZAR';
                const color = recColors[rec] || '#ffd166';
                const data = r.data || {};
                return `
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-5 fade-in">
                    <div class="flex items-center justify-between mb-3">
                        <div class="flex items-center gap-3">
                            <span class="px-3 py-1 rounded-lg text-sm font-bold" style="background:${color}20;color:${color};border:1px solid ${color}40">${rec}</span>
                            <span class="text-xs text-gray-500">${formatDateTime(r.created_at)}</span>
                        </div>
                        <div class="text-sm font-bold" style="color:${r.image_index >= 70 ? '#00ba7c' : r.image_index >= 40 ? '#ffd166' : '#f4212e'}">
                            Indice: ${r.image_index?.toFixed(1) || '-'}/100
                        </div>
                    </div>
                    <p class="text-sm text-gray-300 mb-3">${escapeHtml(r.report_text || '')}</p>
                    ${data.justification ? `<p class="text-sm text-gray-400 italic mb-3">${escapeHtml(data.justification)}</p>` : ''}
                    ${data.risks?.length ? `
                        <div class="mb-2">
                            <span class="text-xs text-red-400 font-semibold uppercase">Riesgos:</span>
                            <ul class="list-disc list-inside text-sm text-gray-400 mt-1">
                                ${data.risks.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
                            </ul>
                        </div>
                    ` : ''}
                    ${data.opportunities?.length ? `
                        <div>
                            <span class="text-xs text-green-400 font-semibold uppercase">Oportunidades:</span>
                            <ul class="list-disc list-inside text-sm text-gray-400 mt-1">
                                ${data.opportunities.map(o => `<li>${escapeHtml(o)}</li>`).join('')}
                            </ul>
                        </div>
                    ` : ''}
                </div>`;
            }).join('')}
        </div>
    `;
}

async function generateWeeklyReport() {
    if (!currentPlayerId) return;
    const btn = document.getElementById('btn-gen-report');
    btn.disabled = true;
    btn.textContent = 'Generando...';
    try {
        const resp = await fetch(`/api/player/${currentPlayerId}/weekly-report`, { method: 'POST' });
        if (!resp.ok) throw new Error(await resp.text());
        // Reload weekly reports
        const reports = await fetch(`/api/player/${currentPlayerId}/weekly-reports?limit=5`).then(r => r.json());
        const idx = await fetch(`/api/player/${currentPlayerId}/image-index`).then(r => r.json()).catch(() => null);
        renderInforme(reports, idx);
    } catch (e) {
        alert('Error generando informe: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Generar Informe';
    }
}

// -- Portfolio View --
async function showPortfolio() {
    document.getElementById('dashboard').classList.add('hidden');
    document.getElementById('portfolio-view').classList.remove('hidden');
    const mobileNav = document.getElementById('mobile-nav');
    if (mobileNav) mobileNav.style.display = 'none';

    const grid = document.getElementById('portfolio-grid');
    grid.innerHTML = '<div class="col-span-3 text-center text-gray-500 py-8">Cargando portfolio...</div>';

    try {
        const [data, sparkData, intelData] = await Promise.all([
            fetch('/api/portfolio').then(r => r.json()),
            fetch('/api/portfolio/sparklines').then(r => r.json()).catch(() => ({})),
            fetch('/api/portfolio/intelligence').then(r => r.json()).catch(() => []),
        ]);
        if (!data.length) {
            grid.innerHTML = '<div class="col-span-3 text-center text-gray-500 py-8">Sin jugadores registrados</div>';
            return;
        }

        // Build intel lookup by player_id
        const intelMap = {};
        (intelData || []).forEach(i => { intelMap[i.player_id] = i; });

        grid.innerHTML = data.map(p => {
            // Build mini sparkline SVG from sparkData
            const pSparks = sparkData[p.id] || [];
            let sparkSvg = '';
            if (pSparks.length > 1) {
                const vals = pSparks.map(s => s.image_index ?? 50);
                const mn = Math.min(...vals) - 5, mx = Math.max(...vals) + 5;
                const rng = mx - mn || 1;
                const sw = 80, sh = 24;
                const pts = vals.map((v, i) => `${(i / (vals.length - 1)) * sw},${sh - ((v - mn) / rng) * sh}`).join(' ');
                const lastColor = vals[vals.length - 1] >= 70 ? '#00ba7c' : vals[vals.length - 1] >= 40 ? '#ffd166' : '#f4212e';
                sparkSvg = `<svg width="${sw}" height="${sh + 2}" class="overflow-visible"><polyline points="${pts}" fill="none" stroke="${lastColor}" stroke-width="1.5" stroke-linejoin="round"/><circle cx="${sw}" cy="${sh - ((vals[vals.length-1] - mn) / rng) * sh}" r="2" fill="${lastColor}"/></svg>`;
            }
            const idx = p.image_index || 0;
            const color = idx >= 70 ? '#00ba7c' : idx >= 40 ? '#ffd166' : '#f4212e';
            const label = idx >= 70 ? 'BIEN' : idx >= 40 ? 'NEUTRO' : 'RIESGO';
            const s = p.summary || {};

            // Intelligence risk badge
            const pi = intelMap[p.id];
            let riskBadgeHtml = '';
            if (pi && pi.risk_score !== undefined) {
                const rrs = Math.round(pi.risk_score);
                const rc = rrs >= 70 ? '#f4212e' : rrs >= 40 ? '#ffd166' : '#00ba7c';
                const hrc = pi.high_risk_count || 0;
                riskBadgeHtml = `
                    <div class="flex items-center gap-1.5 mt-1">
                        <span class="w-2 h-2 rounded-full" style="background:${rc}"></span>
                        <span class="text-[10px] font-semibold" style="color:${rc}">Riesgo: ${rrs}</span>
                        ${hrc > 0 ? `<span class="text-[10px] px-1.5 py-0.5 rounded-full bg-red-500/20 text-red-400 font-bold">${hrc} criticas</span>` : ''}
                    </div>`;
            }

            const initials = (p.name || '').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
            const photoHtml = p.photo_url
                ? `<img src="${p.photo_url}" class="w-12 h-12 rounded-full object-cover border-2" style="border-color:${color}">`
                : `<div class="w-12 h-12 rounded-full flex items-center justify-center font-bold text-white text-sm" style="background:${color}30;border:2px solid ${color};color:${color}">${initials}</div>`;

            const lastScanAgo = p.last_scan?.finished_at ? timeAgo(p.last_scan.finished_at) : 'nunca';

            return `
                <div class="bg-dark-700 rounded-xl border border-gray-800 p-3 sm:p-4 cursor-pointer hover:border-gray-600 transition card-hover" onclick="hidePortfolio(); loadDashboard(${p.id})">
                    <div class="flex items-center gap-3 mb-3">
                        ${photoHtml}
                        <div class="flex-1 min-w-0">
                            <div class="font-semibold text-white truncate text-sm sm:text-base">${p.name}</div>
                            <div class="text-[10px] sm:text-xs text-gray-500">${p.club || ''} ${p.market_value ? '| ' + p.market_value : ''}</div>
                            ${riskBadgeHtml}
                        </div>
                        <div class="text-center flex-shrink-0">
                            <div class="relative w-12 h-12 sm:w-14 sm:h-14">
                                <svg viewBox="0 0 100 100" class="w-12 h-12 sm:w-14 sm:h-14 transform -rotate-90">
                                    <circle cx="50" cy="50" r="42" fill="none" stroke="#222" stroke-width="8"/>
                                    <circle cx="50" cy="50" r="42" fill="none" stroke="${color}" stroke-width="8"
                                        stroke-dasharray="${idx * 2.64} 264" stroke-linecap="round"/>
                                </svg>
                                <div class="absolute inset-0 flex items-center justify-center">
                                    <span class="text-xs sm:text-sm font-bold" style="color:${color}">${Math.round(idx)}</span>
                                </div>
                            </div>
                            <div class="text-[9px] font-bold" style="color:${color}">${label}</div>
                        </div>
                    </div>
                    <div class="grid grid-cols-4 gap-1 sm:gap-2 text-center portfolio-metrics">
                        <div>
                            <div class="text-xs sm:text-sm font-bold text-white">${s.press_count || 0}</div>
                            <div class="text-[9px] sm:text-[10px] text-gray-600">Prensa</div>
                        </div>
                        <div>
                            <div class="text-xs sm:text-sm font-bold text-white">${s.mentions_count || 0}</div>
                            <div class="text-[9px] sm:text-[10px] text-gray-600">Menciones</div>
                        </div>
                        <div>
                            <div class="text-xs sm:text-sm font-bold text-white">${s.posts_count || 0}</div>
                            <div class="text-[9px] sm:text-[10px] text-gray-600">Posts</div>
                        </div>
                        <div>
                            <div class="text-xs sm:text-sm font-bold ${s.alerts_count > 0 ? 'text-red-400' : 'text-white'}">${s.alerts_count || 0}</div>
                            <div class="text-[9px] sm:text-[10px] text-gray-600">Alertas</div>
                        </div>
                    </div>
                    ${sparkSvg ? `<div class="mt-2 flex justify-center">${sparkSvg}</div>` : ''}
                    <div class="flex items-center justify-between mt-3 pt-2 border-t border-gray-800">
                        <span class="text-[10px] text-gray-600">Sent. Prensa: <span style="color:${sentimentColor2(s.press_sentiment)}">${s.press_sentiment?.toFixed(2) || '-'}</span></span>
                        <span class="text-[10px] text-gray-600">Sent. Redes: <span style="color:${sentimentColor2(s.social_sentiment)}">${s.social_sentiment?.toFixed(2) || '-'}</span></span>
                        <span class="text-[10px] text-gray-600">Ultimo: ${lastScanAgo}</span>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        grid.innerHTML = `<div class="col-span-3 text-center text-red-400 py-8">Error: ${e.message}</div>`;
    }
}

function hidePortfolio() {
    document.getElementById('portfolio-view').classList.add('hidden');
    document.getElementById('dashboard').classList.remove('hidden');
    const mobileNav = document.getElementById('mobile-nav');
    if (mobileNav) mobileNav.style.display = '';
}

function sentimentColor2(val) {
    if (val === null || val === undefined) return '#71767b';
    if (val > 0.2) return '#00ba7c';
    if (val < -0.2) return '#f4212e';
    return '#ffd166';
}

// -- Cross-Player Comparison --
async function showPlayerCompareModal() {
    const modal = document.getElementById('player-compare-modal');
    modal.classList.remove('hidden');
    const content = document.getElementById('player-compare-content');
    content.innerHTML = '<p class="text-gray-500">Cargando jugadores...</p>';

    const players = await fetch('/api/players').then(r => r.json());
    if (players.length < 2) {
        content.innerHTML = '<p class="text-gray-500">Necesitas al menos 2 jugadores para comparar.</p>';
        return;
    }

    content.innerHTML = `
        <p class="text-sm text-gray-400 mb-3">Selecciona 2 o mas jugadores para comparar:</p>
        <div class="space-y-2 mb-4">
            ${players.map(p => `
                <label class="flex items-center gap-3 p-2 rounded-lg hover:bg-dark-600 cursor-pointer">
                    <input type="checkbox" class="player-compare-cb" value="${p.id}">
                    <span class="text-sm text-white">${p.name}</span>
                    <span class="text-xs text-gray-500">${p.club || ''}</span>
                </label>
            `).join('')}
        </div>
        <button onclick="runPlayerComparison()" class="bg-accent hover:bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium">Comparar</button>
    `;
}

function hidePlayerCompareModal() {
    document.getElementById('player-compare-modal').classList.add('hidden');
}

async function runPlayerComparison() {
    const checkboxes = document.querySelectorAll('.player-compare-cb:checked');
    const ids = Array.from(checkboxes).map(cb => cb.value);
    if (ids.length < 2) return alert('Selecciona al menos 2 jugadores');

    const content = document.getElementById('player-compare-content');
    content.innerHTML = '<p class="text-gray-500">Comparando...</p>';

    try {
        const data = await fetch(`/api/compare-players?player_ids=${ids.join(',')}`).then(r => r.json());

        const metrics = [
            { key: 'press_count', label: 'Noticias' },
            { key: 'mentions_count', label: 'Menciones' },
            { key: 'posts_count', label: 'Posts' },
            { key: 'press_sentiment', label: 'Sent. Prensa', fmt: v => v?.toFixed(2) || '-' },
            { key: 'social_sentiment', label: 'Sent. Redes', fmt: v => v?.toFixed(2) || '-' },
            { key: 'avg_engagement', label: 'Engagement', fmt: v => v ? (v * 100).toFixed(2) + '%' : '-' },
            { key: 'alerts_count', label: 'Alertas' },
        ];

        // Build radar data from image_index components
        const radarLabels = ['Volumen', 'Sent. Prensa', 'Sent. Redes', 'Engagement', 'Sin Controversia'];
        const radarColors = ['#1d9bf0', '#00ba7c', '#f4212e', '#ffd166', '#a855f7', '#e1306c'];
        const radarDatasets = data.map((d, i) => {
            const idx = d.image_index || {};
            return {
                label: d.player.name,
                data: [idx.volume || 0, idx.press_sentiment || 0, idx.social_sentiment || 0, idx.engagement || 0, idx.no_controversy || 0],
                borderColor: radarColors[i % radarColors.length],
                backgroundColor: radarColors[i % radarColors.length] + '20',
                borderWidth: 2,
                pointRadius: 4,
                pointBackgroundColor: radarColors[i % radarColors.length],
            };
        });

        content.innerHTML = `
            <div class="mb-6">
                <canvas id="chart-compare-radar" height="250"></canvas>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-sm">
                    <thead>
                        <tr class="text-xs text-gray-500 uppercase border-b border-gray-800">
                            <th class="p-3 text-left">Metrica</th>
                            ${data.map(d => `<th class="p-3 text-center">${d.player.name}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        <tr class="border-b border-gray-800">
                            <td class="p-3 text-gray-400 font-semibold">Indice de Imagen</td>
                            ${data.map(d => {
                                const idx = d.image_index?.index || 0;
                                const c = idx >= 70 ? '#00ba7c' : idx >= 40 ? '#ffd166' : '#f4212e';
                                return `<td class="p-3 text-center"><span class="text-lg font-bold" style="color:${c}">${Math.round(idx)}</span><span class="text-xs text-gray-600">/100</span></td>`;
                            }).join('')}
                        </tr>
                        ${metrics.map(m => `
                            <tr class="border-b border-gray-800/50">
                                <td class="p-3 text-gray-500">${m.label}</td>
                                ${data.map(d => {
                                    const val = d.summary?.[m.key];
                                    const display = m.fmt ? m.fmt(val) : (val ?? '-');
                                    return `<td class="p-3 text-center text-white font-medium">${display}</td>`;
                                }).join('')}
                            </tr>
                        `).join('')}
                        <tr class="border-b border-gray-800">
                            <td class="p-3 text-gray-400 font-semibold">Temas Top</td>
                            ${data.map(d => {
                                const topics = Object.entries(d.topics || {}).slice(0, 3);
                                return `<td class="p-3 text-center text-xs">${topics.map(([t, c]) => `<span class="inline-block bg-dark-500 text-gray-300 px-2 py-0.5 rounded-full m-0.5">${t} (${c})</span>`).join('') || '-'}</td>`;
                            }).join('')}
                        </tr>
                    </tbody>
                </table>
            </div>
        `;

        // Render radar chart
        const radarCtx = document.getElementById('chart-compare-radar');
        if (radarCtx) {
            if (charts['chart-compare-radar']) charts['chart-compare-radar'].destroy();
            charts['chart-compare-radar'] = new Chart(radarCtx, {
                type: 'radar',
                data: { labels: radarLabels, datasets: radarDatasets },
                options: {
                    responsive: true,
                    scales: {
                        r: {
                            beginAtZero: true, max: 100,
                            ticks: { color: '#71767b', backdropColor: 'transparent', font: { size: 9 } },
                            grid: { color: '#1a1a1a' },
                            pointLabels: { color: '#e7e9ea', font: { size: 11 } },
                            angleLines: { color: '#1a1a1a' },
                        }
                    },
                    plugins: {
                        legend: { position: 'bottom', labels: { color: '#e7e9ea', boxWidth: 12, padding: 16 } }
                    }
                }
            });
        }
    } catch (e) {
        content.innerHTML = `<p class="text-red-400">Error: ${e.message}</p>`;
    }
}

// -- Date Range --
function setDateRange(preset) {
    const now = new Date();
    dateRange.preset = preset;

    // Update button states
    document.querySelectorAll('.date-range-btn').forEach(b => b.classList.remove('active'));
    const activeBtn = document.querySelector(`[data-range="${preset}"]`);
    if (activeBtn) activeBtn.classList.add('active');

    if (preset === 'all') {
        dateRange.from = null;
        dateRange.to = null;
        document.getElementById('date-from').value = '';
        document.getElementById('date-to').value = '';
    } else if (preset === 'custom') {
        const fromVal = document.getElementById('date-from').value;
        const toVal = document.getElementById('date-to').value;
        dateRange.from = fromVal ? fromVal + 'T00:00:00' : null;
        dateRange.to = toVal ? toVal + 'T23:59:59' : null;
        // Remove active from preset buttons
        document.querySelectorAll('.date-range-btn').forEach(b => b.classList.remove('active'));
    } else {
        const days = parseInt(preset);
        const fromDate = new Date(now);
        fromDate.setDate(fromDate.getDate() - days);
        dateRange.from = fromDate.toISOString().split('T')[0] + 'T00:00:00';
        dateRange.to = null;
        document.getElementById('date-from').value = fromDate.toISOString().split('T')[0];
        document.getElementById('date-to').value = now.toISOString().split('T')[0];
    }

    if (currentPlayerId) reloadDashboardData(currentPlayerId);
}

function buildDateParams() {
    let params = '';
    if (dateRange.from) params += `&date_from=${encodeURIComponent(dateRange.from)}`;
    if (dateRange.to) params += `&date_to=${encodeURIComponent(dateRange.to)}`;
    return params;
}

async function reloadDashboardData(playerId) {
    const dp = buildDateParams();
    pagination = { press: 0, social: 0, activity: 0 };

    const [summary, report, press, social, activity, alerts, stats, sentByPlatform, topInfluencers, activityPeaks] = await Promise.all([
        fetch(`/api/summary?player_id=${playerId}${dp}`).then(r => r.json()),
        fetch(`/api/report?player_id=${playerId}`).then(r => r.json()).catch(() => null),
        fetch(`/api/press?player_id=${playerId}${dp}`).then(r => r.json()),
        fetch(`/api/social?player_id=${playerId}${dp}`).then(r => r.json()),
        fetch(`/api/activity?player_id=${playerId}${dp}`).then(r => r.json()),
        fetch(`/api/alerts?player_id=${playerId}`).then(r => r.json()),
        fetch(`/api/stats?player_id=${playerId}${dp}`).then(r => r.json()),
        fetch(`/api/player/${playerId}/sentiment-by-platform`).then(r => r.json()).catch(() => []),
        fetch(`/api/player/${playerId}/top-influencers`).then(r => r.json()).catch(() => []),
        fetch(`/api/player/${playerId}/activity-peaks`).then(r => r.json()).catch(() => null),
    ]);

    window._currentData = { press, social, activity, alerts };
    renderSummaryCards(summary, report?.delta);
    renderTopicsAndBrands(report);
    renderPress(press, stats);
    renderSocial(social, stats, sentByPlatform, topInfluencers);
    renderActivity(activity, stats, activityPeaks);
    renderAlerts(alerts);
    renderHistorico(stats);
}

// -- Loading Skeletons --
function showSkeletons() {
    const skeletonCard = `<div class="skeleton-card"><div class="skeleton skeleton-line full"></div><div class="skeleton skeleton-line medium"></div><div class="skeleton skeleton-line short"></div></div>`;
    const skeletonCards = Array(4).fill(`<div class="skeleton-card p-4"><div class="skeleton skeleton-line short" style="height:10px;margin-bottom:8px;"></div><div class="skeleton skeleton-line medium" style="height:24px;"></div></div>`).join('');
    document.getElementById('summary-cards').innerHTML = `<div class="col-span-2 md:col-span-4 grid grid-cols-2 md:grid-cols-4 gap-4">${skeletonCards}</div>`;
    ['tab-prensa', 'tab-redes', 'tab-actividad'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = Array(3).fill(skeletonCard).join('');
    });
}

// -- Global Search --
let _searchTimeout = null;
function debounceGlobalSearch(q) {
    clearTimeout(_searchTimeout);
    const results = document.getElementById('global-search-results');
    if (!q || q.length < 2) { results.classList.add('hidden'); return; }
    _searchTimeout = setTimeout(() => globalSearch(q), 300);
}

async function globalSearch(q) {
    if (!currentPlayerId || !q) return;
    const results = document.getElementById('global-search-results');
    try {
        const data = await fetch(`/api/search?player_id=${currentPlayerId}&q=${encodeURIComponent(q)}`).then(r => r.json());
        if (!data.length) {
            results.innerHTML = '<div class="p-4 text-sm text-gray-500 text-center">Sin resultados</div>';
            results.classList.remove('hidden');
            return;
        }
        const typeIcons = { press: '📰', social: '💬', post: '📱' };
        const typeLabels = { press: 'Prensa', social: 'Redes', post: 'Post' };
        results.innerHTML = data.map(r => `
            <div class="p-3 card-hover border-b border-gray-800/50">
                <div class="flex items-center gap-2 mb-1">
                    <span class="text-xs">${typeIcons[r.type] || ''}</span>
                    <span class="text-[10px] px-2 py-0.5 rounded-full bg-dark-500 text-gray-400">${typeLabels[r.type] || r.type}</span>
                    <span class="text-[10px] text-gray-600">${r.extra || ''}</span>
                    <span class="text-[10px] px-2 py-0.5 rounded-full badge-${r.sentiment_label || 'neutro'}">${r.sentiment_label || ''}</span>
                </div>
                <p class="text-sm text-gray-300 line-clamp-2">${escapeHtml((r.text || '').slice(0, 150))}</p>
                <div class="flex items-center gap-3 mt-1">
                    <span class="text-[10px] text-gray-600">${formatDate(r.date)}</span>
                    ${r.url ? `<a href="${r.url}" target="_blank" class="text-[10px] text-accent hover:underline">Ver</a>` : ''}
                </div>
            </div>
        `).join('');
        results.classList.remove('hidden');
    } catch (e) { results.classList.add('hidden'); }
}

// Close search results on click outside
document.addEventListener('click', (e) => {
    const sr = document.getElementById('global-search-results');
    const si = document.getElementById('global-search');
    if (sr && si && !sr.contains(e.target) && e.target !== si) sr.classList.add('hidden');
});

// -- Platform Filter --
function filterPlatform(platform) {
    document.querySelectorAll('.platform-filter-btn').forEach(b => b.classList.remove('active'));
    if (platform) {
        document.querySelector(`[data-platform="${platform}"]`)?.classList.add('active');
    } else {
        document.querySelector('[data-platform="all"]')?.classList.add('active');
    }
    const list = document.getElementById('social-list');
    if (!list) return;
    list.querySelectorAll('.search-item').forEach(item => {
        if (!platform) { item.style.display = ''; return; }
        const search = item.dataset.search || '';
        item.style.display = search.includes(platform) ? '' : 'none';
    });
}

// -- Search/Filter --
function filterList(query, type) {
    const listId = type === 'press' ? 'press-list' : type === 'social' ? 'social-list' : 'activity-list';
    const list = document.getElementById(listId);
    if (!list) return;
    const items = list.querySelectorAll('.search-item');
    const q = query.toLowerCase().trim();
    items.forEach(item => {
        item.style.display = !q || (item.dataset.search && item.dataset.search.includes(q)) ? '' : 'none';
    });
}

// -- Tab switching --
function switchTab(tab) {
    // Desktop tabs
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    const desktopTab = document.querySelector(`.desktop-tab-bar [data-tab="${tab}"]`);
    if (desktopTab) desktopTab.classList.add('active');

    // Mobile bottom nav
    document.querySelectorAll('#mobile-nav button').forEach(b => b.classList.remove('active'));
    const mobileTab = document.querySelector(`#mobile-nav [data-tab="${tab}"]`);
    if (mobileTab) mobileTab.classList.add('active');

    // Tab content
    document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
    document.getElementById(`tab-${tab}`).classList.remove('hidden');
}

// -- Chart helpers --
function createDoughnutChart(canvasId, data) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (charts[canvasId]) charts[canvasId].destroy();
    charts[canvasId] = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: data.labels, datasets: [{ data: data.values, backgroundColor: data.colors || ['#00ba7c', '#ffd166', '#f4212e'], borderWidth: 0 }] },
        options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { color: '#71767b', boxWidth: 12, padding: 12 } } }, cutout: '65%' }
    });
}

function createBarChart(canvasId, labels, values, color) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (charts[canvasId]) charts[canvasId].destroy();
    charts[canvasId] = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ data: values, backgroundColor: color + '40', borderColor: color, borderWidth: 1, borderRadius: 4 }] },
        options: { responsive: true, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#71767b', font: { size: 10 } }, grid: { display: false } }, y: { ticks: { color: '#71767b' }, grid: { color: '#1a1a1a' } } } }
    });
}

function createLineChart(canvasId, labels, values, color, label, min, max) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (charts[canvasId]) charts[canvasId].destroy();
    const opts = { responsive: true, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#71767b', font: { size: 10 } }, grid: { display: false } }, y: { ticks: { color: '#71767b' }, grid: { color: '#1a1a1a' } } }, elements: { point: { radius: 3 }, line: { tension: 0.3 } } };
    if (min !== undefined) opts.scales.y.min = min;
    if (max !== undefined) opts.scales.y.max = max;
    charts[canvasId] = new Chart(ctx, { type: 'line', data: { labels, datasets: [{ label: label || '', data: values, borderColor: color, backgroundColor: color + '20', fill: true, borderWidth: 2 }] }, options: opts });
}

// -- Utility functions --
function buildSentimentDist(sentData) {
    if (!sentData || !sentData.length) return { labels: ['Sin datos'], values: [1], colors: ['#333'] };
    const map = {};
    sentData.forEach(s => { map[s.sentiment_label] = s.count; });
    return { labels: ['Positivo', 'Neutro', 'Negativo'], values: [map['positivo'] || 0, map['neutro'] || 0, map['negativo'] || 0], colors: ['#00ba7c', '#ffd166', '#f4212e'] };
}

function sentimentText(val) {
    if (val === null || val === undefined) return '-';
    if (val > 0.2) return '+' + val.toFixed(2);
    if (val < -0.2) return val.toFixed(2);
    return val.toFixed(2);
}

function sentimentColor(val) {
    if (val === null || val === undefined) return 'accent';
    if (val > 0.2) return 'positive';
    if (val < -0.2) return 'negative';
    return 'warning';
}

function platformIcon(platform) {
    const s = 16;
    const icons = {
        twitter: `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>`,
        reddit: `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0A12 12 0 000 12a12 12 0 0012 12 12 12 0 0012-12A12 12 0 0012 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 01-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.1 3.1 0 01.042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 014.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 01.14-.197.35.35 0 01.238-.042l2.906.617a1.214 1.214 0 011.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 00-.231.094.33.33 0 000 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 000-.463.327.327 0 00-.462 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 00-.205-.094z"/></svg>`,
        instagram: `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>`,
        youtube: `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>`,
        tiktok: `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/></svg>`,
        telegram: `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="currentColor"><path d="M11.944 0A12 12 0 000 12a12 12 0 0012 12 12 12 0 0012-12A12 12 0 0012 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 01.171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>`,
    };
    return icons[platform] || `<span class="text-xs font-bold">${platform || '?'}</span>`;
}

function renderPlatformBreakdown(items) {
    const counts = {};
    items.forEach(i => { counts[i.platform] = (counts[i.platform] || 0) + 1; });
    const platformColors = {
        twitter: '#1d9bf0', reddit: '#ff4500', instagram: '#e1306c',
        youtube: '#ff0000', tiktok: '#00f2ea', telegram: '#26a5e4',
    };
    return Object.entries(counts).map(([p, c]) => `
        <div class="flex items-center justify-between py-2">
            <span class="text-sm font-medium" style="color:${platformColors[p] || '#71767b'}">${platformIcon(p)} ${p}</span>
            <span class="text-sm text-white font-bold">${c}</span>
        </div>
    `).join('');
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return dateStr;
        return d.toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch { return dateStr; }
}

function formatDateTime(dateStr) {
    if (!dateStr) return '-';
    try {
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return dateStr;
        return d.toLocaleDateString('es-ES', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    } catch { return dateStr; }
}

function formatDuration(ms) {
    if (!ms || ms < 0) return '-';
    const secs = Math.floor(ms / 1000);
    if (secs < 60) return `${secs}s`;
    const mins = Math.floor(secs / 60);
    const remSecs = secs % 60;
    return `${mins}m ${remSecs}s`;
}

function fmtNum(n) {
    if (!n) return '0';
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// -- Init --
(async function init() {
    // Check if a scan is running
    try {
        const status = await fetch('/api/scan/status').then(r => r.json());
        if (status.running) {
            document.getElementById('setup-panel').classList.add('hidden');
            document.getElementById('scan-progress').classList.remove('hidden');
            pollScanStatus();
            return;
        }
    } catch (e) {}

    // Check if any player has scan data -> load dashboard
    try {
        const players = await fetch('/api/players').then(r => r.json());
        if (players && players.length > 0) {
            // Find first player with scan data
            for (const p of players) {
                try {
                    const summary = await fetch(`/api/summary?player_id=${p.id}`).then(r => r.json());
                    if (summary.press_count > 0 || summary.mentions_count > 0 || summary.posts_count > 0) {
                        currentPlayer = p;
                        await loadDashboard(p.id);
                        return;
                    }
                } catch (e) {}
            }
            // Players exist but none scanned -> show portfolio/selector
            document.getElementById('setup-panel').classList.add('hidden');
            showPortfolioSelector(players);
            return;
        }
    } catch (e) {
        console.log('No existing players, showing setup');
    }
    // No players at all -> show setup panel
})();

// -- Portfolio selector (shown when players exist but none scanned) --
function showPortfolioSelector(players) {
    const container = document.getElementById('dashboard');
    container.classList.remove('hidden');
    container.innerHTML = `
        <div class="max-w-2xl mx-auto mt-8 sm:mt-16">
            <div class="text-center mb-6 sm:mb-8">
                <img src="/static/logo.svg" alt="MediaPulse" class="w-14 h-14 sm:w-16 sm:h-16 mx-auto mb-4">
                <h2 class="text-xl sm:text-2xl font-bold text-white">Media<span class="text-accent">Pulse</span></h2>
                <p class="text-gray-500 mt-2 text-sm">Selecciona un jugador para escanear</p>
            </div>
            <div class="space-y-2 sm:space-y-3">
                ${players.map(p => {
                    const initials = (p.name || '').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
                    const photoHtml = p.photo_url
                        ? `<img src="${p.photo_url}" class="w-10 h-10 sm:w-12 sm:h-12 rounded-full object-cover border-2 border-gray-700">`
                        : `<div class="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-accent/20 flex items-center justify-center text-accent text-sm font-bold border-2 border-gray-700">${initials}</div>`;
                    const socials = [
                        p.twitter ? `<span class="text-[#1d9bf0]">X</span> @${p.twitter}` : '',
                        p.instagram ? `<span class="text-[#e1306c]">IG</span> @${p.instagram}` : '',
                    ].filter(Boolean).join(' &middot; ');
                    return `
                    <div class="bg-dark-700 rounded-xl border border-gray-800 p-3 sm:p-4 flex items-center gap-3 sm:gap-4 cursor-pointer hover:border-accent/50 transition group"
                         onclick="selectAndScan(${JSON.stringify(p).replace(/"/g, '&quot;')})">
                        ${photoHtml}
                        <div class="flex-1 min-w-0">
                            <div class="font-semibold text-white text-sm sm:text-base group-hover:text-accent transition">${p.name}</div>
                            <div class="text-xs text-gray-500">${p.club || ''} ${p.market_value ? '| ' + p.market_value : ''}</div>
                            ${socials ? `<div class="text-[10px] text-gray-600 mt-0.5">${socials}</div>` : ''}
                        </div>
                        <button class="bg-accent hover:bg-blue-600 text-white px-3 sm:px-4 py-2 rounded-lg text-xs sm:text-sm font-medium transition touch-target flex-shrink-0">
                            Escanear
                        </button>
                    </div>`;
                }).join('')}
            </div>
            <div class="mt-6 text-center">
                <button onclick="document.getElementById('dashboard').classList.add('hidden'); document.getElementById('setup-panel').classList.remove('hidden');"
                    class="text-sm text-gray-500 hover:text-accent transition">
                    + Agregar otro jugador
                </button>
            </div>
        </div>
    `;
}

async function selectAndScan(player) {
    document.getElementById('dashboard').classList.add('hidden');
    document.getElementById('scan-progress').classList.remove('hidden');
    document.getElementById('scan-message').textContent = 'Iniciando escaneo de ' + player.name + '...';

    const data = {
        name: player.name,
        twitter: player.twitter || null,
        instagram: player.instagram || null,
        club: player.club || null,
        transfermarkt_id: player.transfermarkt_id || null,
        tiktok: player.tiktok || null,
    };

    try {
        const resp = await fetch('/api/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!resp.ok) throw new Error(await resp.text());
        pollScanStatus();
    } catch (e) {
        document.getElementById('scan-message').textContent = 'Error: ' + e.message;
    }
}
