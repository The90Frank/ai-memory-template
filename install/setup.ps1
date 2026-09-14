#Requires -Version 5.1
# Windows installer. The logic lives in setup.py: this only picks the interpreter.
$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

foreach ($py in @('python', 'python3', 'py')) {
    $cmd = Get-Command $py -ErrorAction SilentlyContinue
    if ($cmd) {
        & $cmd.Source (Join-Path $dir 'setup.py') @args
        exit $LASTEXITCODE
    }
}

Write-Error 'Python 3 not found in PATH.'
exit 1
