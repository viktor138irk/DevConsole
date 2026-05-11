let currentBusyTask = null;
let collectedErrors = [];
let selectedDeviceSerial = null;

function appendLog(message) {
    const systemLog = document.getElementById('systemLog');
    const time = new Date().toLocaleTimeString();
    const line = `[${time}] ${message}`;
    if (systemLog) {
        systemLog.innerText += systemLog.innerText ? `\n${line}` : line;
        requestAnimationFrame(() => { systemLog.scrollTop = systemLog.scrollHeight; });
        return;
    }
    const logs = document.getElementById('logs');
    if (!logs) return;
    logs.innerText += `\n${line}`;
    requestAnimationFrame(() => { logs.scrollTop = logs.scrollHeight; });
}

function appendRuntimeLog(message) {
    const logs = document.getElementById('logs');
    if (!logs) return;
    const time = new Date().toLocaleTimeString();
    logs.innerText += logs.innerText ? `\n[${time}] ${message}` : `[${time}] ${message}`;
    requestAnimationFrame(() => { logs.scrollTop = logs.scrollHeight; });
    collectErrorsFromText(message);
}

function clearRuntimeOutput() {
    const logs = document.getElementById('logs');
    if (logs) logs.innerText = '';
    collectedErrors = [];
    renderErrors();
}

function collectErrorsFromText(text) {
    if (!text) return;
    const patterns = [/error/i, /failed/i, /failure/i, /exception/i, /fatal/i, /could not/i, /cannot/i, /what went wrong/i, /execution failed/i, /❌/];
    const lines = String(text).split('\n').filter(line => patterns.some(pattern => pattern.test(line)));
    lines.forEach(line => {
        const cleaned = line.trim();
        if (cleaned && !collectedErrors.includes(cleaned)) collectedErrors.push(cleaned);
    });
    renderErrors();
}

function renderErrors() {
    const box = document.getElementById('errorsBox');
    const count = document.getElementById('errorCount');
    if (!box || !count) return;
    if (collectedErrors.length === 0) {
        box.innerText = 'Здесь появятся ошибки из Flutter, Gradle, ADB, API и stderr.';
        count.innerText = 'Ошибок пока нет';
        return;
    }
    box.innerText = collectedErrors.join('\n');
    count.innerText = `Ошибок: ${collectedErrors.length}`;
    requestAnimationFrame(() => { box.scrollTop = box.scrollHeight; });
}

function copyErrorsForAI() {
    navigator.clipboard.writeText(collectedErrors.join('\n') || 'Ошибок пока нет');
    appendLog('Ошибки скопированы в буфер');
}

function clearErrors() {
    collectedErrors = [];
    renderErrors();
    appendLog('Панель ошибок очищена');
}

function setStatus(message, state = 'idle') {
    const status = document.getElementById('runtimeStatus');
    const dot = document.getElementById('runtimeStatusDot');
    if (status) status.innerText = message;
    if (dot) dot.className = `status-dot ${state}`;
}

function setTaskProgress(percent, message, running = true) {
    const wrap = document.getElementById('taskProgressWrap');
    const bar = document.getElementById('taskProgressBar');
    const label = document.getElementById('taskProgressLabel');
    if (wrap) wrap.style.display = 'block';
    if (bar) bar.style.width = `${percent}%`;
    if (label) label.innerText = `${percent}% — ${message}`;
    setStatus(message, running ? 'running' : 'done');
}

function setBusy(message) { currentBusyTask = message; setTaskProgress(5, message, true); appendLog(message); }
function setDone(message) { currentBusyTask = null; setTaskProgress(100, message, false); appendLog(`✅ ${message}`); }
function setError(message) { currentBusyTask = null; setStatus(message, 'error'); appendLog(`❌ ${message}`); }

function updateProgressFromLine(line) {
    const text = line.toLowerCase();
    if (text.includes('resolving dependencies')) setTaskProgress(20, 'Разбор зависимостей Flutter', true);
    else if (text.includes('downloading packages')) setTaskProgress(35, 'Загрузка пакетов', true);
    else if (text.includes('got dependencies')) setTaskProgress(65, 'Зависимости готовы', true);
    else if (text.includes('running gradle task')) setTaskProgress(50, 'Gradle собирает приложение', true);
    else if (text.includes('built ') || text.includes('app-release.apk')) setTaskProgress(95, 'APK собран', true);
    else if (text.includes('ota publish')) setTaskProgress(92, 'OTA публикация', true);
    else if (text.includes('installing') || text.includes('performing streamed install')) setTaskProgress(70, 'Установка на устройство', true);
    else if (text.includes('flutter run key commands')) setTaskProgress(90, 'Приложение запущено, Flutter подключён', true);
}

