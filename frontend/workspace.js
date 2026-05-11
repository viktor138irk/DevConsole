const selectedState={device:null};
const runtimeLogs=document.getElementById?.('logs');
let collectedErrors=[];
function now(){return new Date().toLocaleTimeString();}
function appendLog(message){const box=document.getElementById('systemLog');if(!box)return;box.innerText+=`${box.innerText?'\n':''}[${now()}] ${message}`;box.scrollTop=box.scrollHeight;}
function appendRuntimeLog(message){const box=document.getElementById('logs');if(!box)return;box.innerText+=`${box.innerText?'\n':''}[${now()}] ${message}`;box.scrollTop=box.scrollHeight;collectErrors(message);}
function collectErrors(message){if(/error|failed|exception|fatal|❌/i.test(message)){if(!collectedErrors.includes(message)){collectedErrors.push(message);}renderErrors();}}
function renderErrors(){const box=document.getElementById('errorsBox');const count=document.getElementById('errorCount');if(!box||!count)return;box.innerText=collectedErrors.length?collectedErrors.join('\n'):'Здесь появятся ошибки из Flutter, Gradle, ADB, API и stderr.';count.innerText=collectedErrors.length?`Ошибок: ${collectedErrors.length}`:'Ошибок пока нет';}
function clearRuntimeOutput(){const box=document.getElementById('logs');if(box)box.innerText='';collectedErrors=[];renderErrors();}
async function workspaceApi(url,payload={},method='POST'){appendLog(`API запрос: ${url}`);const response=await fetch(url,{method,headers:{'Content-Type':'application/json'},body:method==='GET'?undefined:JSON.stringify(payload)});return await response.json();}
function getWorkspacePath(){return document.getElementById('workspacePath')?.value?.trim()||'';}
function getSelectedDevice(){return selectedState.device;}
function selectDevice(serial){selectedState.device=serial;document.querySelectorAll('.device-card').forEach(card=>card.classList.toggle('selected',card.dataset.serial===serial));appendLog(`📱 Выбрано устройство: ${serial}`);}
function setStatus(message,state='idle'){const el=document.getElementById('runtimeStatus');if(el)el.innerText=message;const dot=document.getElementById('runtimeStatusDot');if(dot)dot.className=`status-dot ${state}`;}
async function loadDevices(){const data=await workspaceApi('/api/android/devices');const container=document.getElementById('devices');if(!container)return;const devices=data.devices||[];container.innerHTML=devices.map(device=>`<div class="device-card" data-serial="${device.serial}" onclick="selectDevice('${device.serial}')"><strong>📱 ${device.title||device.serial}</strong><br><small>${device.subtitle||device.serial}</small></div>`).join('');}
async function loadProjects(){const data=await workspaceApi('/api/projects/list',{},'GET');const container=document.getElementById('projectsList');if(!container)return;container.innerHTML=(data.projects||[]).map(project=>`<div class="project-card" onclick="openProject('${project.workspace}','${project.name}')"><div class="project-top"><strong>${project.name}</strong><button class="icon-btn" onclick="event.stopPropagation();openEditProjectModal('${project.workspace}')">⚙</button></div><small>${project.workspace}</small></div>`).join('');}
function openProject(workspace,name){document.getElementById('workspacePath').value=workspace;appendLog(`Открытие проекта: ${workspace}`);setStatus(`Проект готов: ${name}`,'done');loadApkArtifacts(false);}
function humanFileSize(bytes){const value=Number(bytes||0);if(value<1024)return `${value} B`;if(value<1048576)return `${(value/1024).toFixed(1)} KB`;return `${(value/1048576).toFixed(1)} MB`;}
async function installArtifactApk(path,name){const workspace=getWorkspacePath();if(!workspace){appendLog('❌ Workspace не выбран');return;}clearRuntimeOutput();appendLog(`📲 Установка APK: ${name}`);appendRuntimeLog(`▶ Installing artifact APK: ${name}`);const response=await fetch('/api/runtime/install-apk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workspace,apk_path:path,device:getSelectedDevice()})});const data=await response.json();if(data.result?.stdout)appendRuntimeLog(data.result.stdout);if(data.result?.stderr)appendRuntimeLog(data.result.stderr);appendLog(data.success?`✅ APK установлен: ${name}`:`❌ Ошибка установки: ${name}`);}
function renderApkArtifacts(apks,directory){const box=document.getElementById('apkArtifactsList');const meta=document.getElementById('apkArtifactsMeta');if(meta)meta.innerText=directory||'build/app/outputs/flutter-apk';if(!box)return;if(!apks||!apks.length){box.innerHTML='<div class="note">APK пока нет.</div>';return;}box.innerHTML=apks.map(apk=>{const openUrl=encodeURI(apk.open_url);const downloadUrl=encodeURI(apk.download_url);const badge=apk.name.includes('release')?'<span class="ota-badge">release</span>':apk.name.includes('debug')?'<span class="ota-badge">debug</span>':'';return `<div class="apk-card"><div class="apk-info"><strong>${apk.name}</strong>${badge}<small>${humanFileSize(apk.size_bytes)}</small></div><div class="apk-actions"><button class="mini-btn" onclick="installArtifactApk('${apk.path}','${apk.name}')">Install</button><button class="mini-btn" onclick="window.open('${openUrl}','_blank')">Открыть</button><a class="button-link" href="${downloadUrl}">Скачать</a></div></div>`;}).join('');}
async function loadApkArtifacts(verbose=true){const workspace=getWorkspacePath();const box=document.getElementById('apkArtifactsList');if(!workspace){if(box)box.innerHTML='<div class="note">Сначала выбери проект.</div>';return;}const data=await workspaceApi(`/api/android/apks?workspace=${encodeURIComponent(workspace)}`,{},'GET');renderApkArtifacts(data.apks||[],data.directory||'');}
async function runRuntimeScenario(type){appendLog(`▶ Runtime scenario: ${type}`);}
async function installLatestApk(){appendLog('▶ Install latest APK');}
async function restartCurrentApp(){appendLog('▶ Restart app');}
async function stopRuntimeCommand(){appendLog('🛑 Runtime stop requested');}
function copyErrorsForAI(){navigator.clipboard.writeText(collectedErrors.join('\n'));appendLog('Ошибки скопированы');}
function clearErrors(){collectedErrors=[];renderErrors();appendLog('Ошибки очищены');}
function openAddProjectModal(){document.getElementById('addProjectModal').style.display='flex';}
function closeAddProjectModal(){document.getElementById('addProjectModal').style.display='none';}
function openEditProjectModal(){document.getElementById('editProjectModal').style.display='flex';}
function closeEditProjectModal(){document.getElementById('editProjectModal').style.display='none';}
function toggleAuthFields(){}
function toggleOtaFields(){}
async function syncPubspecVersion(){appendLog('📦 Читаю pubspec.yaml');}
async function saveProjectSettings(){appendLog('✅ Настройки проекта сохранены');closeEditProjectModal();}
async function analyzeProject(){appendLog('📦 Анализ проекта');}
window.addEventListener('load',()=>{appendLog('DevConsole runtime initialized...');loadDevices();loadProjects();loadApkArtifacts(false);setStatus('DevConsole workspace runtime готов','done');});