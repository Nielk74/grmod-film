# Decode JPEGs into 720x480 raw BGR files (preview inputs for build.ts).
#   powershell -File photos.ps1 OUTDIR photo1.jpg photo2.jpg ...
param([Parameter(Mandatory = $true)][string]$out, [Parameter(ValueFromRemainingArguments = $true)][string[]]$files)
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Force $out | Out-Null
foreach ($f in $files) {
  $img = [System.Drawing.Image]::FromFile($f)
  # Centre crop to 3:2, then scale to 720x480.
  $w = $img.Width; $h = $img.Height
  if ($w / $h -gt 1.5) { $cw = [int]($h * 1.5); $ch = $h } else { $cw = $w; $ch = [int]($w / 1.5) }
  $src = New-Object System.Drawing.Rectangle ([int](($w - $cw) / 2)), ([int](($h - $ch) / 2)), $cw, $ch
  $bmp = New-Object System.Drawing.Bitmap 720, 480, ([System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.DrawImage($img, (New-Object System.Drawing.Rectangle 0, 0, 720, 480), $src, [System.Drawing.GraphicsUnit]::Pixel)
  $data = $bmp.LockBits((New-Object System.Drawing.Rectangle 0, 0, 720, 480), [System.Drawing.Imaging.ImageLockMode]::ReadOnly, $bmp.PixelFormat)
  $stride = $data.Stride
  $buf = New-Object byte[] ($stride * 480)
  [System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $buf, 0, $buf.Length)
  $bmp.UnlockBits($data)
  # 720 x 3 bytes is a whole number of words: the rows have no padding. GDI+ keeps BGR order.
  [System.IO.File]::WriteAllBytes((Join-Path $out ([System.IO.Path]::GetFileNameWithoutExtension($f) + '.bgr')), $buf)
  $g.Dispose(); $bmp.Dispose(); $img.Dispose()
}
