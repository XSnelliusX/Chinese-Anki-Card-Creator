async function generateCards() {
    const input = document.getElementById('word-input');
    const btn = document.getElementById('generate-btn');
    const btnText = document.getElementById('btn-text');
    const spinner = document.getElementById('btn-spinner');
    const logArea = document.getElementById('log-area');

    const text = input.value.trim();
    if (!text) return;

    const words = text.split(/[\n,]+/).map(w => w.trim()).filter(w => w);
    if (words.length === 0) return;

    // UI Loading State
    btn.disabled = true;
    btnText.textContent = "Processing...";
    spinner.classList.remove('hidden');

    // Get API Key if exists
    const apiKey = localStorage.getItem('anki_api_key') || "";
    const headers = { 'Content-Type': 'application/json' };
    if (apiKey) {
        headers['X-API-Key'] = apiKey;
    }
    input.value = "";

    try {
        const response = await fetch('/chinese/stream', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({ words: words })
        });

        if (response.status === 401) {
            alert("Unauthorized: Please check your API Key in settings.");
            return;
        }

        if (!response.ok) {
            alert(`Error: ${response.statusText}`);
            return;
        }

        // Clear previous logs and only add placeholders if authorized
        logArea.innerHTML = "";
        const wordElements = {};

        words.forEach(word => {
            const item = document.createElement('div');
            item.className = 'log-item';
            item.id = `log-word-${word.replace(/[^a-zA-Z0-9]/g, '_')}`; // Use a safe ID

            const header = document.createElement('div');
            header.className = 'log-header';

            const wordSpan = document.createElement('span');
            wordSpan.className = 'log-word';
            wordSpan.textContent = word;

            const statusSpan = document.createElement('span');
            statusSpan.className = 'log-status hidden';

            header.appendChild(wordSpan);
            header.appendChild(statusSpan);

            const progressDiv = document.createElement('div');
            progressDiv.className = 'progress-text';
            progressDiv.innerHTML = '<div class="spinner spinner-small"></div><span class="msg dots">Initializing</span>';

            const subStepsDiv = document.createElement('div');
            subStepsDiv.className = 'sub-steps';
            ['Text', 'Image', 'Audio'].forEach(step => {
                const s = document.createElement('span');
                s.className = 'sub-step';
                s.dataset.step = step.toLowerCase();
                s.textContent = step;
                subStepsDiv.appendChild(s);
            });

            item.appendChild(header);
            item.appendChild(progressDiv);
            item.appendChild(subStepsDiv);

            logArea.prepend(item); // Newest at top
            wordElements[word] = item;
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        handleStreamEvent(data, wordElements);
                    } catch (e) { console.error("Error parsing stream:", e); }
                }
            }
        }

    } catch (error) {
        console.error("Stream error:", error);
    } finally {
        btn.disabled = false;
        btnText.textContent = "Generate Cards";
        spinner.classList.add('hidden');
    }
}

