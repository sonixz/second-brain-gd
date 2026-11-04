# Local OCR with the engine built into Windows 10/11 (Windows.Media.Ocr). Nothing leaves the machine.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ocr_windows.ps1 -List <file with one PNG path per line> [-Lang fr-CA]
# Prints one JSON line per image as soon as it is read: {"i": 1, "text": "..."}, then {"language": "fr-CA"} (UTF-8).
param([Parameter(Mandatory = $true)][string]$List, [string]$Lang = "")
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }

$engine = $null
$wanted = @()
if ($Lang) { $wanted += $Lang }
$wanted += @("fr-CA", "fr-FR", "fr-BE", "fr-CH")
foreach ($tag in $wanted) {
    if ($engine -eq $null) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($tag)) }
}
if ($engine -eq $null) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($engine -eq $null) { throw "no OCR language installed in Windows (Settings > Time & language > Language)" }

$i = 0
foreach ($path in (Get-Content -LiteralPath $List -Encoding UTF8 | Where-Object { $_.Trim() })) {
    $i += 1
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    try {
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $text = (($result.Lines | ForEach-Object { $_.Text }) -join "`n")
        [Console]::Out.WriteLine((@{ i = $i; text = $text } | ConvertTo-Json -Compress))
        [Console]::Out.Flush()
    } finally { $stream.Dispose() }
}
[Console]::Out.WriteLine((@{ language = $engine.RecognizerLanguage.LanguageTag } | ConvertTo-Json -Compress))
