# Finance News Bot - daily local runner
# Replaces GitHub Actions while the GitHub account is locked for billing.
# Runs: crawl -> markdown daily -> AI article -> images -> WeChat HTML
#
# Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File "C:\project\finance-news-bot\run_daily.ps1"

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Base      = "C:\project\finance-news-bot"
$Py        = "C:\Tools\Python\python.exe"
$Yesterday = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")
$LogDir    = Join-Path $Base "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile   = Join-Path $LogDir ("daily_" + $Yesterday + ".log")

function Log($msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# Guard: if today's run for this target date already completed, do nothing.
# (Lets the logon catch-up task re-run safely without repeating work.)
if (Test-Path $LogFile) {
    $tail = Get-Content $LogFile -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($tail -match "=== FinanceNewsBot daily run done ===") {
        Log "guard: run for $Yesterday already completed, skip."
        exit 0
    }
}

function Run-Step($n, $name, $exe, $scriptArgs) {
    Log "[$n] $name"
    & $exe @scriptArgs 2>&1 | Out-File -FilePath $LogFile -Append -Encoding utf8
    $code = $LASTEXITCODE
    if ($code -ne 0) { Log "[$n] FAILED (exit=$code)"; return $false }
    Log "[$n] ok"
    return $true
}

Set-Location $Base
Log "=== FinanceNewsBot daily run start (target date=$Yesterday) ==="

# 1) Crawl yesterday's news
$ok = Run-Step "1/5" "finance_crawler.py" $Py @("finance_crawler.py", "--date", $Yesterday, "--full")
if (-not $ok) { Log "aborting: crawl failed"; exit 1 }

# 2) Generate markdown daily report
$ok = Run-Step "2/5" "generate_md.py" $Py @("generate_md.py", "--date", $Yesterday)
if (-not $ok) { Log "warn: generate_md failed, continuing" }

# 3) AI article draft (skip if already generated for this date)
$ArticleMd = Join-Path $Base ("drafts\" + $Yesterday + "\article.md")
if (Test-Path $ArticleMd) {
    Log "[3/5] article.md already exists, skip write_article.py"
} else {
    $ok = Run-Step "3/5" "write_article.py" $Py @("write_article.py", "--date", $Yesterday)
    if (-not $ok) { Log "aborting: article generation failed (cannot build HTML without article)"; exit 1 }
}

# 4) Search and download images (script skips existing files by default)
$ok = Run-Step "4/5" "search_images.py" $Py @("search_images.py", "--date", $Yesterday)
if (-not $ok) { Log "warn: image search failed, continuing" }

# 5) Convert article to WeChat-compatible HTML
$ArticleArg = "drafts\" + $Yesterday + "\article.md"
$OutArg     = "drafts\" + $Yesterday + "\mp_body.html"
$ok = Run-Step "5/5" "md_to_mphtml.py" $Py @("md_to_mphtml.py", $ArticleArg, "-o", $OutArg)
if (-not $ok) { Log "warn: md_to_mphtml failed" }

Log "=== FinanceNewsBot daily run done ==="
