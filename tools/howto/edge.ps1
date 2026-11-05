# Drives a throwaway Microsoft Edge for the "Connect your browser" How-to guide (tools/howto.sh --edge browser).
# A separate Edge: its own temporary profile (no sign-in, no sync, nothing from your own Edge), the extension loaded
# from the project folder, DevTools on 127.0.0.1 only. "close" kills that Edge and deletes the profile.
#   edge.ps1 launch <extension dir> <url>   |  eval <target url part> <js> [gesture]  |  shot <png>
#   edge.ps1 click <button name>            |  focus  |  targets  |  names            |  close
param([Parameter(Position = 0)][string]$Cmd, [Parameter(Position = 1)][string]$A = "",
      [Parameter(Position = 2)][string]$B = "", [Parameter(Position = 3)][string]$C = "")
$ErrorActionPreference = "Stop"
$Port = 9333
$Profile = Join-Path $env:TEMP "sbgd-edge-howto"
$Edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"

Add-Type @"
using System; using System.Runtime.InteropServices;
public static class W {
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr v);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint x, uint y, uint d, UIntPtr e);
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr h, int a, out RECT r, int s);
}
"@
[void][W]::SetProcessDpiAwarenessContext([IntPtr](-4))

function Browser-Pid {  # the browser process of OUR Edge (its command line names the throwaway profile)
  $p = Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
    Where-Object { $_.CommandLine -like "*$Profile*" -and $_.CommandLine -notlike "*--type=*" } | Select-Object -First 1
  if ($p) { return [uint32]$p.ProcessId } else { return 0 }
}

function Main-Window {
  $bp = Browser-Pid
  $script:found = [IntPtr]::Zero; $script:best = 0
  [W]::EnumWindows({ param($h, $l)
    $wp = [uint32]0; [void][W]::GetWindowThreadProcessId($h, [ref]$wp)
    if ($wp -eq $bp -and [W]::IsWindowVisible($h) -and [W]::GetWindowTextLength($h) -gt 0) {
      $rc = New-Object W+RECT; [void][W]::DwmGetWindowAttribute($h, 9, [ref]$rc, 16)
      $area = ($rc.R - $rc.L) * ($rc.B - $rc.T)
      if ($area -gt $script:best) { $script:best = $area; $script:found = $h } }
    return $true }, [IntPtr]::Zero) | Out-Null
  return $script:found
}

function Cdp($wsUrl, $method, $params) {
  $ws = New-Object System.Net.WebSockets.ClientWebSocket
  $ct = [Threading.CancellationToken]::None
  $ws.ConnectAsync([Uri]$wsUrl, $ct).Wait()
  $msg = @{ id = 1; method = $method; params = $params } | ConvertTo-Json -Depth 10 -Compress
  $bytes = [Text.Encoding]::UTF8.GetBytes($msg)
  $ws.SendAsync((New-Object ArraySegment[byte] -ArgumentList @(, $bytes)), "Text", $true, $ct).Wait()
  $buf = New-Object byte[] 1048576
  while ($true) {
    $ms = New-Object IO.MemoryStream
    do {
      $r = $ws.ReceiveAsync((New-Object ArraySegment[byte] -ArgumentList @(, $buf)), $ct)
      if (-not $r.Wait(60000)) { throw "DevTools did not answer" }
      $ms.Write($buf, 0, $r.Result.Count)
    } while (-not $r.Result.EndOfMessage)
    $text = [Text.Encoding]::UTF8.GetString($ms.ToArray())
    $o = $text | ConvertFrom-Json
    if ($o.id -eq 1) { $ws.Dispose(); return $o }
  }
}

function Targets { $l = Invoke-RestMethod "http://127.0.0.1:$Port/json/list"; foreach ($t in $l) { $t } }

