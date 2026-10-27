@echo off
setlocal
python "%~dp0app\frontend.py" %*
exit /b %errorlevel%
