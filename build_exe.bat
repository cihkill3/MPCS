@echo off
REM MPCS single-file executable build (PyInstaller onefile)
REM Output: dist\MPCS.exe
REM Requires pyinstaller in .venv2: (.venv2\Scripts\python.exe -m pip install "pyinstaller==6.*")
REM
REM .venv2 is created on top of Anaconda Python. Anaconda keeps DLLs that extension
REM modules need (e.g. ffi.dll for _ctypes) in Library\bin, and PyInstaller does not
REM search there for a venv. Put that folder on PATH so the DLLs get bundled;
REM otherwise the exe fails at start with "DLL load failed while importing _ctypes".
setlocal
cd /d "%~dp0"
set QT_API=pyqt5

.\.venv2\Scripts\python.exe packaging\make_icon.py || goto :error

for /f "tokens=2 delims==" %%H in ('findstr /b /c:"home" .venv2\pyvenv.cfg') do set "PYHOME=%%H"
set "PYHOME=%PYHOME:~1%"
if exist "%PYHOME%\Library\bin" set "PATH=%PYHOME%\Library\bin;%PATH%"

.\.venv2\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name MPCS ^
  --icon "%~dp0packaging\mpcs.ico" ^
  --paths "%~dp0." ^
  --add-data "%~dp0mpcs\assets;mpcs\assets" ^
  --hidden-import molmass ^
  --hidden-import sympy ^
  --hidden-import qtpy ^
  --hidden-import pyqtgraph ^
  --hidden-import qtpy.QtSvg ^
  --exclude-module PySide6 ^
  --exclude-module PyQt6 ^
  --exclude-module tkinter ^
  --exclude-module IPython ^
  --exclude-module pytest ^
  --distpath dist ^
  --workpath build\pyi ^
  --specpath build ^
  main.py || goto :error

echo.
echo Build finished: dist\MPCS.exe
exit /b 0

:error
echo Build FAILED
exit /b 1
