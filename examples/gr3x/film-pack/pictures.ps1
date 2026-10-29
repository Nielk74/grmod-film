# Draw the film pack's power-off pictures (720 x 480 PNG and raw BGR) into OUTDIR.
#   powershell -File pictures.ps1 OUTDIR
param([Parameter(Mandatory = $true)][string]$out)
Add-Type -ReferencedAssemblies System.Drawing -Path (Join-Path $PSScriptRoot 'Pictures.cs')
[FilmPackPictures]::Run([System.IO.Path]::GetFullPath($out))
