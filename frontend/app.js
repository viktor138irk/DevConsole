async function api(url, options = {}) {
    const response = await fetch(url, options);
    return await response.json();
}

async function loadStatus() {
    const data = await api('/api/system/status');

    document.getElementById('systemStatus').innerHTML = `
        <div class="status-grid">
            <div class="status-item"><span>Project</span><strong>${data.project}</strong></div>
            <div class="status-item"><span>Version</span><strong>${data.version}</strong></div>
            <div class="status-item"><span>OpenAI</span><strong>${data.openai_configured ? 'Configured' : 'Not configured'}</strong></div>
            <div class="status-item"><span>Model</span><strong>${data.openai_model}</strong></div>
        </div>
    `;
}

async function analyzeProject() {
    const repo_url = document.getElementById('repoUrl').value;

    document.getElementById('projectResult').innerText = 'Analyzing repository...';

    const data = await api('/api/projects/analyze', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ repo_url })
    });

    document.getElementById('projectResult').innerText = JSON.stringify(data, null, 2);
}

async function adbDevices() {
    const data = await api('/api/android/devices', {
        method: 'POST'
    });

    document.getElementById('adbResult').innerText = data.stdout || data.stderr;
}

loadStatus();
