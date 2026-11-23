#Requires -Version 5.1
<#
.SYNOPSIS
    Installs AbletonMCP on Windows: the Python MCP/REST server, the Ableton remote
    script, and the Max for Live device.

.DESCRIPTION
    Installs AbletonMCP for the current user:

      * an isolated Python environment (uv when available, otherwise an existing
        Python 3.10+) with the MCP server and REST API installed
      * the remote script -> <Live User Library>\Remote Scripts\AbletonMCP (the library path
        is read from Live's preferences, falling back to <Documents>\Ableton)
      * the Max for Live device, built from AbletonMCP_M4L\AbletonMCP.amxd.maxpat,
        -> <Documents>\Ableton\User Library\Presets\Audio Effects\Max Audio Effect\AbletonMCP
      * launchers, Start Menu shortcuts and an entry in Settings > Apps

    The newest installed Ableton Live version is detected and reported. The remote
    script is installed for every Live version that uses the User Library (Live 10+).

.PARAMETER InstallDir
    Where the Python environment and launchers live. Default: %LOCALAPPDATA%\AbletonMCP

.PARAMETER Uninstall
    Remove everything this installer created.

.PARAMETER DryRun
    Report every action without changing anything.

.PARAMETER SystemWide
    Also copy the remote script into Ableton's own MIDI Remote Scripts folder for the
    newest installed Live version. Requires an elevated shell.

.PARAMETER ConfigureClaude
    Add an "AbletonMCP" server entry to Claude Desktop's claude_desktop_config.json
    (the existing file is backed up first).

.PARAMETER SkipPython
    Only install the remote script and the Max for Live device.

.PARAMETER NoM4LDevice
    Skip the Max for Live device.

.PARAMETER NoRegistry
    Do not create the Settings > Apps (uninstall) entry.

.EXAMPLE
    .\AbletonMCP-Setup.ps1 -DryRun

.EXAMPLE
    .\AbletonMCP-Setup.ps1 -ConfigureClaude

.EXAMPLE
    .\AbletonMCP-Setup.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'AbletonMCP'),
    [switch]$Uninstall,
    [switch]$DryRun,
    [switch]$SystemWide,
    [switch]$ConfigureClaude,
    [switch]$SkipPython,
    [switch]$NoM4LDevice,
    [switch]$NoRegistry
)

$ErrorActionPreference = 'Stop'

$script:DryRun = [bool]$DryRun
$script:InstallDir = $InstallDir
$script:LogPath = $null
$script:RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $script:RepoRoot -or -not (Test-Path -LiteralPath (Join-Path $script:RepoRoot 'pyproject.toml'))) {
    $script:RepoRoot = $null
}

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------

function Add-Log {
    param(
        [string]$Message,
        [ValidateSet('INFO', 'STEP', 'OK', 'WARN', 'ERROR')]
        [string]$Level = 'INFO'
    )
    $line = '{0} [{1,-5}] {2}' -f (Get-Date -Format 'HH:mm:ss'), $Level, $Message
    $color = switch ($Level) {
        'STEP' { 'Cyan' }
        'OK' { 'Green' }
        'WARN' { 'Yellow' }
        'ERROR' { 'Red' }
        default { 'Gray' }
    }
    Write-Host $line -ForegroundColor $color
    if ($script:LogPath) {
        try { Add-Content -LiteralPath $script:LogPath -Value $line -Encoding UTF8 } catch { }
    }
}

function Step { param([string]$Text) Add-Log $Text 'STEP' }
function Info { param([string]$Text) Add-Log $Text 'INFO' }
function Ok { param([string]$Text) Add-Log $Text 'OK' }
function Warn { param([string]$Text) Add-Log $Text 'WARN' }
function Fail { param([string]$Text) Add-Log $Text 'ERROR' }

# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-UserDocuments {
    $documents = [Environment]::GetFolderPath('MyDocuments')
    if ([string]::IsNullOrWhiteSpace($documents)) {
        $documents = Join-Path $env:USERPROFILE 'Documents'
    }
    return $documents
}

