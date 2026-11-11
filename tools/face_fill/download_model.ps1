param([string]$OutputDirectory = 'scratch/face-fill/models')
$ErrorActionPreference = 'Stop'
$modelDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
foreach ($sourceDirectory in @('C:\Users\Antoine\Pictures\Ricoh', 'C:\Users\Antoine\Pictures\Ricoh2')) {
    if ($modelDirectory.Equals($sourceDirectory, [System.StringComparison]::OrdinalIgnoreCase) -or
        $modelDirectory.StartsWith($sourceDirectory + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Model output must stay outside original photo folders'
    }
}
New-Item -ItemType Directory -Force -Path $modelDirectory | Out-Null
$modelPath = Join-Path $modelDirectory 'yunet.onnx'
$expectedHash = '8F2383E4DD3CFBB4553EA8718107FC0423210DC964F9F4280604804ED2552FA4'
Invoke-WebRequest -Uri 'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx' -OutFile $modelPath
$actualHash = (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash
if ($actualHash -ne $expectedHash) { throw "Unexpected YuNet model hash: $actualHash" }
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_detection_yunet/LICENSE' -OutFile (Join-Path $modelDirectory 'LICENSE')
Write-Output "Verified YuNet model: $actualHash"
