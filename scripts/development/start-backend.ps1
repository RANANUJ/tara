param(
    [int]$Port = 8000
)

$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
python -m uvicorn tara_api.main:app --app-dir (Join-Path $repositoryRoot "backend\src") --host 127.0.0.1 --port $Port --reload