function Get-UserLibrary {
    # Live may keep its User Library anywhere; <Documents>\Ableton is only the default.
    # The real location is recorded in Library.cfg, and Live never scans any other path.
    $default = Join-Path (Get-UserDocuments) 'Ableton\User Library'
    $prefRoot = Join-Path $env:APPDATA 'Ableton'
    if (-not (Test-Path -LiteralPath $prefRoot)) { return $default }

    $candidates = @()
    foreach ($dir in (Get-ChildItem -LiteralPath $prefRoot -Directory -ErrorAction SilentlyContinue)) {
        if ($dir.Name -notmatch '^Live\s+(\d+(?:\.\d+)*)$') { continue }
        $candidates += [pscustomobject]@{
            Version = [version]$Matches[1]
            Config = (Join-Path (Join-Path $dir.FullName 'Preferences') 'Library.cfg')
        }
    }

    foreach ($candidate in ($candidates | Sort-Object -Property Version -Descending)) {
        if (-not (Test-Path -LiteralPath $candidate.Config)) { continue }
        try {
            $raw = (Get-Content -LiteralPath $candidate.Config -Raw) -replace '^\uFEFF', ''
            $xml = [xml]$raw
            $node = $xml.SelectSingleNode('/Ableton/ContentLibrary/UserLibrary/LibraryProject/ProjectPath')
            if (-not $node -or [string]::IsNullOrWhiteSpace($node.Value)) { continue }
            $library = Join-Path ($node.Value.Replace('/', '\')) 'User Library'
            if (Test-Path -LiteralPath $library) {
                if ($library -ne $default) { Info "Live's User Library is $library (not $default)" }
                return $library
            }
            Warn "Live's configured User Library does not exist: $library; using $default"
        }
        catch {
            Info "could not read $($candidate.Config): $($_.Exception.Message)"
        }
    }
    return $default
}

function Ensure-Directory {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) { return }
    if ($script:DryRun) {
        Info "would create directory $Path"
        return
    }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    Info "created directory $Path"
}

function Remove-PathQuiet {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        Info "not present: $Path"
        return
    }
    if ($script:DryRun) {
        Info "would remove $Path"
        return
    }
    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $Path) {
        Warn "could not fully remove $Path"
    }
    else {
        Ok "removed $Path"
    }
}

function Invoke-Native {
    param(
        [string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory
    )
    Info ('> {0} {1}' -f $FilePath, ($Arguments -join ' '))
    if ($script:DryRun) { return 0 }
    if (-not $WorkingDirectory) { $WorkingDirectory = (Get-Location).Path }
    # Tools such as uv write progress to stderr; keep those lines from turning into
    # terminating NativeCommandError exceptions under $ErrorActionPreference = 'Stop'.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $FilePath @Arguments 2>&1 | ForEach-Object { if ("$_".Trim()) { Info ("  " + "$_".TrimEnd()) } }
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
        $ErrorActionPreference = $previousPreference
    }
    return $exitCode
}

function New-Shortcut {
    param(
        [string]$Path,
        [string]$Target,
        [string]$Arguments = '',
        [string]$WorkingDirectory = '',
        [string]$Description = ''
    )
    if ($script:DryRun) {
        Info "would create shortcut $Path"
        return
    }
    $shell = New-Object -ComObject WScript.Shell
    try {
        $link = $shell.CreateShortcut($Path)
        $link.TargetPath = $Target
        if ($Arguments) { $link.Arguments = $Arguments }
        if ($WorkingDirectory) { $link.WorkingDirectory = $WorkingDirectory }
        if ($Description) { $link.Description = $Description }
        $link.Save()
    }
    finally {
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
    }
    Info "created shortcut $Path"
}

# ----------------------------------------------------------------------------
# Ableton Live detection
# ----------------------------------------------------------------------------

