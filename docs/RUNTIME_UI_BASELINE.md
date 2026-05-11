# DevConsole Runtime UI Baseline

This document fixes the current production UI baseline for DevConsole.

## Main rule

The root route `/` must render:

```text
frontend/runtime.html
```

The file below is legacy and must not be used as the main UI:

```text
frontend/index.html
```

## Why

`index.html` is the old editor-era interface. It contains legacy blocks that must not appear in the production runtime UI:

- manual file editor;
- GitHub settings panel in sidebar;
- old Android device dropdown;
- old combined logs.

`runtime.html` is the active production runtime interface:

- project cards;
- clickable Android device cards;
- selected device highlight;
- runtime scenarios;
- separated runtime log;
- separated system/activity log under devices;
- errors panel for AI;
- system status panel;
- project OTA settings modal.

## Backend routing requirement

`backend/main.py` must keep:

```python
@app.get('/')
async def root():
    return FileResponse(FRONTEND_DIR / 'runtime.html')
```

Optional runtime alias:

```python
@app.get('/runtime')
async def runtime_page():
    return FileResponse(FRONTEND_DIR / 'runtime.html')
```

## Development rule

Frontend changes must be additive and targeted.

Do not replace the whole `frontend/workspace.js` or `frontend/runtime.html` unless intentionally restoring from a known-good commit.

Known-good runtime UI reference chain:

```text
008eae9 — GitHub-only runtime UI
49a388c — system panel under log
4b2bd2b — Android device model cards
16a726c — separated system log under devices
ec268a5 — root route switched to runtime.html
```
