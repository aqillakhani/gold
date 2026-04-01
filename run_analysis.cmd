@echo off
cd /d "C:\Users\claws\OneDrive\Desktop\gold"
C:\Python314\python.exe analyze_brightness_fast.py > brightness_report_final.txt 2>&1
echo Analysis complete!
pause
