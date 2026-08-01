param(
    [int]$Port = 3000
)

$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
pnpm --dir (Join-Path $repositoryRoot "frontend") dev -- --port $Port
