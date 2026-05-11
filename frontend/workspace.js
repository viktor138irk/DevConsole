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

    return await response.json();
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
    const name = repoUrl.split('/').pop();

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
    const workspace = document.getElementById('workspacePath').value;

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

    if (!container) {
        return;
    }

    const lines = (data.stdout || '').split('\n');

    const devices = lines.filter(line =>
        line.includes('device') && !line.includes('List')
    );

    if (devices.length === 0) {
        container.innerHTML = 'Устройства не подключены';
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
}

window.addEventListener('load', () => {
    loadDevices();
    loadProjects();
    appendLog('DevConsole workspace runtime готов');
});