async function workspaceApi(url, payload = {}, method = 'POST') {
    appendLog(`API запрос: ${url}`);
    const response = await fetch(url, { method, headers: {'Content-Type': 'application/json'}, body: method === 'GET' ? undefined : JSON.stringify(payload) });
    const data = await response.json().catch(() => ({success: false, detail: 'Пустой ответ сервера'}));
    if (!response.ok) appendLog(`Ошибка API ${response.status}: ${data.detail || 'unknown error'}`);
    return data;
}

async function streamRuntimeCommand(command, title, progress = 50) {
    const workspace = getWorkspacePath();
    if (!workspace) { setError('Workspace не выбран'); return false; }
    clearRuntimeOutput();
    setTaskProgress(progress, title || command, true);
    appendLog(`▶ ${title || command} live`);
    appendRuntimeLog(`▶ ${title || command} live`);
    const response = await fetch('/api/runtime/command-stream', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({workspace, command, device: getSelectedDevice()}) });
    if (!response.ok || !response.body) { setError(`Не удалось открыть live stream: ${title || command}`); appendRuntimeLog(`❌ Не удалось открыть live stream: ${title || command}`); return false; }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let ok = true;
    while (true) {
        const {value, done} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true});
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const raw of lines) {
            if (!raw.trim()) continue;
            let event;
            try { event = JSON.parse(raw); } catch (_) { appendRuntimeLog(raw); continue; }
            if (event.type === 'line') { appendRuntimeLog(event.message); updateProgressFromLine(event.message); }
            else if (event.type === 'error') { ok = false; appendRuntimeLog(`❌ ${event.message}`); setError(event.message); }
            else if (event.type === 'publish') { const message = event.success ? '✅ OTA публикация выполнена' : `OTA публикация пропущена: ${event.result?.message || ''}`; appendRuntimeLog(message); appendLog(message); }
            else if (event.type === 'done') { ok = Number(event.returncode) === 0; appendRuntimeLog(ok ? `✅ Выполнено: ${title || command}` : `❌ Ошибка: ${title || command} exit ${event.returncode}`); }
        }
    }
    if (!ok) setError(`Ошибка: ${title || command}`);
    return ok;
}

async function streamFlutterBatch(commands) {
    const workspace = getWorkspacePath();
    if (!workspace) { setError('Workspace не выбран'); return false; }
    if (!commands || !commands.trim()) { setError('Команда Flutter не указана'); return false; }
    clearRuntimeOutput();
    setTaskProgress(5, 'Flutter batch запущен', true);
    appendLog('▶ Flutter batch live');
    appendRuntimeLog('▶ Flutter batch live');
    const response = await fetch('/api/runtime/flutter-batch-stream', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({workspace, commands, device: getSelectedDevice(), stop_on_error: true})
    });
    if (!response.ok || !response.body) {
        const text = await response.text().catch(() => '');
        setError('Не удалось открыть Flutter batch stream');
        appendRuntimeLog(`❌ Flutter batch stream error ${response.status}: ${text}`);
        return false;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let ok = true;
    while (true) {
        const {value, done} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true});
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const raw of lines) {
            if (!raw.trim()) continue;
            let event;
            try { event = JSON.parse(raw); } catch (_) { appendRuntimeLog(raw); continue; }
            if (event.type === 'batch_start') { appendRuntimeLog(event.message); setTaskProgress(10, event.message, true); }
            else if (event.type === 'line') { appendRuntimeLog(event.message); updateProgressFromLine(event.message); }
            else if (event.type === 'start') { appendRuntimeLog(`$ ${event.message}`); setTaskProgress(20, event.message, true); }
            else if (event.type === 'error') { ok = false; appendRuntimeLog(`❌ ${event.message}`); setError(event.message); }
            else if (event.type === 'done') { appendRuntimeLog(Number(event.returncode) === 0 ? `✅ ${event.message}` : `❌ ${event.message} exit ${event.returncode}`); }
            else if (event.type === 'batch_done') { ok = Boolean(event.success); appendRuntimeLog(ok ? '✅ Flutter batch completed' : '❌ Flutter batch failed'); }
        }
    }
    setTaskProgress(100, ok ? 'Flutter batch завершён' : 'Flutter batch завершён с ошибкой', false);
    if (!ok) setStatus('Flutter batch error', 'error');
    return ok;
}

