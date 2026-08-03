@echo off
"%~dp0.venv\Scripts\python.exe" -m unittest discover -s "%~dp0tests"

