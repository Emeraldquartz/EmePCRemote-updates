Option Explicit
Dim sh, fso, base, cmd
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)

cmd = "cmd /c cd /d """ & base & """ && " & _
      "(where pyw.exe >nul 2>&1 && pyw.exe -3 EmePCRemote.py) || " & _
      "(where pythonw.exe >nul 2>&1 && pythonw.exe EmePCRemote.py)"

sh.Run cmd, 0, False
