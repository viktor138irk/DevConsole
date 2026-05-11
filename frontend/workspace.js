let currentBusyTask = null;
let collectedErrors = [];

function appendLog(message) {
    const logs = document.getElementById('logs');
    if (!logs) return;

    const time = new Date().toLocaleTimeString();
    logs.innerText += `\n[${time}] ${message}`;
    requestAnimationFrame(() => { logs.scrollTop = logs.scrollHeight; });
    collectErrorsFromText(message);
}

function collectErrorsFromText(text) {
    if (!text) return;
    const patterns = [
        /error/i, /failed/i, /failure/i, /exception/i, /fatal/i,
        /gradle task assemble.*failed/i, /could not/i, /cannot/i,
        /what went wrong/i, /execution failed/i, /❌/
    ];
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
    const text = collectedErrors.join('\n');
    navigator.clipboard.writeText(text || 'Ошибок пока нет');
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

function setBusy(message) {
    currentBusyTask = message;
    setStatus(message, 'running');
    setTaskProgress(5, message, true);
}

function setDone(message) {
    currentBusyTask = null;
    setTaskProgress(100, message, false);
    appendLog(`✅ ${message}`);
}

function setError(message) {
    currentBusyTask = null;
    const label = document.getElementById('taskProgressLabel');
    if (label) label.innerText = `Ошибка — ${message}`;
    setStatus(message, 'error');
    appendLog(`❌ ${message}`);
}

function updateProgressFromLine(line) {
    const text = line.toLowerCase();
    if (text.includes('resolving dependencies')) setTaskProgress(20, 'Разбор зависимостей Flutter', true);
    else if (text.includes('downloading packages')) setTaskProgress(35, 'Загрузка пакетов', true);
    else if (text.includes('got dependencies')) setTaskProgress(65, 'Зависимости готовы', true);
    else if (text.includes('running gradle task')) setTaskProgress(50, 'Gradle собирает приложение', true);
    else if (text.includes('built ') || text.includes('app-release.apk')) setTaskProgress(95, 'APK собран', true);
    else if (text.includes('installing') || text.includes('performing streamed install')) setTaskProgress(70, 'Установка на устройство', true);
    else if (text.includes('syncing files')) setTaskProgress(80, 'Синхронизация файлов на телефоне', true);
    else if (text.includes('flutter run key commands')) setTaskProgress(90, 'Приложение запущено, Flutter подключён', true);
}

async function workspaceApi(url, payload = {}, method = 'POST') {
    appendLog(`API запрос: ${url}`);
    const response = await fetch(url, {
        method,
        headers: {'Content-Type': 'application/json'},
        body: method === 'GET' ? undefined : JSON.stringify(payload)
    });
    const data = await response.json().catch(() => ({success: false, detail: 'Пустой ответ сервера'}));
    if (!response.ok) appendLog(`Ошибка API ${response.status}: ${data.detail || 'unknown error'}`);
    return data;
}

async function streamRuntimeCommand(command, title, progress = 50) {
    const workspace = getWorkspacePath();
    if (!workspace) {
        setError('Workspace не выбран');
        return false;
    }

    setTaskProgress(progress, title || command, true);
    appendLog(`▶ ${title || command} live`);

    const response = await fetch('/api/runtime/command-stream', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({workspace, command, device: getSelectedDevice()})
    });

    if (!response.ok || !response.body) {
        setError(`Не удалось открыть live stream: ${title || command}`);
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
            try { event = JSON.parse(raw); } catch (_) { appendLog(raw); continue; }
            if (event.type === 'line') {
                appendLog(event.message);
                updateProgressFromLine(event.message);
            } else if (event.type === 'error') {
                ok = false;
                setError(event.message);
            } else if (event.type === 'done') {
                ok = Number(event.returncode) === 0;
                appendLog(ok ? `✅ Выполнено: ${title || command}` : `❌ Ошибка: ${title || command} exit ${event.returncode}`);
            }
        }
    }

    if (!ok) setError(`Ошибка: ${title || command}`);
    return ok;
}

function getSelectedDevice() {
    const select = document.getElementById('deviceSelect');
    return select ? (select.value || null) : null;
}