function handleStreamEvent(data, wordElements) {
    if (data.type === 'progress') {
        const item = wordElements[data.word];
        if (!item) return;
        const msgSpan = item.querySelector('.msg');
        msgSpan.textContent = data.message;

        // Mark sub-steps as active based on message content
        const steps = item.querySelectorAll('.sub-step');
        steps.forEach(s => s.classList.remove('active'));

        if (data.message.includes('text')) item.querySelector('[data-step="text"]').classList.add('active');
        if (data.message.includes('image')) item.querySelector('[data-step="image"]').classList.add('active');
        if (data.message.includes('audio')) item.querySelector('[data-step="audio"]').classList.add('active');
    }
    else if (data.type === 'done') {
        const item = wordElements[data.word];
        if (!item) return;

        // Final statuses for sub-steps
        const textFailed = data.text && data.text.startsWith('Failed');
        const imageFailed = data.image && data.image.startsWith('Failed');
        const audioFailed = data.audio && data.audio.startsWith('Failed');

        const hasWarning = data.success && (imageFailed || audioFailed);

        const statusLabel = item.querySelector('.log-status');
        statusLabel.classList.remove('hidden');

        if (data.success) {
            if (hasWarning) {
                statusLabel.textContent = 'WARNING';
                statusLabel.className = 'log-status status-warning';
            } else {
                statusLabel.textContent = 'SUCCESS';
                statusLabel.className = 'log-status status-success';
            }
        } else {
            statusLabel.textContent = 'FAILED';
            statusLabel.className = 'log-status status-failed';
        }

        // Update sub-step styles
        updateSubStep(item, 'text', textFailed);
        updateSubStep(item, 'image', imageFailed);
        updateSubStep(item, 'audio', audioFailed);

        // Hide progress text and spinner
        item.querySelector('.progress-text').classList.add('hidden');

        if (!data.success) {
            const errDiv = document.createElement('div');
            errDiv.style = "font-size:12px; color:var(--error); margin-top:5px;";
            errDiv.textContent = data.message;
            item.appendChild(errDiv);
        } else if (hasWarning) {
            let warnMsg = "Card created, but: ";
            if (imageFailed) warnMsg += "Image failed. ";
            if (audioFailed) warnMsg += "Audio failed.";
            const warnDiv = document.createElement('div');
            warnDiv.style = "font-size:12px; color:var(--warning); margin-top:5px;";
            warnDiv.textContent = warnMsg;
            item.appendChild(warnDiv);
        }
    }
}

function updateSubStep(item, step, isFailed) {
    const el = item.querySelector(`[data-step="${step}"]`);
    if (!el) return;
    el.classList.remove('active');
    el.classList.add(isFailed ? 'failed' : 'success');
}

// --- Stats Logic ---
async function toggleStats() {
    const existing = document.getElementById('stats-modal');
    if (existing) {
        existing.remove();
        return;
    }

    try {
        const apiKey = localStorage.getItem('anki_api_key') || "";
        const headers = {};
        if (apiKey) headers['X-API-Key'] = apiKey;

        const response = await fetch('/usage', { headers: headers });
        if (response.status === 401) {
            alert("Unauthorized: Please check your API Key in settings.");
            return;
        }
        const data = await response.json();
        showStatsModal(data);
    } catch (e) {
        console.error("Failed to fetch stats:", e);
    }
}

function showStatsModal(data) {
    const modal = document.createElement('div');
    modal.id = 'stats-modal';
    modal.className = 'modal-overlay';
    modal.onclick = (e) => { if (e.target === modal) toggleStats(); };

    modal.innerHTML = `
        <div class="modal">
            <div class="modal-header">
                <h2>Cost Overview</h2>
                <button class="close-btn" onclick="toggleStats()">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card stat-full-width">
                    <div class="stat-label">Total Consumption</div>
                    <div class="stat-cost">$${data.total_cost.toFixed(4)}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Words</div>
                    <div class="stat-value">${data.words_processed}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Avg / Word</div>
                    <div class="stat-value">$${data.avg_cost_per_word.toFixed(4)}</div>
                </div>
            </div>

            <div class="components-list">
                <div class="component-item">
                    <span class="comp-name">Text</span>
                    <span class="comp-val">${data.components.text.total} tkn</span>
                    <span class="comp-price">$${data.components.text.cost.toFixed(4)}</span>
                </div>
                <div class="component-item">
                    <span class="comp-name">Image</span>
                    <span class="comp-val">${data.components.image.total} img</span>
                    <span class="comp-price">$${data.components.image.cost.toFixed(4)}</span>
                </div>
                <div class="component-item">
                    <span class="comp-name">Audio</span>
                    <span class="comp-val">${(data.components.audio.total / 1000).toFixed(1)}k chars</span>
                    <span class="comp-price">$${data.components.audio.cost.toFixed(4)}</span>
                </div>
            </div>
            
            <div style="margin-top: 24px; font-size: 11px; color: var(--text-light); text-align: center;">
                Prices based on Google Cloud Vertex AI standard rates.
            </div>
        </div>
    `;

    document.body.appendChild(modal);
}

function toggleSettings() {
    const key = prompt("Enter API Key (leave blank if not used):", localStorage.getItem('anki_api_key') || "");
    if (key !== null) {
        localStorage.setItem('anki_api_key', key);
    }
}
