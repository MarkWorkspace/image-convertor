@echo off

echo Проверка наличия Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не установлен или не добавлен в переменную окружения PATH!
    echo Пожалуйста, установите Python с сайта https://www.python.org/ и убедитесь,
    echo что при установке установлена галочка "Add python.exe to PATH".
    pause
    exit /b
)

echo Установка зависимостей...
pip install -r requirements.txt

echo.
echo Сборка приложения в .exe...
pyinstaller --noconsole --onefile --icon=icon.ico --add-data "icon.ico;." --hidden-import pillow_heif --name "convert-to-.webp" converter.py

echo.
echo Очистка временных файлов...
rmdir /s /q "build"
del /q "Converter to .webp.spec"

echo.
echo Сборка завершена! Исполняемый файл находится в папке dist.
pause