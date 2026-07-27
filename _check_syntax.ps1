$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile('D:\cybersecudraft\init.ps1', [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count -eq 0) {
    Write-Output 'PS1 SYNTAX OK'
} else {
    $errors | ForEach-Object { Write-Output $_.Message }
}
