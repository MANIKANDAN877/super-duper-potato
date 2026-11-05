$backend = Invoke-WebRequest -Uri 'http://localhost:8000/health' -UseBasicParsing -TimeoutSec 20
$frontend = Invoke-WebRequest -Uri 'http://localhost:5173' -UseBasicParsing -TimeoutSec 20
Write-Output "BACKEND_STATUS=$($backend.StatusCode)"
Write-Output "BACKEND_BODY=$($backend.Content)"
Write-Output "FRONTEND_STATUS=$($frontend.StatusCode)"
Write-Output "FRONTEND_BODY_SNIPPET=$($frontend.Content.Substring(0, 80))"
