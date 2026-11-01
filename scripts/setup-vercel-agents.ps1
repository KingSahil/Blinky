$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
# Isolated tools avoid the root package's Linux-only dependency on Windows.
& npm install --prefix (Join-Path $projectRoot 'data/agent-tools') --no-audit --no-fund agent-browser@0.41.0 agent-desktop@1.0.2
if ($LASTEXITCODE -ne 0) { throw 'Agent tool installation failed' }
& node (Join-Path $projectRoot 'data/agent-tools/node_modules/agent-browser/bin/agent-browser.js') --version
if ($LASTEXITCODE -ne 0) { throw 'agent-browser binary verification failed' }
& node (Join-Path $projectRoot 'data/agent-tools/node_modules/agent-desktop/bin/agent-desktop') status
if ($LASTEXITCODE -ne 0) { throw 'agent-desktop status check failed' }
