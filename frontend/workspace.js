async function workspaceApi(url, payload = {}) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    });

    return await response.json();
}

async function loadWorkspaceTree() {
    const workspace = document.getElementById('workspacePath').value;

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
    const data = await workspaceApi('/api/files/read', {
        path
    });

    document.getElementById('editorPath').innerText = path;
    document.getElementById('editor').value = data.content || '';
}

async function saveCurrentFile() {
    const path = document.getElementById('editorPath').innerText;
    const content = document.getElementById('editor').value;

    const data = await workspaceApi('/api/files/save', {
        path,
        content
    });

    document.getElementById('editorStatus').innerText = data.success
        ? 'Файл сохранен'
        : 'Ошибка сохранения';
}
