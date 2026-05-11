let currentBusyTask = null;

function appendLog(message) {
    const logs = document.getElementById('logs');

    if (!logs) {
        return;
    }

    const time = new Date().toLocaleTimeString();

    logs.innerText += `\n[${time}] ${message}`;
    logs.scrollTop = logs.scrollHeight;
}

function setStatus(message, state = 'idle') {
    const status = document.getElementById('runtimeStatus');
    const dot = document.getElementById('runtimeStatusDot');

    if (status) {
        status.innerText = message;
    }

    if (dot) {
        dot.className = `status-dot ${state}`;
    }
}

function setTaskProgress(percent, message, running = true) {
    const wrap = document.getElementById('taskProgressWrap');
    const bar = document.getElementById('taskProgressBar');
    const label = document.getElementById('taskProgressLabel');

    if (wrap) {
        wrap.style.display = 'block';
    }

    if (bar) {
        bar.style.width = `${percent}%`;
    }

    if (label) {
        label.innerText = `${percent}% — ${message}`;
    }

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
    if (label) {
        label.innerText = `Ошибка — ${message}`;
    }
    setStatus(message, 'error');
    appendLog(`❌ ${message}`);
}

async function workspaceApi(url, payload = {}, method = 'POST') {
    appendLog(`API запрос: ${url}`);

    const response = await fetch(url, {
        method,
        headers: {
            'Content-Type': 'application/json'
        },
        body: method === 'GET' ? undefined : JSON.stringify(payload)
    });

    const data = await response.json().catch(() => ({success: false, detail: 'Пустой ответ сервера'}));

    if (!response.ok) {
        appendLog(`Ошибка API ${response.status}: ${data.detail || 'unknown error'}`);
    }

    return data;
}

function getSelectedDevice() {
    const select = document.getElementById('deviceSelect');

    if (!select) {
        return null;
    }

    return select.value || null;
}

function getWorkspacePath() {
    const input = document.getElementById('workspacePath');
    return input ? input.value.trim() : '';
}

async function loadSystemStatus() {
    setStatus('Проверяю состояние DevConsole', 'running');
    const data = await workspaceApi('/api/system/status', {}, 'GET');
    const status = document.getElementById('githubStatus');
    const username = document.getElementById('githubUsername');

    if (status && username) {
        if (data.github?.username) {
            username.value = data.github.username;
        }

        status.innerText = data.github?.token_set
            ? `GitHub: ${data.github.username || 'user'} / доступ сохранён`
            : 'GitHub доступ не сохранён';
    }

    setStatus('DevConsole готов', 'done');
}

async function saveGitHubSettings() {
    const username = document.getElementById('githubUsername').value.trim();
    const token = document.getElementById('githubToken').value.trim();

    if (!username) {
        setError('Укажите GitHub username');
        return;
    }

    if (!token) {
        setError('Укажите GitHub credential');
        return;
    }

    setBusy('Сохраняю GitHub доступ');

    const data = await workspaceApi('/api/settings/github', {
        username,
        token
    });

    if (data.success) {
        document.getElementById('githubToken').value = '';
        await loadSystemStatus();
        setDone('GitHub доступ сохранён');
    } else {
        setError('Не удалось сохранить GitHub доступ');
    }
}

function renderGroupedRuntimeButtons() {
    const container = document.getElementById('runtimeButtons');

    if (!container) {
        return;
    }

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
    const workspace = getWorkspacePath();

    if (!workspace) {
        setError('Workspace не выбран');
        return false;
    }

    const taskTitle = title || command;
    setTaskProgress(progress, taskTitle, true);
    appendLog(`▶ ${taskTitle}`);

    const data = await workspaceApi('/api/runtime/command', {
        workspace,
        command,
        device: getSelectedDevice()
    });

    if (data.result?.stdout) {
        appendLog(data.result.stdout);
    }

    if (data.result?.stderr) {
        appendLog(data.result.stderr);
    }

    appendLog(data.success
        ? `✅ Выполнено: ${data.label || command}`
        : `❌ Ошибка: ${data.label || command}`
    );

    if (!data.success) {
        setError(`Ошибка: ${data.label || command}`);
    }

    return Boolean(data.success);
}

