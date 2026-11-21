param([string]$RestoreEndpoint)
$ErrorActionPreference = 'Stop'
$d = Get-Content -Raw artifacts/stage4/deployment.json | ConvertFrom-Json
$clientIp = (Invoke-RestMethod https://checkip.amazonaws.com).Trim()
$env:NODE_PATH = (Resolve-Path artifacts/stage4/node_modules).Path
$context = @('-c', "certificate=$($d.Certificate)", '-c', "stable=$($d.Stable)", '-c', "fixture=$($d.Fixture)",
    '-c', "ingress=$clientIp/32", '-c', 'imageTag=stage4-v1')
if ($RestoreEndpoint) { $context += @('-c', "restoreEndpoint=$RestoreEndpoint") }
node artifacts/stage4/node_modules/aws-cdk/bin/cdk synth --app 'node infra/stage4.cjs' --output artifacts/stage4/cdk.out --quiet @context
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
aws cloudformation update-stack --stack-name RankFlowStage4 --region ca-central-1 --template-body file://artifacts/stage4/cdk.out/RankFlowStage4.template.json --capabilities CAPABILITY_IAM --no-cli-pager
exit $LASTEXITCODE