function Get-LiveVersionFromExe {
    param([string]$Directory)
    $program = Join-Path $Directory 'Program'
    if (-not (Test-Path -LiteralPath $program)) { return $null }
    foreach ($exe in (Get-ChildItem -LiteralPath $program -Filter 'Live*.exe' -File -ErrorAction SilentlyContinue)) {
        try { $info = (Get-Item -LiteralPath $exe.FullName).VersionInfo } catch { continue }
        foreach ($candidate in @($info.ProductVersion, $info.FileVersion)) {
            if ($candidate -and $candidate -match '^(\d+(?:\.\d+)+)') {
                try { return [version]$Matches[1] } catch { }
            }
        }
    }
    return $null
}

function Get-AbletonInstalls {
    # Only a tree that ships Live's own MIDI Remote Scripts is an installation. The
    # %APPDATA%\Ableton\Live X folders also match "Live *" but are preference folders:
    # they hold Library.cfg (read by Get-UserLibrary) and no application to copy into.
    $roots = @()
    if ($env:PROGRAMDATA) { $roots += (Join-Path $env:PROGRAMDATA 'Ableton') }
    if ($env:APPDATA) { $roots += (Join-Path $env:APPDATA 'Ableton') }

    $installs = @()
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        foreach ($dir in (Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue)) {
            if ($dir.Name -notmatch '^Live') { continue }
            if (-not (Test-Path -LiteralPath (Join-Path $dir.FullName 'Resources\MIDI Remote Scripts'))) { continue }

            $version = Get-LiveVersionFromExe -Directory $dir.FullName
            if (-not $version -and $dir.Name -match '^Live\s+(\d+(?:\.\d+)+)') {
                try { $version = [version]$Matches[1] } catch { }
            }
            if (-not $version -and $dir.Name -match '(\d+)') {
                try { $version = [version]($Matches[1] + '.0') } catch { }
            }
            if (-not $version) { $version = [version]'0.0' }

            $installs += [pscustomobject]@{
                Name = $dir.Name
                Version = $version
                Path = $dir.FullName
                Root = $root
                # "<name>_updated" is an update Live stages and swaps in on restart.
                Staging = [bool]($dir.Name -match '_updated$')
            }
        }
    }
    return @($installs | Sort-Object -Property @{ Expression = 'Version'; Descending = $true }, @{ Expression = 'Staging'; Descending = $false })
}

# ----------------------------------------------------------------------------
# Python discovery / environment
# ----------------------------------------------------------------------------

function Find-Command {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    return $null
}

function Find-SupportedPython {
    $candidates = @(
        @{ Exe = 'py'; Prefix = @('-3.13', '-3') },
        @{ Exe = 'python'; Prefix = @() },
        @{ Exe = 'python3'; Prefix = @() }
    )
    foreach ($candidate in $candidates) {
        $exe = Find-Command $candidate.Exe
        if (-not $exe) { continue }
        $prefixList = @()
        if ($candidate.Prefix.Count -gt 0) { $prefixList = @($candidate.Prefix[0]) }
        try {
            $probeArgs = $prefixList + @('-c', 'import sys; print("%d.%d" % sys.version_info[:2])')
            $output = & $exe @probeArgs 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $output) { continue }
            $version = [version]($output.ToString().Trim() + '.0')
            if ($version -ge [version]'3.10.0') {
                return @{ Exe = $exe; Prefix = $prefixList; Version = $output.ToString().Trim() }
            }
            Info "ignoring $exe $($output.ToString().Trim()) (AbletonMCP needs Python 3.10+)"
        }
        catch {
            continue
        }
    }
    return $null
}

function Find-AnyPython {
    foreach ($name in @('python', 'py', 'python3')) {
        $exe = Find-Command $name
        if ($exe) { return @{ Exe = $exe; Prefix = @() } }
    }
    return $null
}

