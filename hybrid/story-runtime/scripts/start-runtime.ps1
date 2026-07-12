$ErrorActionPreference = "Stop"
$runtimeDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $env:STORY_RUNTIME_DB) { $env:STORY_RUNTIME_DB = Join-Path $runtimeDir "data\story.db" }
python -X utf8 -m story_runtime --db $env:STORY_RUNTIME_DB serve @args
