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
    
    // Clear previous logs but we'll add placeholders immediately
    logArea.innerHTML = "";
    const wordElements = {};

    words.forEach(word => {
        const item = document.createElement('div');
        item.className = 'log-item';
        item.id = `log-word-${word}`;
        item.innerHTML = `
            <div class="log-header">
                <span class="log-word">${word}</span>
                <span class="log-status hidden"></span>
            </div>
            <div class="progress-text">
                <div class="spinner spinner-small"></div>
                <span class="msg dots">Initializing</span>
            </div>
            <div class="sub-steps">
                <span class="sub-step" data-step="text">Text</span>
                <span class="sub-step" data-step="image">Image</span>
                <span class="sub-step" data-step="audio">Audio</span>
            </div>
        `;
        logArea.prepend(item); // Newest at top
        wordElements[word] = item;
    });

    input.value = "";

    try {
        const response = await fetch('/chinese/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ words: words })
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
