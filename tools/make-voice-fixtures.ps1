# Generates spoken test clips with the built-in Windows speech synthesizer
# (offline, free) as 24 kHz 16-bit mono WAV, the format the realtime API wants.
# Expected transcripts live next to them in expected.json.
Add-Type -AssemblyName System.Speech
$out = Join-Path $PSScriptRoot "..\tests\fixtures\voice"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(24000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$clips = @(
  @{ name = "en_atlas"; voice = "Microsoft Zira Desktop"; text = "Remind me to send the Atlas proposal on Friday, and link it to the weekly review." },
  @{ name = "en_idea"; voice = "Microsoft David Desktop"; text = "New idea: each project space could have its own soundscape." },
  @{ name = "fr_by_en_voice"; voice = "Microsoft Zira Desktop"; text = "Note pour demain: appeler le client Atlas." }
)
foreach ($c in $clips) {
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice($c.voice)
  $s.Rate = 0
  $s.SetOutputToWaveFile((Join-Path $out ($c.name + ".wav")), $fmt)
  $s.Speak($c.text)
  $s.Dispose()
}