switch ($Cmd) {
  "launch" {
    if (Browser-Pid) { throw "the throwaway Edge is already running" }
    if (Test-Path $Profile) { Remove-Item -Recurse -Force $Profile }
    New-Item -ItemType Directory $Profile | Out-Null
    $args = @("--user-data-dir=$Profile", "--no-first-run", "--no-default-browser-check", "--disable-sync",
      "--disable-features=msImplicitSignin,msEdgeImplicitSignin,DisableLoadExtensionCommandLineSwitch,msEdgeWelcomePage",
      "--remote-debugging-port=$Port", "--remote-allow-origins=http://127.0.0.1:$Port", "--load-extension=$A",
      "--window-position=80,60", "--window-size=1280,800", "--lang=en-US", "--new-window", $B)
    Start-Process -FilePath $Edge -ArgumentList $args | Out-Null
    for ($i = 0; $i -lt 40; $i++) { Start-Sleep -Milliseconds 500; try { Targets | Out-Null; break } catch {} }
    Targets | ForEach-Object { "{0}`t{1}" -f $_.type, $_.url }
  }
  "targets" { Targets | ForEach-Object { "{0}`t{1}`t{2}" -f $_.type, $_.title, $_.url } }
  "eval" {
    $t = Targets | Where-Object { $_.url -like "*$A*" -and $_.webSocketDebuggerUrl } | Select-Object -First 1
    if (-not $t) { throw "no target matches $A" }
    $o = Cdp $t.webSocketDebuggerUrl "Runtime.evaluate" @{ expression = $B; awaitPromise = $true; returnByValue = $true; userGesture = ($C -eq "gesture") }
    if ($o.result.exceptionDetails) { throw ($o.result.exceptionDetails | ConvertTo-Json -Depth 6 -Compress) }
    $o.result.result.value | ConvertTo-Json -Depth 6 -Compress
  }
  "shot" {
    Add-Type -AssemblyName System.Drawing
    $h = Main-Window
    if ($h -eq [IntPtr]::Zero) { throw "no Edge window" }
    $r = New-Object W+RECT
    [void][W]::DwmGetWindowAttribute($h, 9, [ref]$r, 16)
    $bmp = New-Object Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
    $gr = [Drawing.Graphics]::FromImage($bmp)
    $gr.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size)
    $bmp.Save($A, [Drawing.Imaging.ImageFormat]::Png)
    "{0}x{1}" -f $bmp.Width, $bmp.Height
  }
  "focus" {  # brings our Edge to the front (a shot does not: it would close an open extension popup)
    $h = Main-Window
    [void][W]::ShowWindow($h, 9); [void][W]::SetForegroundWindow($h)
    Start-Sleep -Milliseconds 500
    "focused"
  }
  "click" {  # a button of Edge's own interface (the permission prompt), found by its name
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    $h = Main-Window
    $root = [Windows.Automation.AutomationElement]::RootElement
    $bp = Browser-Pid
    $cond = New-Object Windows.Automation.AndCondition (
      (New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::ProcessIdProperty, [int]$bp)),
      (New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::NameProperty, $A)),
      (New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::ControlTypeProperty, [Windows.Automation.ControlType]::Button)))
    for ($i = 0; $i -lt 20; $i++) {
      $el = $root.FindFirst([Windows.Automation.TreeScope]::Descendants, $cond)
      if ($el) { break }
      Start-Sleep -Milliseconds 500
    }
    if (-not $el) { throw "no button named $A" }
    $p = $null
    if ($el.TryGetCurrentPattern([Windows.Automation.InvokePattern]::Pattern, [ref]$p)) { $p.Invoke() }
    else {  # some Edge buttons only take a real click
      $b = $el.Current.BoundingRectangle
      [void][W]::SetCursorPos([int]($b.X + $b.Width / 2), [int]($b.Y + $b.Height / 2))
      [W]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero); [W]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)
    }
    "clicked $A"
  }
  "dismiss" {  # an Edge bubble's button, if it is there (the developer-mode warning); never fails
    try { & $PSCommandPath click $A } catch { "nothing to dismiss" }
  }
  "names" {  # what Edge's interface shows (to find a button's name)
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    $bp = Browser-Pid
    $root = [Windows.Automation.AutomationElement]::RootElement
    $cond = New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::ProcessIdProperty, [int]$bp)
    $root.FindAll([Windows.Automation.TreeScope]::Descendants, $cond) | ForEach-Object {
      $n = $_.Current.Name; if ($n) { "{0}`t{1}" -f $_.Current.ControlType.ProgrammaticName, $n } }
  }
  "close" {
    $bp = Browser-Pid
    if ($bp) { Stop-Process -Id $bp -Force; Start-Sleep -Seconds 2 }
    Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object { $_.CommandLine -like "*$Profile*" } |
      ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
    if (Test-Path $Profile) { Remove-Item -Recurse -Force $Profile -ErrorAction SilentlyContinue }
    "closed"
  }
  default { throw "unknown command $Cmd" }
}