async function runRuntimeScenario(scenario) {
    const workspace = getWorkspacePath();

    if (!workspace) {
        setError('Workspace не выбран');
        return;
    }

    if (scenario === 'check') {
        setBusy('Проверка проекта');
        appendLog('=== Проверка проекта: git pull + flutter pub get ===');
        if (!await executeRuntimeCommand('git_pull', 'Git Pull', 25)) return;
        if (!await executeRuntimeCommand('flutter_pub_get', 'Flutter Pub Get', 70)) return;
        setDone('Проверка завершена');
        return;
    }

    if (scenario === 'run_profile') {
        if (!getSelectedDevice()) {
            setError('Устройство не выбрано');
            return;
        }
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

async function runRuntimeCommand(command) {
    await executeRuntimeCommand(command, command);
}

async function installLatestApk() {
    const workspace = getWorkspacePath();

    setTaskProgress(40, 'Отправляю APK на устройство', true);

    const data = await workspaceApi('/api/runtime/install-latest-apk', {
        workspace,
        device: getSelectedDevice()
    });

    if (data.result?.stdout) {
        appendLog(data.result.stdout);
    }

    if (data.result?.stderr) {
        appendLog(data.result.stderr);
    }

    if (data.success) {
        setDone('APK установлен');
    } else {
        setError('Ошибка установки APK');
    }
}

async function restartCurrentApp() {
    const workspace = getWorkspacePath();
    const packageName = document.getElementById('packageName').value;

    if (!packageName) {
        setError('Укажите package name');
        return;
    }

    setBusy('Перезапускаю приложение');

    const data = await workspaceApi('/api/runtime/restart-app', {
        workspace,
        device: getSelectedDevice(),
        package_name: packageName
    });

    if (data.result?.stdout) {
        appendLog(data.result.stdout);
    }

    if (data.result?.stderr) {
        appendLog(data.result.stderr);
    }

    if (data.success) {
        setDone('Приложение перезапущено');
    } else {
        setError('Ошибка перезапуска приложения');
    }
}

async function loadProjects() {
    const container = document.getElementById('projectsList');

    if (!container) {
        return;
    }

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

    await workspaceApi('/api/projects/register', {
        name,
        repo_url: repoUrl,
        workspace,
        stack
    });

    appendLog(`Проект зарегистрирован: ${name}`);

    loadProjects();
}

async function loadWorkspaceTree() {
    const workspace = getWorkspacePath();

    if (!workspace) {
        setError('Workspace path пустой');
        return;
    }

    setDone(`Workspace выбран: ${workspace}`);
}

async function loadDevices() {
    setStatus('Ищу Android устройства', 'running');
    appendLog('Обновление списка Android устройств');

    const data = await workspaceApi('/api/android/devices');

    const container = document.getElementById('devices');
    const select = document.getElementById('deviceSelect');

    if (!container || !select) {
        return;
    }

    const lines = (data.stdout || '').split('\n');

    const devices = lines.filter(line =>
        line.includes('device') && !line.includes('List')
    );

    if (devices.length === 0) {
        container.innerHTML = 'Устройства не подключены';
        select.innerHTML = '<option value="">Нет устройств</option>';
        setStatus('Android устройства не подключены', 'idle');
        return;
    }

    container.innerHTML = devices.map(device => {
        const id = device.split(/\s+/)[0];

        return `
            <div style="margin-bottom:8px;padding:8px;background:#1d2430;border-radius:8px;">
                📱 ${id}
            </div>
        `;
    }).join('');

    select.innerHTML = devices.map(device => {
        const id = device.split(/\s+/)[0];

        return `<option value="${id}">${id}</option>`;
    }).join('');

    setStatus(`Android устройства найдены: ${devices.length}`, 'done');
}

window.addEventListener('load', () => {
    setStatus('Запуск DevConsole runtime', 'running');
    loadSystemStatus();
    loadDevices();
    loadProjects();
    loadRuntimeCommands();
    appendLog('DevConsole workspace runtime готов');
});
