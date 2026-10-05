# Starts the full development stack, each part in its own PowerShell window:
#   backend (FastAPI :8000) -> machine (PLC simulator + kiosk API :8765) -> kiosk UI (:5173) -> admin UI (:5174)
# Usage (from the project root):  powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1

$root = Split-Path -Parent $PSScriptRoot

function Start-Part($title, $dir, $cmd) {
    Start-Process powershell -ArgumentList '-NoExit', '-Command', "`$Host.UI.RawUI.WindowTitle='$title'; Set-Location '$root\$dir'; $cmd"
}

Start-Part 'RVM backend :8000' 'backend' '.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload'
Start-Sleep -Seconds 3
Start-Part 'RVM machine :8765' 'machine' '.venv\Scripts\python -m rvm.main --config config\machine.dev.yaml'
Start-Part 'RVM kiosk UI :5173' 'kiosk' 'npm run dev'
Start-Part 'RVM admin UI :5174' 'admin' 'npm run dev'

Start-Sleep -Seconds 6
Start-Process 'http://localhost:5173'
Start-Process 'http://localhost:5174'
Write-Host 'Kiosk: http://localhost:5173   Admin: http://localhost:5174   API docs: http://127.0.0.1:8000/docs'
