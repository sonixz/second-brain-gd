# Draws a page of text as a picture (a "scanned" page with no text layer), for the How-to sample files.
#   powershell -File render_page.ps1 -TextFile page.txt -Out page.bmp
param([string]$TextFile, [string]$Out)
Add-Type -AssemblyName System.Drawing
$w = 1275; $h = 1650
$bmp = New-Object System.Drawing.Bitmap $w, $h, ([System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(246, 244, 238))
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias
$g.TranslateTransform(0, 0); $g.RotateTransform(0.35)
$ink = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(38, 38, 44))
$title = New-Object System.Drawing.Font "Georgia", 26, ([System.Drawing.FontStyle]::Bold)
$body = New-Object System.Drawing.Font "Georgia", 17
$y = 110
foreach ($line in (Get-Content -Encoding UTF8 $TextFile)) {
  if ($line.StartsWith("# ")) { $g.DrawString($line.Substring(2), $title, $ink, 110, $y); $y += 62; continue }
  $g.DrawString($line, $body, $ink, 110, $y); $y += 34
}
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Bmp)