function getWorkspacePath() {
    const input = document.getElementById('workspacePath');
    return input ? input.value.trim() : '';
}

async function loadSystemStatus() {
    setStatus('Проверяю состояние DevConsole', 'running');
    await workspaceApi('/api/system/status', {}, 'GET');
    setStatus('DevConsole готов', 'done');
}

async function saveGitHubSettings() {
    const username = document.getElementById('githubUsername')?.value.trim() || '';
    const token = document.getElementById('githubToken')?.value.trim() || '';
    if (!username) { setError('Укажите GitHub login'); return; }
    if (!token) { setError('Укажите GitHub key'); return; }
    setBusy('Сохраняю GitHub доступ');
    const data = await workspaceApi('/api/settings/github', {username, token});
    if (data.success) {
        const tokenInput = document.getElementById('githubToken');
        if (tokenInput) tokenInput.value = '';
        setDone('GitHub доступ сохранён');
    } else setError('Не удалось сохранить GitHub доступ');
}

function renderGroupedRuntimeButtons() {
    const container = document.getElementById('runtimeButtons');
    if (!container) return;
    container.innerHTML = `
        <button onclick="runRuntimeScenario('check')">Проверить</button>
        <button onclick="runRuntimeScenario('run_profile')">Запустить</button>
        <button onclick="runRuntimeScenario('build')">Собрать APK</button>
        <button onclick="runRuntimeScenario('install')">Установить APK</button>
        <button onclick="runRuntimeScenario('diagnostics')">Диагностика</button>
    `;
}

async function loadRuntimeCommands() {
    renderGroupedRuntimeButtons();
    setStatus('Runtime сценарии готовы', 'done');
}

async function executeRuntimeCommand(command, title, progress = 50) {
    return await streamRuntimeCommand(command, title, progress);
}

async function runRuntimeScenario(scenario) {
    const workspace = getWorkspacePath();
    if (!workspace) { setError('Workspace не выбран'); return; }

    if (scenario === 'check') {
        setBusy('Проверка проекта');
        appendLog('=== Проверка проекта: git pull + flutter pub get ===');
        if (!await executeRuntimeCommand('git_pull', 'Git Pull', 25)) return;
        if (!await executeRuntimeCommand('flutter_pub_get', 'Flutter Pub Get', 70)) return;
        setDone('Проверка завершена');
        return;
    }

    if (scenario === 'run_profile') {
        if (!getSelectedDevice()) { setError('Устройство не выбрано'); return; }
        setBusy('Запуск на телефоне');
        appendLog('=== Запуск на телефоне в profile режиме ===');
        if (!await executeRuntimeCommand('flutter_pub_get', 'Подготовка зависимостей', 30)) return;
        if (!await executeRuntimeCommand('flutter_run_profile', 'Flutter Run --profile', 75)) return;
        setDone('Запуск завершён');
        return;
    }

    if (scenario === 'build') {
        setBusy('Сборка APK');
        appendLog('=== Сборка APK: clean + pub get + release build ===');
        if (!await executeRuntimeCommand('flutter_clean', 'Flutter Clean', 20)) return;
        if (!await executeRuntimeCommand('flutter_pub_get', 'Flutter Pub Get', 45)) return;
        if (!await executeRuntimeCommand('flutter_build_apk', 'Flutter Build APK', 80)) return;
        setDone('Сборка APK завершена');
        return;
    }

    if (scenario === 'install') {
        setBusy('Установка APK');
        appendLog('=== Установка последнего APK на устройство ===');
        await installLatestApk();
        return;
    }

    if (scenario === 'diagnostics') {
        setBusy('Диагностика Android runtime');
        appendLog('=== Диагностика Android runtime ===');
        if (!await executeRuntimeCommand('adb_reconnect', 'ADB Reconnect', 40)) return;
        if (!await executeRuntimeCommand('adb_logcat', 'ADB Logcat Snapshot', 80)) return;
        setDone('Диагностика завершена');
    }
}

async function installLatestApk() {
    const workspace = getWorkspacePath();
    setTaskProgress(40, 'Отправляю APK на устройство', true);
    const data = await workspaceApi('/api/runtime/install-latest-apk', {workspace, device: getSelectedDevice()});
    if (data.result?.stdout) appendLog(data.result.stdout);
    if (data.result?.stderr) appendLog(data.result.stderr);
    if (data.success) setDone('APK установлен'); else setError('Ошибка установки APK');
}

