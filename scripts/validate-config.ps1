param(
  [string]$ConfigPath = "config/app-config.yaml",
  [string]$SchemaPath = "schemas/app-config.schema.json"
)

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
  Write-Error "Python not found. Install Python and run: pip install pyyaml jsonschema"
  exit 1
}

python scripts/validate-config.py $ConfigPath $SchemaPath
exit $LASTEXITCODE