function Install-PythonEnvironment {
    param([string]$VenvDir)

    $uv = Find-Command 'uv'
    $venvPython = Join-Path $VenvDir 'Scripts\python.exe'

    if (Test-Path -LiteralPath $venvPython) {
        Info "reusing the existing environment at $VenvDir"
    }
    else {
        if (Test-Path -LiteralPath $VenvDir) {
            Warn "removing an incomplete environment at $VenvDir"
            Remove-PathQuiet -Path $VenvDir
        }
        if ($uv) {
            Info "using uv ($uv) with Python 3.13"
            $code = Invoke-Native -FilePath $uv -Arguments @('venv', '--python', '3.13', $VenvDir)
            if ($code -ne 0) { throw "uv venv failed with exit code $code" }
        }
        else {
            $python = Find-SupportedPython
            if (-not $python) {
                throw 'No Python 3.10+ found. Install uv (https://astral.sh/uv) or Python 3.10+ and run again.'
            }
            Info "using Python $($python.Version) at $($python.Exe)"
            $code = Invoke-Native -FilePath $python.Exe -Arguments (@($python.Prefix) + @('-m', 'venv', $VenvDir))
            if ($code -ne 0) { throw "python -m venv failed with exit code $code" }
        }

        if ($script:DryRun) { return $venvPython }
        if (-not (Test-Path -LiteralPath $venvPython)) {
            throw "Virtual environment interpreter not found: $venvPython"
        }
    }

    $spec = "$($script:RepoRoot)[rest]"
    if ($uv) {
        $code = Invoke-Native -FilePath $uv -Arguments @('pip', 'install', '--python', $venvPython, $spec)
    }
    else {
        $code = Invoke-Native -FilePath $venvPython -Arguments @('-m', 'pip', 'install', '--disable-pip-version-check', $spec)
    }
    if ($code -ne 0) { throw "installing the ableton-mcp package failed with exit code $code" }

    $code = Invoke-Native -FilePath $venvPython -Arguments @('-c', 'import MCP_Server.server, MCP_Server.rest_api_server')
    if ($code -ne 0) { throw 'The installed server failed its import check' }
    return $venvPython
}

# ----------------------------------------------------------------------------
# Claude Desktop configuration
# ----------------------------------------------------------------------------

function Set-ClaudeDesktopConfig {
    param([string]$VenvPython, [string]$RestLauncher)

    $claudeDir = Join-Path $env:APPDATA 'Claude'
    if (-not (Test-Path -LiteralPath $claudeDir)) {
        Warn 'Claude Desktop does not appear to be installed (no %APPDATA%\Claude); skipping its config'
        return $null
    }
    $configPath = Join-Path $claudeDir 'claude_desktop_config.json'

    if ($script:DryRun) {
        Info "would add an AbletonMCP server entry to $configPath"
        return $configPath
    }

    $config = [pscustomobject]@{}
    if (Test-Path -LiteralPath $configPath) {
        $backup = '{0}.bak-{1}' -f $configPath, (Get-Date -Format 'yyyyMMddHHmmss')
        Copy-Item -LiteralPath $configPath -Destination $backup -Force
        Info "backed up existing Claude config to $backup"
        $raw = Get-Content -LiteralPath $configPath -Raw
        if ($raw -and $raw.Trim()) {
            $config = $raw | ConvertFrom-Json
        }
    }
    if (-not ($config.PSObject.Properties.Name -contains 'mcpServers') -or -not $config.mcpServers) {
        $config | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) -Force
    }
    $server = [pscustomobject]@{ command = $VenvPython; args = @('-m', 'MCP_Server.server') }
    $config.mcpServers | Add-Member -NotePropertyName AbletonMCP -NotePropertyValue $server -Force
    $config | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $configPath -Encoding UTF8
    Ok "added the AbletonMCP server to $configPath"
    return $configPath
}