async function restartCurrentApp() {
    const workspace = getWorkspacePath();
    const packageName = document.getElementById('packageName').value;
    if (!packageName) { setError('Укажите package name'); return; }
    setBusy('Перезапускаю приложение');
    const data = await workspaceApi('/api/runtime/restart-app', {workspace, device: getSelectedDevice(), package_name: packageName});
    if (data.result?.stdout) appendLog(data.result.stdout);
    if (data.result?.stderr) appendLog(data.result.stderr);
    if (data.success) setDone('Приложение перезапущено'); else setError('Ошибка перезапуска приложения');
}

async function loadProjects() {
    const container = document.getElementById('projectsList');
    if (!container) return;
    setStatus('Загружаю список проектов', 'running');
    appendLog('Загрузка списка проектов');
    const data = await workspaceApi('/api/projects/list', {}, 'GET');
    const projects = data.projects || [];
    if (projects.length === 0) {
        container.innerHTML = 'Проекты отсутствуют';
        setStatus('Проекты отсутствуют', 'idle');
        return;
    }
    container.innerHTML = projects.map(project => `
        <div class="project-card" onclick="openProject('${project.workspace}', '${project.name || 'project'}')">
            <strong>${project.name}</strong><br>
            <small>${project.stack || 'unknown stack'}</small><br>
            <small>${project.workspace}</small>
        </div>
    `).join('');
    setStatus(`Проекты загружены: ${projects.length}`, 'done');
}

function openProject(workspace, name = 'project') {
    document.getElementById('workspacePath').value = workspace;
    appendLog(`Открытие проекта: ${workspace}`);
    setTaskProgress(100, `Проект выбран: ${name}`, false);
    setStatus(`Проект готов: ${name}`, 'done');
    appendLog(`✅ Workspace готов к runtime-командам: ${workspace}`);
}

async function registerCurrentProject(repoUrl, workspace, stack = 'unknown') {
    const name = repoUrl.split('/').pop().replace('.git', '');
    setTaskProgress(90, `Регистрирую проект: ${name}`, true);
    await workspaceApi('/api/projects/register', {name, repo_url: repoUrl, workspace, stack});
    appendLog(`Проект зарегистрирован: ${name}`);
    loadProjects();
}

function parseLegacyDevices(stdout) {
    return (stdout || '').split('\n').filter(line => line.includes('device') && !line.includes('List')).map(line => {
        const serial = line.split(/\s+/)[0];
        return {serial, title: serial, subtitle: 'ADB device', state: 'device'};
    });
}

async function loadDevices() {
    setStatus('Ищу Android устройства', 'running');
    appendLog('Обновление списка Android устройств');
    const data = await workspaceApi('/api/android/devices');
    const container = document.getElementById('devices');
    const select = document.getElementById('deviceSelect');
    if (!container || !select) return;
    const devices = Array.isArray(data.devices) && data.devices.length > 0 ? data.devices : parseLegacyDevices(data.stdout || '');
    if (devices.length === 0) {
        container.innerHTML = 'Устройства не подключены';
        select.innerHTML = '<option value="">Нет устройств</option>';
        setStatus('Android устройства не подключены', 'idle');
        return;
    }
    container.innerHTML = devices.map(device => `
        <div style="margin-bottom:8px;padding:10px;background:#1d2430;border-radius:8px;">
            <strong>📱 ${device.title || device.serial}</strong><br>
            <small>${device.subtitle || device.serial}</small>
        </div>
    `).join('');
    select.innerHTML = devices.map(device => `<option value="${device.serial}">${device.title || device.serial}</option>`).join('');
    setStatus(`Android устройства найдены: ${devices.length}`, 'done');
    appendLog(`✅ Android устройства обновлены: ${devices.map(device => device.title || device.serial).join(', ')}`);
}

window.addEventListener('load', () => {
    setStatus('Запуск DevConsole runtime', 'running');
    loadSystemStatus();
    loadDevices();
    loadProjects();
    loadRuntimeCommands();
    appendLog('DevConsole workspace runtime готов');
});
