$taskName = "Daily_IEEE_EarlyAccess"
$batPath = Join-Path $PSScriptRoot "run_daily.bat"
$workDir = $PSScriptRoot

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "已删除旧任务: $taskName"
}

$action = New-ScheduledTaskAction -Execute $batPath -WorkingDirectory $workDir
$trigger = New-ScheduledTaskTrigger -Daily -At 8:00AM
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
# 用 SYSTEM 账户运行，无需用户交互登录即可触发；
# Edge 为系统级安装（Program Files），SYSTEM 可访问
$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "每日 08:00 抓取 IEEE Early Access 并推送中文总结到企业微信"

Write-Host "定时任务已注册: $taskName (每日 08:00，以 SYSTEM 身份运行，无需登录)"
Write-Host "启动脚本: $batPath"
Write-Host ""
Write-Host "管理命令:"
Write-Host '  查看状态: Get-ScheduledTask -TaskName ''Daily_IEEE_EarlyAccess'''
Write-Host '  立即触发: Start-ScheduledTask -TaskName ''Daily_IEEE_EarlyAccess'''
Write-Host '  删除任务: Unregister-ScheduledTask -TaskName ''Daily_IEEE_EarlyAccess'' -Confirm:$false'
