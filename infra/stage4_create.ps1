# Prepare the Stage 4 CDK and Python tooling, then create the base stack.
$ErrorActionPreference = 'Stop'
$env:AWS_DEFAULT_REGION = 'ca-central-1'
aws sts get-caller-identity --region ca-central-1 --no-cli-pager
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$work = 'artifacts/stage4'
New-Item -ItemType Directory -Force $work | Out-Null
Copy-Item infra/package.json,infra/package-lock.json $work
npm.cmd ci --prefix $work
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv pip install --target "$work/python" boto3==1.43.7
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:NODE_PATH = (Resolve-Path "$work/node_modules").Path
node "$work/node_modules/aws-cdk/bin/cdk" synth --app 'node infra/stage4.cjs' --output "$work/cdk.out" --quiet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
aws cloudformation create-stack --stack-name RankFlowStage4 --region ca-central-1 --template-body "file://$work/cdk.out/RankFlowStage4.template.json" --tags Key=project,Value=rankflow Key=stage,Value=stage4 --no-cli-pager
exit $LASTEXITCODE