function Remove-ClaudeDesktopConfig {
    $configPath = Join-Path (Join-Path $env:APPDATA 'Claude') 'claude_desktop_config.json'
    if (-not (Test-Path -LiteralPath $configPath)) { return }
    if ($script:DryRun) {
        Info "would remove the AbletonMCP entry from $configPath"
        return
    }
    try {
        $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
        if ($config.PSObject.Properties.Name -contains 'mcpServers' -and $config.mcpServers) {
            if ($config.mcpServers.PSObject.Properties.Name -contains 'AbletonMCP') {
                $config.mcpServers.PSObject.Properties.Remove('AbletonMCP')
                $config | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $configPath -Encoding UTF8
                Ok "removed the AbletonMCP entry from $configPath"
            }
        }
    }
    catch {
        Warn "could not update $configPath : $($_.Exception.Message)"
    }
}

# ----------------------------------------------------------------------------
# Add/Remove Programs entry
# ----------------------------------------------------------------------------

function Register-UninstallEntry {
    param([string]$SetupScriptPath)
    if ($NoRegistry) {
        Info 'skipping the Settings > Apps entry (-NoRegistry)'
        return
    }
    if ($script:DryRun) {
        Info 'would register an uninstall entry under HKCU'
        return
    }
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AbletonMCP'
    New-Item -Path $key -Force | Out-Null
    $values = @{
        DisplayName = 'AbletonMCP'
        DisplayVersion = '2.0.0'
        Publisher = 'AbletonMCP'
        DisplayIcon = 'powershell.exe'
        InstallLocation = $script:InstallDir
        UninstallString = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -Uninstall' -f $SetupScriptPath
        QuietUninstallString = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -Uninstall' -f $SetupScriptPath
        NoModify = 1
        NoRepair = 1
    }
    foreach ($name in $values.Keys) {
        New-ItemProperty -Path $key -Name $name -Value $values[$name] -PropertyType String -Force | Out-Null
    }
    Ok 'registered AbletonMCP in Settings > Apps'
}

function Unregister-UninstallEntry {
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AbletonMCP'
    if (-not (Test-Path -LiteralPath $key)) { return }
    if ($script:DryRun) {
        Info 'would remove the Settings > Apps entry'
        return
    }
    Remove-Item -LiteralPath $key -Recurse -Force -ErrorAction SilentlyContinue
    Ok 'removed the Settings > Apps entry'
}

# ----------------------------------------------------------------------------
# Install
# ----------------------------------------------------------------------------

