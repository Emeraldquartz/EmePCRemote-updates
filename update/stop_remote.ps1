$procs = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and $_.CommandLine -like "*EmePCRemote.py*"
}
if (-not $procs) {
    Write-Host "Eme PC Remote is not running."
} else {
    foreach ($p in $procs) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped PID $($p.ProcessId)"
    }
}
Read-Host "Press Enter to close"
