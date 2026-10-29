# Raw BGR (rows padded to 4 bytes) to a JPEG or PNG, by the output's extension.
#   powershell -File bgr2img.ps1 IN.bgr WIDTH HEIGHT OUT.jpg|OUT.png
param([string]$in, [int]$width, [int]$height, [string]$out)
Add-Type -AssemblyName System.Drawing
$buf = [System.IO.File]::ReadAllBytes($in)
$bmp = New-Object System.Drawing.Bitmap $width, $height, ([System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
$data = $bmp.LockBits((New-Object System.Drawing.Rectangle 0, 0, $width, $height), [System.Drawing.Imaging.ImageLockMode]::WriteOnly, $bmp.PixelFormat)
if ($data.Stride * $height -ne $buf.Length) { throw "expected $($data.Stride * $height) bytes, got $($buf.Length)" }
[System.Runtime.InteropServices.Marshal]::Copy($buf, 0, $data.Scan0, $buf.Length)
$bmp.UnlockBits($data)
if ($out.ToLower().EndsWith('.png')) { $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png) }
else {
  $codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq 'image/jpeg' }
  $params = New-Object System.Drawing.Imaging.EncoderParameters 1
  $params.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter ([System.Drawing.Imaging.Encoder]::Quality), 92L
  $bmp.Save($out, $codec, $params)
}
$bmp.Dispose()
