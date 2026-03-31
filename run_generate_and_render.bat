@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=python"
set "BLENDER_EXE=%~1"
if "%BLENDER_EXE%"=="" set "BLENDER_EXE=blender"
set "BLENDER_MODE=%~2"
if /I "%BLENDER_MODE%"=="--background" (
  set "BLENDER_BG=--background"
) else (
  set "BLENDER_BG="
)

echo [Pipeline] Step1 -> Step2 -> Step3 -> Step4 -> Step5 -> RenderStep5
echo [Workdir] %CD%

echo [Run] Step1 network generation
%PYTHON_EXE% generate_step1_network.py --input step1_test_input.json --settings default_network.yaml --output step1_generated_scene.json
if errorlevel 1 goto :error

echo [Run] Step2 building generation
%PYTHON_EXE% generate_step2_building.py --input step1_generated_scene.json --output step2_generated_scene.json --typology default_building.yaml
if errorlevel 1 goto :error

echo [Run] Step3 key point generation
%PYTHON_EXE% generate_step3_keyPoint.py --input step2_generated_scene.json --output step3_generated_scene.json --typology default_keyPoint.yaml
if errorlevel 1 goto :error

echo [Run] Step4 pedestrian network generation
%PYTHON_EXE% generate_step4_pedestrian_network.py --input step3_generated_scene.json --output step4_generated_scene.json --typology default_pedestrian_network.yaml
if errorlevel 1 goto :error

echo [Run] Step5 pedestrian space generation
%PYTHON_EXE% generate_step5_pedestrian_space.py --input step4_generated_scene.json --output step5_generated_scene.json --typology defaults_pedestrian_space.yaml
if errorlevel 1 goto :error

echo [Run] Blender render preview for Step5
where "%BLENDER_EXE%" >nul 2>nul
if errorlevel 1 (
  echo [Warn] Blender not found in PATH as "%BLENDER_EXE%".
  echo [Hint] Re-run with blender full path:
  echo        run_generate_and_render.bat "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
  goto :done_no_blender
)

"%BLENDER_EXE%" %BLENDER_BG% --python render_step5_result.py -- step5_generated_scene.json
if errorlevel 1 goto :error

echo [Done] All steps finished.
goto :eof

:done_no_blender
echo [Done] Generation finished without Blender preview.
goto :eof

:error
echo [Error] Pipeline failed.
exit /b 1
