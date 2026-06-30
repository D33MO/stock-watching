@echo off
echo ====================================
echo   股票监控 - 打包脚本
echo ====================================
echo.

echo [2/3] 开始打包...
venv\Scripts\pyinstaller.exe --noconfirm --onefile --windowed ^
    --name "股票监控" ^
    --add-data "config.json;." ^
    --hidden-import akshare ^
    --hidden-import pyqtgraph ^
    --hidden-import PyQt6 ^
    --hidden-import PyQt6.QtWidgets ^
    --hidden-import PyQt6.QtGui ^
    --hidden-import PyQt6.QtCore ^
    main.py

if errorlevel 1 (
    echo 打包失败！
    pause
    exit /b 1
)

echo [3/3] 复制配置文件...
copy /Y config.json dist\config.json >nul

echo.
echo ====================================
echo   打包完成！
echo   输出目录: dist\
echo ====================================
echo.
pause
