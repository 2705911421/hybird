@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "RUNTIME_DIR=%SCRIPT_DIR%.."
if not defined STORY_RUNTIME_DB set "STORY_RUNTIME_DB=%RUNTIME_DIR%\data\story.db"
python -X utf8 -m story_runtime --db "%STORY_RUNTIME_DB%" serve %*
