$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$vbs = Join-Path $base "start_hidden.vbs"
$startup = [Environment]::GetFolderPath("Startup")
$shortcut = Join-Path $startup "Eme PC Remote.lnk"

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($shortcut)
$sc.TargetPath = "$env:WINDIR\System32\wscript.exe"
$sc.Arguments = "`"$vbs`""
$sc.WorkingDirectory = $base
$sc.WindowStyle = 7
$sc.Description = "Eme PC Remote background startup"
$sc.Save()

Write-Host "Eme PC Remote startup registration completed."
Read-Host "Press Enter to close"
