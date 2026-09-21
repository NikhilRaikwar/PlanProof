[CmdletBinding()]
param(
    [string]$ProjectId = "planproof-ai",
    [string]$Region = "asia-south1"
)

$ErrorActionPreference = "Stop"

$gcloud = Get-Command gcloud -ErrorAction SilentlyContinue
if (-not $gcloud) {
    $bundledGcloud = "${env:LOCALAPPDATA}\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    if (-not (Test-Path -LiteralPath $bundledGcloud)) {
        throw "Google Cloud CLI is required. Install it and authenticate before deployment."
    }
    $gcloud = $bundledGcloud
} else {
    $gcloud = $gcloud.Source
}

$requiredApis = @(
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
    "redis.googleapis.com",
    "compute.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com"
)
$enabled = & $gcloud services list --enabled --project $ProjectId --format="value(config.name)"
foreach ($api in $requiredApis) {
    if ($enabled -notcontains $api) { throw "Required API is not enabled: $api" }
}

$secretNames = @(
    "planproof-mongodb-uri", "planproof-mongodb-database", "planproof-redis-url",
    "planproof-openrouter-api-key", "planproof-openrouter-primary-model",
    "planproof-aimlapi-api-key", "planproof-aimlapi-fallback-model"
)
foreach ($secretName in $secretNames) {
    & $gcloud secrets describe $secretName --project $ProjectId --format="value(name)" | Out-Null
}

Write-Output "Preflight passed for project $ProjectId in $Region. No resources were created."
