@echo off
echo ====================================
echo   股票监控 - 打包脚本
echo ====================================
echo.

echo [1/4] 安装/更新依赖...
venv\Scripts\pip.exe install -r requirements.txt -q
if errorlevel 1 (
    echo 依赖安装失败！
    pause
    exit /b 1
)

echo [2/4] 生成图标...
venv\Scripts\python.exe -c "from PIL import Image; img = Image.open('logo.png'); img.save('logo.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if errorlevel 1 (
    echo 图标生成失败！请确认已安装 Pillow
    pause
    exit /b 1
)

echo [3/4] 开始打包...
venv\Scripts\pyinstaller.exe --noconfirm --onefile --windowed ^
    --name "股票监控" ^
    --icon "logo.ico" ^
    --add-data "config.json;." ^
    --add-data "logo.ico;." ^
    --add-data "logo.png;." ^
    --add-data "assets/svg;assets/svg" ^
    --hidden-import akshare ^
    --collect-data akshare ^
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

echo [4/4] 复制配置文件...
copy /Y config.json dist\config.json >nul
copy /Y logo.ico dist\logo.ico >nul
copy /Y logo.png dist\logo.png >nul
if not exist dist\assets\svg mkdir dist\assets\svg
copy /Y assets\svg\*.svg dist\assets\svg\ >nul

echo.
echo ====================================
echo   打包完成！
echo   输出目录: dist\
echo ====================================
echo.
pause