function runFlutterCommandBatch() {
    const input = document.getElementById('flutterCommandInput');
    streamFlutterBatch(input ? input.value : '');
}

function setFlutterPreset(value) {
    const input = document.getElementById('flutterCommandInput');
    if (input) input.value = value;
}

function initFlutterConsole() {
    if (document.getElementById('flutterConsolePanel')) return;
    const logsWrap = document.querySelector('.logs-wrap');
    const logs = document.getElementById('logs');
    if (!logsWrap || !logs) return;
    const panel = document.createElement('div');
    panel.id = 'flutterConsolePanel';
    panel.style.cssText = 'padding:12px;border-top:1px solid #2a2f3a;background:#10141b;flex:0 0 auto;';
    panel.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px">
            <strong>Flutter console</strong><span class="note">Ctrl+Enter запуск</span>
        </div>
        <textarea id="flutterCommandInput" style="min-height:96px;font-family:monospace;font-size:12px" placeholder="flutter clean&#10;flutter pub get&#10;flutter analyze&#10;flutter run --profile"></textarea>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
            <button class="mini-btn" onclick="runFlutterCommandBatch()">Run Batch</button>
            <button class="mini-btn muted" onclick="setFlutterPreset('flutter clean\\nflutter pub get\\nflutter analyze')">check</button>
            <button class="mini-btn muted" onclick="setFlutterPreset('flutter clean\\nflutter pub get\\nflutter build apk --debug')">debug APK</button>
            <button class="mini-btn muted" onclick="setFlutterPreset('flutter clean\\nflutter pub get\\nflutter run --profile')">run profile</button>
        </div>`;
    logsWrap.insertBefore(panel, logs.nextSibling);
    const input = document.getElementById('flutterCommandInput');
    if (input) {
        input.addEventListener('keydown', event => {
            if (event.ctrlKey && event.key === 'Enter') {
                event.preventDefault();
                runFlutterCommandBatch();
            }
        });
    }
}

function getSelectedDevice() { return selectedDeviceSerial; }
function getWorkspacePath() { const input = document.getElementById('workspacePath'); return input ? input.value.trim() : ''; }
function selectDevice(serial) {
    selectedDeviceSerial = serial;
    document.querySelectorAll('.device-card').forEach(card => card.classList.toggle('selected', card.dataset.serial === serial));
    appendLog(`📱 Выбрано устройство: ${serial}`);
}

async function loadSystemStatus() { setStatus('Проверяю состояние DevConsole', 'running'); await workspaceApi('/api/system/status', {}, 'GET'); setStatus('DevConsole готов', 'done'); }

async function saveGitHubSettings() {
    const username = document.getElementById('githubUsername')?.value.trim() || '';
    const token = document.getElementById('githubToken')?.value.trim() || '';
    if (!username) { setError('Укажите GitHub login'); return; }
    if (!token) { setError('Укажите GitHub key'); return; }
    const data = await workspaceApi('/api/settings/github', {username, token});
    if (data.success) { const tokenInput = document.getElementById('githubToken'); if (tokenInput) tokenInput.value = ''; appendLog('✅ GitHub доступ сохранён'); }
    else setError('Не удалось сохранить GitHub доступ');
}

function renderGroupedRuntimeButtons() {
    const container = document.getElementById('runtimeButtons');
    if (!container) return;
    container.innerHTML = `<button onclick="runRuntimeScenario('check')">Проверить</button><button onclick="runRuntimeScenario('run_profile')">Запустить</button><button onclick="runRuntimeScenario('build')">Собрать APK</button><button onclick="runRuntimeScenario('install')">Установить APK</button><button onclick="runRuntimeScenario('diagnostics')">Диагностика</button>`;
}

async function loadRuntimeCommands() { renderGroupedRuntimeButtons(); setStatus('Runtime сценарии готовы', 'done'); }
async function executeRuntimeCommand(command, title, progress = 50) { return await streamRuntimeCommand(command, title, progress); }

async function runRuntimeScenario(scenario) {
    const workspace = getWorkspacePath();
    if (!workspace) { setError('Workspace не выбран'); return; }
    if (scenario === 'check') { setBusy('Проверка проекта'); if (!await executeRuntimeCommand('git_pull', 'Git Pull', 25)) return; if (!await executeRuntimeCommand('flutter_pub_get', 'Flutter Pub Get', 70)) return; setDone('Проверка завершена'); return; }
    if (scenario === 'run_profile') { if (!getSelectedDevice()) { setError('Устройство не выбрано'); return; } setBusy('Запуск на телефоне'); if (!await executeRuntimeCommand('flutter_pub_get', 'Подготовка зависимостей', 30)) return; if (!await executeRuntimeCommand('flutter_run_profile', 'Flutter Run --profile', 75)) return; setDone('Запуск завершён'); return; }
    if (scenario === 'build') { setBusy('Сборка APK'); if (!await executeRuntimeCommand('flutter_clean', 'Flutter Clean', 20)) return; if (!await executeRuntimeCommand('flutter_pub_get', 'Flutter Pub Get', 45)) return; if (!await executeRuntimeCommand('flutter_build_apk', 'Flutter Build APK', 80)) return; setDone('Сборка APK завершена'); return; }
    if (scenario === 'install') { setBusy('Установка APK'); await installLatestApk(); return; }
    if (scenario === 'diagnostics') { setBusy('Диагностика Android runtime'); if (!await executeRuntimeCommand('adb_reconnect', 'ADB Reconnect', 40)) return; if (!await executeRuntimeCommand('adb_logcat', 'ADB Logcat Snapshot', 80)) return; setDone('Диагностика завершена'); }
}

async function stopRuntimeCommand() {
    const data = await workspaceApi('/api/runtime/stop', {send_confirm: true});
    appendLog(data.success ? '🛑 Команда остановлена' : 'Не удалось остановить команду');
}

async function installLatestApk() {
    const workspace = getWorkspacePath();
    clearRuntimeOutput();
    setTaskProgress(40, 'Отправляю APK на устройство', true);
    appendLog('▶ Install latest APK');
    appendRuntimeLog('▶ Install latest APK');
    const data = await workspaceApi('/api/runtime/install-latest-apk', {workspace, device: getSelectedDevice()});
    if (data.result?.stdout) appendRuntimeLog(data.result.stdout);
    if (data.result?.stderr) appendRuntimeLog(data.result.stderr);
    if (data.success) setDone('APK установлен'); else setError('Ошибка установки APK');
}

async function restartCurrentApp() {
    const workspace = getWorkspacePath();
    const packageName = document.getElementById('packageName').value;
    if (!packageName) { setError('Укажите package name'); return; }
    clearRuntimeOutput();
    appendLog(`▶ Restart app: ${packageName}`);
    appendRuntimeLog(`▶ Restart app: ${packageName}`);
    const data = await workspaceApi('/api/runtime/restart-app', {workspace, device: getSelectedDevice(), package_name: packageName});
    if (data.result?.stdout) appendRuntimeLog(data.result.stdout);
    if (data.result?.stderr) appendRuntimeLog(data.result.stderr);
    if (data.success) setDone('Приложение перезапущено'); else setError('Ошибка перезапуска приложения');
}

async function loadProjects() {
    const container = document.getElementById('projectsList');
    if (!container) return;
    setStatus('Загружаю список проектов', 'running');
    const data = await workspaceApi('/api/projects/list', {}, 'GET');
    const projects = data.projects || [];
    if (projects.length === 0) { container.innerHTML = 'Проекты отсутствуют'; setStatus('Проекты отсутствуют', 'idle'); return; }
    container.innerHTML = projects.map(project => {
        const ota = project.ota?.enabled ? '<span class="ota-badge">OTA</span>' : '';
        return `<div class="project-card" onclick="openProject('${project.workspace}', '${project.name || 'project'}')"><div class="project-top"><strong>${project.name}</strong><button class="icon-btn" onclick="event.stopPropagation();openEditProjectModal('${project.workspace}')">⚙</button></div><small>${project.stack || 'unknown stack'}</small><br><small>${project.workspace}</small><br>${ota}</div>`;
    }).join('');
    setStatus(`Проекты загружены: ${projects.length}`, 'done');
}

function openProject(workspace, name = 'project') {
    document.getElementById('workspacePath').value = workspace;
    appendLog(`Открытие проекта: ${workspace}`);
    setTaskProgress(100, `Проект выбран: ${name}`, false);
    setStatus(`Проект готов: ${name}`, 'done');
}

async function openEditProjectModal(workspace) {
    const modal = document.getElementById('editProjectModal');
    const data = await workspaceApi(`/api/projects/settings?workspace=${encodeURIComponent(workspace)}`, {}, 'GET');
    if (!data.success) { setError('Не удалось загрузить настройки проекта'); return; }
    const project = data.project || {};
    const ota = project.ota || {};
    document.getElementById('editProjectTitle').innerText = `Настройки: ${project.name || 'project'}`;
    document.getElementById('editWorkspace').value = workspace;
    document.getElementById('otaEnabled').checked = Boolean(ota.enabled);
    document.getElementById('otaHost').value = ota.sftp_host || '';
    document.getElementById('otaPort').value = ota.sftp_port || '22';
    document.getElementById('otaUsername').value = ota.sftp_username || '';
    document.getElementById('otaPassword').value = '';
    document.getElementById('otaRemotePath').value = ota.remote_path || '';
    document.getElementById('otaPublicBaseUrl').value = ota.public_base_url || '';
    document.getElementById('otaLatestJsonName').value = ota.latest_json_name || 'latest.json';
    document.getElementById('otaLatestApkName').value = ota.latest_apk_name || 'pulse-latest.apk';
    document.getElementById('otaVersion').value = ota.version || '';
    document.getElementById('otaBuild').value = ota.build || '';
    document.getElementById('otaNotes').value = ota.notes || '';
    toggleOtaFields();
    modal.style.display = 'flex';
}

function closeEditProjectModal() { document.getElementById('editProjectModal').style.display = 'none'; }

async function saveProjectSettings() {
    const workspace = document.getElementById('editWorkspace').value;
    const ota = {
        enabled: document.getElementById('otaEnabled').checked,
        sftp_host: document.getElementById('otaHost').value.trim(),
        sftp_port: document.getElementById('otaPort').value.trim() || '22',
        sftp_username: document.getElementById('otaUsername').value.trim(),
        remote_path: document.getElementById('otaRemotePath').value.trim(),
        public_base_url: document.getElementById('otaPublicBaseUrl').value.trim(),
        latest_json_name: document.getElementById('otaLatestJsonName').value.trim() || 'latest.json',
        latest_apk_name: document.getElementById('otaLatestApkName').value.trim() || 'pulse-latest.apk',
        version: document.getElementById('otaVersion').value.trim(),
        build: document.getElementById('otaBuild').value.trim(),
        notes: document.getElementById('otaNotes').value.trim()
    };
    const password = document.getElementById('otaPassword').value.trim();
    if (password) ota.sftp_password = password;
    const data = await workspaceApi('/api/projects/settings', {workspace, settings: {ota}});
    if (data.success) { appendLog('✅ Настройки проекта сохранены'); closeEditProjectModal(); loadProjects(); }
    else setError('Не удалось сохранить настройки проекта');
}

async function registerCurrentProject(repoUrl, workspace, stack = 'unknown') {
    const name = repoUrl.split('/').pop().replace('.git', '');
    await workspaceApi('/api/projects/register', {name, repo_url: repoUrl, workspace, stack});
    appendLog(`Проект зарегистрирован: ${name}`);
    loadProjects();
}

function parseLegacyDevices(stdout) {
    return (stdout || '').split('\n').filter(line => line.includes('device') && !line.includes('List')).map(line => ({serial: line.split(/\s+/)[0], title: line.split(/\s+/)[0], subtitle: 'ADB device', state: 'device'}));
}

async function loadDevices() {
    setStatus('Ищу Android устройства', 'running');
    const data = await workspaceApi('/api/android/devices');
    const container = document.getElementById('devices');
    if (!container) return;
    const devices = Array.isArray(data.devices) && data.devices.length > 0 ? data.devices : parseLegacyDevices(data.stdout || '');
    if (devices.length === 0) { container.innerHTML = 'Устройства не подключены'; setStatus('Android устройства не подключены', 'idle'); return; }
    container.innerHTML = devices.map(device => `<div class="device-card ${selectedDeviceSerial === device.serial ? 'selected' : ''}" data-serial="${device.serial}" onclick="selectDevice('${device.serial}')"><strong>📱 ${device.title || device.serial}</strong><br><small>${device.subtitle || device.serial}</small></div>`).join('');
    if (!selectedDeviceSerial && devices[0]) requestAnimationFrame(() => selectDevice(devices[0].serial));
    setStatus(`Android устройства найдены: ${devices.length}`, 'done');
}

window.addEventListener('load', () => {
    setStatus('Запуск DevConsole runtime', 'running');
    appendLog('DevConsole runtime initialized...');
    initFlutterConsole();
    loadSystemStatus();
    loadDevices();
    loadProjects();
    loadRuntimeCommands();
    appendLog('DevConsole workspace runtime готов');
});