function Install-Main {
    if (-not $script:RepoRoot) {
        throw 'AbletonMCP-Setup.ps1 must be run from a copy of the ableton-mcp repository (pyproject.toml not found).'
    }

    $documents = Get-UserDocuments
    $userLibrary = Get-UserLibrary
    $remoteScriptRoot = Join-Path $userLibrary 'Remote Scripts'
    $remoteScriptDir = Join-Path $remoteScriptRoot 'AbletonMCP'
    $m4lPresetRoot = Join-Path $userLibrary 'Presets\Audio Effects\Max Audio Effect'
    $m4lDeviceDir = Join-Path $m4lPresetRoot 'AbletonMCP'
    $startMenuRoot = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
    $startMenuDir = Join-Path $startMenuRoot 'AbletonMCP'

    Step 'AbletonMCP installer'
    Info "repository : $($script:RepoRoot)"
    Info "install dir: $($script:InstallDir)"
    Info "documents  : $documents"
    Info "user lib   : $userLibrary"
    if ($script:DryRun) { Warn 'dry run - nothing will be changed' }

    # -- Ableton Live ---------------------------------------------------------
    Step 'Detecting Ableton Live'
    $installs = Get-AbletonInstalls
    $latest = $null
    if ($installs.Count -gt 0) {
        foreach ($install in $installs) {
            Info ("found {0} ({1})" -f $install.Name, $install.Path)
        }
        $latest = $installs[0]
        Ok "maximum installed Live version: $($latest.Name)"
    }
    else {
        Warn 'no Ableton Live installation found; installing for the user library anyway'
    }

    # -- Python environment ---------------------------------------------------
    $venvDir = Join-Path $script:InstallDir 'venv'
    $venvPython = Join-Path $venvDir 'Scripts\python.exe'
    $binDir = Join-Path $script:InstallDir 'bin'

    if ($SkipPython) {
        Warn 'skipping the Python server environment (-SkipPython)'
    }
    else {
        Step 'Installing the Python MCP / REST server'
        Ensure-Directory $script:InstallDir
        Ensure-Directory $binDir
        $venvPython = Install-PythonEnvironment -VenvDir $venvDir
        Ok "server environment ready: $venvPython"

        if (-not $script:DryRun) {
            $launchServer = @(
                '@echo off',
                'setlocal',
                ('"{0}" -m MCP_Server.server %*' -f $venvPython)
            )
            $launchRest = @(
                '@echo off',
                'setlocal',
                ('"{0}" -m MCP_Server.rest_api_server %*' -f $venvPython)
            )
            Set-Content -LiteralPath (Join-Path $binDir 'ableton-mcp.cmd') -Value $launchServer -Encoding ASCII
            Set-Content -LiteralPath (Join-Path $binDir 'ableton-mcp-rest.cmd') -Value $launchRest -Encoding ASCII
            Ok "wrote launchers to $binDir"
        }
    }

    # -- Remote script --------------------------------------------------------
    Step 'Installing the Ableton remote script'
    $remoteSourceDir = Join-Path $script:RepoRoot 'AbletonMCP_Remote_Script'
    $remoteSources = @(Get-ChildItem -LiteralPath $remoteSourceDir -Filter '*.py' -File)
    if (-not $remoteSources) {
        throw "Remote script source not found: $remoteSourceDir"
    }
    Ensure-Directory $remoteScriptDir
    foreach ($source in $remoteSources) {
        $destination = Join-Path $remoteScriptDir $source.Name
        if ($script:DryRun) {
            Info "would copy $($source.FullName) -> $destination"
        }
        else {
            Copy-Item -LiteralPath $source.FullName -Destination $destination -Force
        }
    }
    if (-not $script:DryRun) {
        Ok "remote script installed: $remoteScriptDir"
    }

    if ($SystemWide) {
        if ($latest -and (Test-Admin)) {
            $systemDir = Join-Path $latest.Path 'Resources\MIDI Remote Scripts\AbletonMCP'
            Ensure-Directory $systemDir
            if (-not $script:DryRun) {
                foreach ($source in $remoteSources) {
                    Copy-Item -LiteralPath $source.FullName -Destination (Join-Path $systemDir $source.Name) -Force
                }
                Ok "remote script installed system-wide: $systemDir"
            }
        }
        else {
            Warn '-SystemWide needs an elevated shell and a detected Live installation; skipped'
        }
    }

    # -- Max for Live device --------------------------------------------------
    if ($NoM4LDevice) {
        Warn 'skipping the Max for Live device (-NoM4LDevice)'
    }
    else {
        Step 'Building and installing the Max for Live device'
        $buildScript = Join-Path $script:RepoRoot 'scripts\build_amxd.py'
        $maxpat = Join-Path $script:RepoRoot 'AbletonMCP_M4L\AbletonMCP.amxd.maxpat'
        $builtAmxd = Join-Path $script:RepoRoot 'AbletonMCP_M4L\AbletonMCP.amxd'

        $buildPython = $null
        if ($venvPython -and (Test-Path -LiteralPath $venvPython)) { $buildPython = $venvPython }
        else {
            $anyPython = Find-AnyPython
            if ($anyPython) { $buildPython = $anyPython.Exe }
        }

        if (-not (Test-Path -LiteralPath $buildScript)) {
            Warn "device builder not found: $buildScript; skipping the Max for Live device"
        }
        elseif (-not $buildPython) {
            Warn 'no Python interpreter available to build the device; skipping the Max for Live device'
        }
        else {
            $code = Invoke-Native -FilePath $buildPython -Arguments @($buildScript, $maxpat, '-o', $builtAmxd, '--verify') -WorkingDirectory $script:RepoRoot
            if ($code -ne 0 -or (-not $script:DryRun -and -not (Test-Path -LiteralPath $builtAmxd))) {
                Warn 'the Max for Live device could not be built; skipping it'
            }
            else {
                Ensure-Directory $m4lDeviceDir
                Ensure-Directory (Join-Path $m4lDeviceDir 'code')
                if ($script:DryRun) {
                    Info "would copy $builtAmxd -> $m4lDeviceDir\AbletonMCP.amxd"
                    Info "would copy code\main.js -> $m4lDeviceDir\code\main.js"
                }
                else {
                    Copy-Item -LiteralPath $builtAmxd -Destination (Join-Path $m4lDeviceDir 'AbletonMCP.amxd') -Force
                    Copy-Item -LiteralPath (Join-Path $script:RepoRoot 'AbletonMCP_M4L\code\main.js') -Destination (Join-Path $m4lDeviceDir 'code\main.js') -Force
                    Ok "Max for Live device installed: $m4lDeviceDir"
                }
            }
        }
    }

    # -- Shortcuts, uninstall entry, state ------------------------------------
    Step 'Creating shortcuts and uninstall entry'
    Ensure-Directory $startMenuDir
    $setupCopy = Join-Path $script:InstallDir 'AbletonMCP-Setup.ps1'
    if (-not $script:DryRun -and (Test-Path -LiteralPath $PSCommandPath)) {
        Copy-Item -LiteralPath $PSCommandPath -Destination $setupCopy -Force
        $uninstallCmd = @(
            '@echo off',
            'setlocal',
            ('powershell -NoProfile -ExecutionPolicy Bypass -File "{0}" -Uninstall' -f $setupCopy),
            'pause'
        )
        Set-Content -LiteralPath (Join-Path $binDir 'uninstall.cmd') -Value $uninstallCmd -Encoding ASCII
    }

    if (-not $SkipPython) {
        New-Shortcut -Path (Join-Path $startMenuDir 'AbletonMCP REST API.lnk') `
            -Target (Join-Path $binDir 'ableton-mcp-rest.cmd') -WorkingDirectory $binDir `
            -Description 'Start the AbletonMCP REST API on http://127.0.0.1:8000'
        New-Shortcut -Path (Join-Path $startMenuDir 'AbletonMCP MCP Server.lnk') `
            -Target (Join-Path $binDir 'ableton-mcp.cmd') -WorkingDirectory $binDir `
            -Description 'Run the AbletonMCP MCP server (stdio)'
    }
    New-Shortcut -Path (Join-Path $startMenuDir 'Uninstall AbletonMCP.lnk') `
        -Target (Join-Path $binDir 'uninstall.cmd') -WorkingDirectory $binDir `
        -Description 'Remove AbletonMCP'

    Register-UninstallEntry -SetupScriptPath (Join-Path $script:InstallDir 'AbletonMCP-Setup.ps1')

    $claudeConfig = $null
    if ($ConfigureClaude) {
        Step 'Configuring Claude Desktop'
        $claudeConfig = Set-ClaudeDesktopConfig -VenvPython $venvPython -RestLauncher (Join-Path $binDir 'ableton-mcp-rest.cmd')
    }

    if (-not $script:DryRun) {
        $state = [ordered]@{
            Name = 'AbletonMCP'
            Version = '2.0.0'
            InstalledAt = (Get-Date).ToString('o')
            InstallDir = $script:InstallDir
            VenvPython = $venvPython
            RemoteScriptDir = $remoteScriptDir
            M4LDeviceDir = $m4lDeviceDir
            StartMenuDir = $startMenuDir
            ClaudeConfig = $claudeConfig
            ConfiguredClaude = [bool]$ConfigureClaude
            LatestLiveVersion = if ($latest) { $latest.Name } else { $null }
        }
        $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $script:InstallDir 'install-state.json') -Encoding UTF8
        Ok "wrote install state to $($script:InstallDir)\install-state.json"
    }

    # -- Summary --------------------------------------------------------------
    Step 'Done'
    if ($latest) {
        Ok "targeted Live versions: this and any other version using the User Library (newest: $($latest.Name))"
    }
    Info ''
    Info 'Next steps:'
    Info '  1. Start Ableton Live.'
    Info '  2. Settings > Link, Tempo & MIDI > Control Surface: choose "AbletonMCP"; Input/Output: None.'
    Info '  3. For the Max for Live device: Browser > User Library > Audio Effects > Max Audio Effect > AbletonMCP.'
    if (-not $SkipPython) {
        Info '  4. REST API: Start Menu > AbletonMCP > AbletonMCP REST API (http://127.0.0.1:8000/docs).'
        if (-not $ConfigureClaude) {
            Info '     Claude Desktop: run this installer with -ConfigureClaude to register the MCP server.'
        }
    }
    Info ''
    Info 'Uninstall: Settings > Apps > AbletonMCP, or Start Menu > AbletonMCP > Uninstall AbletonMCP.'
    return 0
}

