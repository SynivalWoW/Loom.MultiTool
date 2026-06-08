@echo off
for %%f in ("%~dp0*.m2") do "C:\WoTLK_MultiTool\Retroport\Python-3.14.2\python.exe" "C:\WoTLK_MultiTool\Retroport\m2_convert.py" "%%f"
