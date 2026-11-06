$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $Project 'run_garmin_sync.ps1'
$PowerShell = (Get-Command powershell.exe).Source
$Action = New-ScheduledTaskAction -Execute $PowerShell -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$Runner`"" -WorkingDirectory $Project
$Daily = New-ScheduledTaskTrigger -Daily -At '7:00AM'
$Logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 6) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Garmin Connect Local Export' -Description 'Daily export of Garmin Connect data to this user profile.' -Action $Action -Trigger @($Daily, $Logon) -Settings $Settings -Principal $Principal -Force | Out-Null
Write-Host 'Scheduled: daily at 07:00 and once when you sign in. It runs only while your Windows account is signed in.'

