param(
  [string]$ConfigPath = "config/app-config.yaml"
)

if (-not (Test-Path $ConfigPath)) {
  Write-Error "Config not found: $ConfigPath"
  exit 1
}

$repoURL = ""
$envName = ""
$targetRevision = "main"
$argoNamespace = "argocd"
$appName = ""
$appNamespace = ""
$platformRepos = @(
  "https://kubernetes.github.io/ingress-nginx",
  "https://charts.jetstack.io",
  "https://kubernetes-sigs.github.io/secrets-store-csi-driver/charts",
  "https://raw.githubusercontent.com/gidoichi/secrets-store-csi-driver-provider-infisical/main/charts"
)

$lines = Get-Content $ConfigPath
$section = ""
foreach ($line in $lines) {
  if ($line -match '^\s*bootstrap:\s*$') { $section = "bootstrap"; continue }
  if ($line -match '^\s*global:\s*$') { $section = "global"; continue }
  if ($line -match '^\s*workloads:\s*$') { $section = ""; continue }

  if ($section -eq "bootstrap") {
    if ($line -match '^\s{4}repoURL:\s*(\S+)') { $repoURL = $matches[1]; continue }
    if ($line -match '^\s{4}env:\s*(\S+)') { $envName = $matches[1]; continue }
    if ($line -match '^\s{4}targetRevision:\s*(\S+)') { $targetRevision = $matches[1]; continue }
    if ($line -match '^\s{4}argoNamespace:\s*(\S+)') { $argoNamespace = $matches[1]; continue }
  }

  if ($section -eq "global") {
    if ($line -match '^\s{4}name:\s*(\S+)') { $appName = $matches[1]; continue }
    if ($line -match '^\s{4}namespace:\s*(\S+)') { $appNamespace = $matches[1]; continue }
  }
}

if (-not $repoURL) { Write-Error "Missing spec.bootstrap.repoURL in $ConfigPath"; exit 1 }
if (-not $envName) { Write-Error "Missing spec.bootstrap.env in $ConfigPath"; exit 1 }
if (-not $appName) { Write-Error "Missing spec.global.name in $ConfigPath"; exit 1 }
if (-not $appNamespace) { Write-Error "Missing spec.global.namespace in $ConfigPath"; exit 1 }

function Replace-NthCaptureLine {
  param(
    [string]$Content,
    [string]$Pattern,
    [int]$Index,
    [string]$Value
  )
  $matches = [regex]::Matches($Content, $Pattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)
  if ($matches.Count -le $Index) { return $Content }
  $match = $matches[$Index]
  $prefix = $match.Groups[1].Value
  $replacement = $prefix + $Value
  return $Content.Remove($match.Index, $match.Length).Insert($match.Index, $replacement)
}

$rootPath = "apps/root/application.yaml"
if (Test-Path $rootPath) {
  $rootContent = Get-Content $rootPath -Raw
  $rootContent = [regex]::Replace($rootContent, '(?m)^(\s*repoURL:\s*).*$', ('$1' + $repoURL))
  $rootContent = [regex]::Replace($rootContent, '(?m)^(\s*targetRevision:\s*).*$', ('$1' + $targetRevision))
  $rootContent = [regex]::Replace($rootContent, '(?m)^(\s*path:\s*).*$', ('$1' + "clusters/$envName"))
  $rootContent = [regex]::Replace($rootContent, '(?m)^(\s*namespace:\s*).*$', ('$1' + $argoNamespace))
  Set-Content -Path $rootPath -Value $rootContent
}

$appPath = "applications/app/application.yaml"
if (Test-Path $appPath) {
  $appContent = Get-Content $appPath -Raw
  $appContent = [regex]::Replace($appContent, '(?m)^(\s*repoURL:\s*).*$', ('$1' + $repoURL))
  $appContent = [regex]::Replace($appContent, '(?m)^(\s*targetRevision:\s*).*$', ('$1' + $targetRevision))
  $appContent = [regex]::Replace($appContent, '(?m)^(\s*project:\s*).*$', ('$1' + "cluster-$envName"))
  $appContent = Replace-NthCaptureLine -Content $appContent -Pattern '(?m)^(\s*name:\s*).*$' -Index 0 -Value $appName
  $appContent = Replace-NthCaptureLine -Content $appContent -Pattern '(?m)^(\s*namespace:\s*).*$' -Index 0 -Value $argoNamespace
  $appContent = Replace-NthCaptureLine -Content $appContent -Pattern '(?m)^(\s*namespace:\s*).*$' -Index 1 -Value $appNamespace
  Set-Content -Path $appPath -Value $appContent
}

$platformDir = "applications/platform"
if (Test-Path $platformDir) {
  $platformFiles = Get-ChildItem -Path $platformDir -Filter "*.yaml" -ErrorAction SilentlyContinue
  foreach ($platformFile in $platformFiles) {
    $platformContent = Get-Content $platformFile.FullName -Raw
    $platformContent = [regex]::Replace($platformContent, '(?m)^(\s*project:\s*).*$', ('$1' + "cluster-$envName"))
    $platformContent = Replace-NthCaptureLine -Content $platformContent -Pattern '(?m)^(\s*namespace:\s*).*$' -Index 0 -Value $argoNamespace
    if ($platformFile.Name -in @("cert-manager-issuers.yaml", "infisical-secretproviderclass.yaml")) {
      $platformContent = [regex]::Replace($platformContent, '(?m)^(\s*repoURL:\s*).*$', ('$1' + $repoURL))
      $platformContent = [regex]::Replace($platformContent, '(?m)^(\s*targetRevision:\s*).*$', ('$1' + $targetRevision))
    }
    if ($platformFile.Name -eq "infisical-secretproviderclass.yaml") {
      $platformContent = Replace-NthCaptureLine -Content $platformContent -Pattern '(?m)^(\s*namespace:\s*).*$' -Index 1 -Value $appNamespace
    }
    Set-Content -Path $platformFile.FullName -Value $platformContent
  }
}

$projectFiles = Get-ChildItem -Path "projects" -Recurse -Filter "project.yaml" -ErrorAction SilentlyContinue
foreach ($projectFile in $projectFiles) {
  $projLines = Get-Content $projectFile.FullName
  $updated = New-Object System.Collections.Generic.List[string]
  $inSourceRepos = $false
  foreach ($line in $projLines) {
    if ($line -match '^\s*sourceRepos:\s*$') {
      $updated.Add($line) | Out-Null
      $updated.Add("  - $repoURL") | Out-Null
      foreach ($platformRepo in $platformRepos) {
        $updated.Add("  - $platformRepo") | Out-Null
      }
      $inSourceRepos = $true
      continue
    }
    if ($inSourceRepos) {
      if ($line -match '^\s*-\s*') { continue }
      $inSourceRepos = $false
    }
    if (-not $inSourceRepos) {
      $updated.Add($line) | Out-Null
    }
  }
  Set-Content -Path $projectFile.FullName -Value $updated
}

Write-Host "Bootstrap files updated from $ConfigPath"
