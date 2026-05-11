function appendLog(message) {
    const logs = document.getElementById('logs');

    if (!logs) {
        return;
    }

    const time = new Date().toLocaleTimeString();

    logs.innerText += `\n[${time}] ${message}`;
    logs.scrollTop = logs.scrollHeight;
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
    const data = await workspaceApi('/api/system/status', {}, 'GET');
    const status = document.getElementById('githubStatus');
    const username = document.getElementById('githubUsername');

    if (!status || !username) {
        return;
    }

    if (data.github?.username) {
        username.value = data.github.username;
    }

    status.innerText = data.github?.token_set
        ? `GitHub: ${data.github.username || 'user'} / token сохранён`
        : 'GitHub token не сохранён';
}

async function saveGitHubSettings() {
    const username = document.getElementById('githubUsername').value.trim();
    const token = document.getElementById('githubToken').value.trim();

    if (!username) {
        appendLog('Укажите GitHub username');
        return;
    }

    if (!token) {
        appendLog('Укажите GitHub token');
        return;
    }

    const data = await workspaceApi('/api/settings/github', {
        username,
        token
    });

    if (data.success) {
        document.getElementById('githubToken').value = '';
        appendLog('GitHub доступ сохранён');
        await loadSystemStatus();
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
}

async function executeRuntimeCommand(command, title) {
    const workspace = getWorkspacePath();

    if (!workspace) {
        appendLog('Workspace не выбран');
        return false;
    }

    appendLog(`▶ ${title || command}`);

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

    return Boolean(data.success);
}

async function runRuntimeScenario(scenario) {
    const workspace = getWorkspacePath();

    if (!workspace) {
        appendLog('Workspace не выбран');
        return;
    }

    if (scenario === 'check') {
        appendLog('=== Проверка проекта: git pull + flutter pub get ===');
        if (!await executeRuntimeCommand('git_pull', 'Git Pull')) return;
        await executeRuntimeCommand('flutter_pub_get', 'Flutter Pub Get');
        appendLog('=== Проверка завершена ===');
        return;
    }

    if (scenario === 'run_profile') {
        appendLog('=== Запуск на телефоне в profile режиме ===');
        if (!getSelectedDevice()) {
            appendLog('Устройство не выбрано');
            return;
        }
        if (!await executeRuntimeCommand('flutter_pub_get', 'Подготовка зависимостей')) return;
        await executeRuntimeCommand('flutter_run_profile', 'Flutter Run --profile');
        appendLog('=== Запуск завершён ===');
        return;
    }

    if (scenario === 'build') {
        appendLog('=== Сборка APK: clean + pub get + release build ===');
        if (!await executeRuntimeCommand('flutter_clean', 'Flutter Clean')) return;
        if (!await executeRuntimeCommand('flutter_pub_get', 'Flutter Pub Get')) return;
        await executeRuntimeCommand('flutter_build_apk', 'Flutter Build APK');
        appendLog('=== Сборка завершена ===');
        return;
    }

    if (scenario === 'install') {
        appendLog('=== Установка последнего APK на устройство ===');
        await installLatestApk();
        appendLog('=== Установка завершена ===');
        return;
    }

    if (scenario === 'diagnostics') {
        appendLog('=== Диагностика Android runtime ===');
        await executeRuntimeCommand('adb_reconnect', 'ADB Reconnect');
        await executeRuntimeCommand('adb_logcat', 'ADB Logcat Snapshot');
        appendLog('=== Диагностика завершена ===');
    }
}

async function runRuntimeCommand(command) {
    await executeRuntimeCommand(command, command);
}

async function installLatestApk() {
    const workspace = getWorkspacePath();

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

    appendLog(data.success ? '✅ APK установлен' : '❌ Ошибка установки APK');
}

async function restartCurrentApp() {
    const workspace = getWorkspacePath();
    const packageName = document.getElementById('packageName').value;

    if (!packageName) {
        appendLog('Укажите package name');
        return;
    }

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
}

async function loadProjects() {
    const container = document.getElementById('projectsList');

    if (!container) {
        return;
    }

    appendLog('Загрузка списка проектов');

    const data = await workspaceApi('/api/projects/list', {}, 'GET');

    const projects = data.projects || [];

    if (projects.length === 0) {
        container.innerHTML = 'Проекты отсутствуют';
        return;
    }

    container.innerHTML = projects.map(project => `
        <div style="padding:10px;margin-bottom:10px;background:#1d2430;border-radius:10px;cursor:pointer" onclick="openProject('${project.workspace}')">
            <strong>${project.name}</strong><br>
            <small>${project.stack || 'unknown stack'}</small>
        </div>
    `).join('');
}

function openProject(workspace) {
    document.getElementById('workspacePath').value = workspace;

    appendLog(`Открытие проекта: ${workspace}`);

    loadWorkspaceTree();
}

async function registerCurrentProject(repoUrl, workspace, stack = 'unknown') {
    const name = repoUrl.split('/').pop().replace('.git', '');

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
        appendLog('Workspace path пустой');
        return;
    }

    appendLog(`Загрузка workspace: ${workspace}`);

    const data = await workspaceApi('/api/files/tree', {
        path: workspace
    });

    renderTree(data.tree || []);
}

function renderTree(tree, level = 0) {
    const container = document.getElementById('fileTree');

    if (level === 0) {
        container.innerHTML = '';
    }

    tree.forEach(node => {
        const item = document.createElement('div');

        item.className = 'tree-node';
        item.style.paddingLeft = `${level * 16}px`;

        if (node.type === 'directory') {
            item.innerHTML = `📁 ${node.name}`;
            container.appendChild(item);

            renderTree(node.children || [], level + 1);
        } else {
            item.innerHTML = `📄 ${node.name}`;
            item.onclick = () => openFile(node.path);
            container.appendChild(item);
        }
    });
}

async function openFile(path) {
    appendLog(`Открытие файла: ${path}`);

    const data = await workspaceApi('/api/files/read', {
        path
    });

    document.getElementById('editorPath').innerText = path;
    document.getElementById('editor').value = data.content || '';
}

async function saveCurrentFile() {
    const path = document.getElementById('editorPath').innerText;
    const content = document.getElementById('editor').value;

    appendLog(`Сохранение файла: ${path}`);

    const data = await workspaceApi('/api/files/save', {
        path,
        content
    });

    appendLog(data.success ? 'Файл успешно сохранен' : 'Ошибка сохранения файла');
}

async function loadDevices() {
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
}

window.addEventListener('load', () => {
    loadSystemStatus();
    loadDevices();
    loadProjects();
    loadRuntimeCommands();
    appendLog('DevConsole workspace runtime готов');
});
