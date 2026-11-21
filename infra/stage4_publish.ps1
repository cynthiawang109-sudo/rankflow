param([Parameter(Mandatory=$true)][string]$OpenSsl)
$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = (Resolve-Path artifacts/stage4/python).Path

docker build -t rankflow-stage4-local .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker build -f infra/Dockerfile -t rankflow-stage4-cloud .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
aws cloudformation wait stack-create-complete --stack-name RankFlowStage4 --region ca-central-1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run --locked python -m scripts.stage4_stage_assets $OpenSsl
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$d = Get-Content -Raw artifacts/stage4/deployment.json | ConvertFrom-Json
$registry = $d.Repository.Split('/')[0]
aws ecr get-login-password --region ca-central-1 | docker login --username AWS --password-stdin $registry
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$destination = $d.Repository + ':stage4-v1'
docker tag rankflow-stage4-cloud $destination
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker push $destination
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& infra/stage4_update.ps1
exit $LASTEXITCODE
