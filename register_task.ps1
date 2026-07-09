$taskName = "Daily_IEEE_EarlyAccess"
$batPath = Join-Path $PSScriptRoot "run_daily.bat"
$workDir = $PSScriptRoot

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "已删除旧任务: $taskName"
}

$action = New-ScheduledTaskAction -Execute $batPath -WorkingDirectory $workDir
# 触发器：每日 08:00
#   - WakeToRun：到点主动唤醒系统（覆盖 S0 Modern Standby 低功耗空闲）
#   - StartWhenAvailable：唤醒失败/系统关机时，下次可用时补跑
$trigger = New-ScheduledTaskTrigger -Daily -At 8:00AM
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -WakeToRun `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

# 以当前用户身份运行，但用密码登录（无需活跃桌面会话即可触发）
# 避开 SYSTEM 账户下 Edge 在 Session 0 崩溃的问题（exitCode=1002）
$userId = "$env:USERDOMAIN\$env:USERNAME"
Write-Host "将以下列用户身份注册任务: $userId"
Write-Host "请输入该用户的 Windows 登录密码（输入时不可见，密码仅用于注册任务，不保存到文件）:"
$securePwd = Read-Host -AsSecureString
$plainPwd = [System.Net.NetworkCredential]::new("", $securePwd).Password

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -User $userId `
    -Password $plainPwd `
    -Description "每日 08:00 抓取 IEEE Early Access 并推送中文总结到企业微信"

Write-Host ""
Write-Host "定时任务已注册: $taskName"
Write-Host "  - 每日 08:00 触发（WakeToRun 主动唤醒系统；错过则由 StartWhenAvailable 补跑）"
Write-Host "  - 以 $userId 身份运行（带密码登录，无需活跃桌面会话）"
Write-Host "  - 启动脚本: $batPath"
Write-Host ""
Write-Host "建议（确保按时触发）:"
Write-Host "  插电过夜时将 AC 电源的睡眠超时设为从不，屏幕仍会自动关闭但不影响任务触发："
Write-Host "    powercfg /change standby-timeout-ac 0   # 需管理员权限"