# ----------------------------------------------------------------------------
# Uninstall
# ----------------------------------------------------------------------------

function Uninstall-Main {
    Step 'AbletonMCP uninstall'

    $statePath = Join-Path $script:InstallDir 'install-state.json'
    $state = $null
    if (Test-Path -LiteralPath $statePath) {
        try { $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json } catch { Warn "could not read $statePath" }
    }

    $documents = Get-UserDocuments
    $userLibrary = Get-UserLibrary
    $remoteScriptDir = Join-Path $userLibrary 'Remote Scripts\AbletonMCP'
    $m4lDeviceDir = Join-Path $userLibrary 'Presets\Audio Effects\Max Audio Effect\AbletonMCP'
    $startMenuDir = Join-Path (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs') 'AbletonMCP'

    if ($state) {
        if ($state.RemoteScriptDir) { $remoteScriptDir = $state.RemoteScriptDir }
        if ($state.M4LDeviceDir) { $m4lDeviceDir = $state.M4LDeviceDir }
        if ($state.StartMenuDir) { $startMenuDir = $state.StartMenuDir }
    }
    else {
        Warn 'no install state found; removing the default locations'
    }

    # Older installs used <Documents>\Ableton even when Live's library lives elsewhere.
    $documentLibrary = Join-Path (Get-UserDocuments) 'Ableton\User Library'
    if ($documentLibrary -ne (Get-UserLibrary)) {
        Remove-PathQuiet (Join-Path $documentLibrary 'Remote Scripts\AbletonMCP')
        Remove-PathQuiet (Join-Path $documentLibrary 'Presets\Audio Effects\Max Audio Effect\AbletonMCP')
    }
    if ($state -and $state.ConfiguredClaude) { Remove-ClaudeDesktopConfig }
    Unregister-UninstallEntry
    Remove-PathQuiet $startMenuDir
    Remove-PathQuiet $remoteScriptDir
    Remove-PathQuiet $m4lDeviceDir
    Remove-PathQuiet $script:InstallDir

    Step 'Done'
    Ok 'AbletonMCP was removed. Ableton user library folders that are still in use were kept.'
    return 0
}

# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------

if (-not $script:DryRun) {
    try {
        if (-not (Test-Path -LiteralPath $script:InstallDir)) {
            New-Item -ItemType Directory -Path $script:InstallDir -Force | Out-Null
        }
        $logDir = Join-Path $script:InstallDir 'logs'
        if (-not (Test-Path -LiteralPath $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
        $script:LogPath = Join-Path $logDir 'install.log'
        Add-Content -LiteralPath $script:LogPath -Value ('--- {0} {1} ---' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), ($MyInvocation.Line)) -Encoding UTF8
    }
    catch {
        $script:LogPath = $null
    }
}

try {
    if ($Uninstall) {
        exit (Uninstall-Main)
    }
    exit (Install-Main)
}
catch {
    Fail $_.Exception.Message
    Fail 'Installation failed. See the log for details.'
    exit 1
}
