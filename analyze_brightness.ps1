$ffmpegPath = "C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
$clipsDir = "C:\Users\claws\OneDrive\Desktop\gold\data\media\clips"

$clips = Get-ChildItem -Path $clipsDir -Filter "*.mp4" -ErrorAction SilentlyContinue | Sort-Object Name

$results = @()
$errorCount = 0
$processedCount = 0

foreach ($clip in $clips) {
    $file = $clip.FullName
    $fileName = $clip.Name
    $processedCount++
    
    if ($processedCount % 50 -eq 0) {
        Write-Host "Processed $processedCount files..." -ForegroundColor Gray
    }
    
    # Get duration using ffprobe
    $durationOutput = & "$ffmpegPath\ffprobe.exe" -v error -select_streams v:0 -show_entries format=duration -of csv=p=0 "$file" 2>$null
    
    if (-not $durationOutput) {
        $errorCount++
        continue
    }
    
    $duration = $null
    if (-not [double]::TryParse($durationOutput, [ref]$duration)) {
        $errorCount++
        continue
    }
    
    $midpoint = [math]::Floor($duration / 2)
    
    # Get YAVG from signalstats
    try {
        $ffmpegOutput = & "$ffmpegPath\ffmpeg.exe" -ss $midpoint -i "$file" -frames:v 1 -vf "signalstats,metadata=print:file=-" -f null - 2>&1 -ErrorAction SilentlyContinue
        
        # Find YAVG line - format is "lavfi.signalstats.YAVG=170.408"
        $yavgLines = @($ffmpegOutput | Where-Object { $_ -match "lavfi\.signalstats\.YAVG=" })
        
        if ($yavgLines.Count -gt 0) {
            # Take the last YAVG value (most recent frame analysis)
            $yavgLine = $yavgLines[-1]
            
            # Extract YAVG value using regex
            if ($yavgLine -match "lavfi\.signalstats\.YAVG=([\d\.]+)") {
                $yavgValueStr = $Matches[1]
                $yavgValue = [double]$yavgValueStr
                
                # Extract content_ID from filename
                $contentId = ""
                if ($fileName -match "^content_(\d+)_stock") {
                    $contentId = "content_$($Matches[1])"
                } elseif ($fileName -match "^test_([a-z_]+)_") {
                    $contentId = "test_$($Matches[1])"
                } else {
                    # Fallback: use first part before underscore
                    if ($fileName -match "^([^_]+)") {
                        $contentId = $Matches[1]
                    } else {
                        $contentId = "unknown"
                    }
                }
                
                $results += [PSCustomObject]@{
                    Filename = $fileName
                    ContentID = $contentId
                    YAVG = $yavgValue
                    TooBright = $yavgValue -gt 200
                }
            }
        }
    }
    catch {
        $errorCount++
    }
}

# Output results
Write-Host "`n=== ALL CLIPS (Sorted by YAVG descending) ===" -ForegroundColor Cyan
$sortedResults = $results | Sort-Object YAVG -Descending
$sortedResults | Format-Table -AutoSize -Property Filename, ContentID, YAVG, TooBright

Write-Host "`n=== CLIPS WITH YAVG > 160 (HIGHLIGHT) ===" -ForegroundColor Yellow
$highlightResults = $sortedResults | Where-Object { $_.YAVG -gt 160 }
if ($highlightResults) {
    $highlightResults | Format-Table -AutoSize -Property Filename, ContentID, YAVG, TooBright
} else {
    Write-Host "No clips with YAVG > 160" -ForegroundColor Green
}

Write-Host "`n=== GROUPED BY CONTENT_ID ===" -ForegroundColor Magenta
$grouped = $sortedResults | Group-Object ContentID | Sort-Object { ($_.Group | Measure-Object YAVG -Average).Average } -Descending
foreach ($group in $grouped) {
    $avgYavg = [Math]::Round(($group.Group | Measure-Object YAVG -Average).Average, 2)
    Write-Host "`nContent: $($group.Name) | Count: $($group.Count) | Avg YAVG: $avgYavg" -ForegroundColor Cyan
    $group.Group | Sort-Object YAVG -Descending | Format-Table -AutoSize @{Name="Filename"; Expression={$_.Filename}}, @{Name="YAVG"; Expression={$_.YAVG}}, @{Name="TooBright"; Expression={$_.TooBright}}
}

# Summary
Write-Host "`n=== SUMMARY ===" -ForegroundColor Green
Write-Host "Total clips analyzed: $($results.Count)"
Write-Host "Clips with YAVG > 200 (TOO BRIGHT): $(($results | Where-Object { $_.TooBright }).Count)"
Write-Host "Clips with YAVG > 160 (WARNING): $(($results | Where-Object { $_.YAVG -gt 160 }).Count)"
Write-Host "Processing errors: $errorCount"
