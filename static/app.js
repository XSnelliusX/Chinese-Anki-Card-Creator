const input = document.getElementById('word-input');
input.placeholder = "e.g. 你好, 謝謝";

async function generateCards() {
    const input = document.getElementById('word-input');
    const btn = document.getElementById('generate-btn');
    const btnText = document.getElementById('btn-text');
    const spinner = document.getElementById('btn-spinner');
    const logArea = document.getElementById('log-area');

    const text = input.value.trim();
    if (!text) return;

    // Parse words (comma or newline)
    const words = text.split(/[\n,]+/).map(w => w.trim()).filter(w => w);
    if (words.length === 0) return;

    // UI Loading State
    btn.disabled = true;
    btnText.textContent = "Generating...";
    spinner.classList.remove('hidden');
    logArea.innerHTML = ""; // Clear previous logs

    try {
        const endpoint = '/chinese';
        
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ words: words })
        });

        const data = await response.json();

        // Render Results
        if (data.results) {
            data.results.forEach(res => {
                const item = document.createElement('div');
                item.className = 'log-item';
                
                const statusClass = res.success ? 'status-success' : 'status-failed';
                const statusText = res.success ? 'SUCCESS' : 'FAILED';
                
                item.innerHTML = `
                    <span class="log-word">${res.word}</span>
                    <span class="log-status ${statusClass}">${statusText}</span>
                `;
                
                // If failed, maybe show reason in a small subtitle?
                if (!res.success) {
                    item.innerHTML += `<div style="font-size:10px; color:var(--error); width:100%; margin-top:5px;">${res.message}</div>`;
                    item.style.flexWrap = "wrap";
                }

                logArea.appendChild(item);
            });
        }

        // Clear input on success
        input.value = "";

    } catch (error) {
        alert("Error: " + error.message);
    } finally {
        // Reset UI
        btn.disabled = false;
        btnText.textContent = "Generate Cards";
        spinner.classList.add('hidden');
    }
}
