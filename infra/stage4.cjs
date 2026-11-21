const cdk = require('aws-cdk-lib');
const { aws_ec2: ec2, aws_ecs: ecs, aws_rds: rds, aws_s3: s3,
  aws_ecr: ecr, aws_elasticloadbalancingv2: elb, aws_secretsmanager: secrets,
  aws_logs: logs } = cdk;

const app = new cdk.App();
const stack = new cdk.Stack(app, 'RankFlowStage4', {
  env: { region: 'ca-central-1' },
  synthesizer: new cdk.BootstraplessSynthesizer(),
});
cdk.Tags.of(stack).add('project', 'rankflow');
cdk.Tags.of(stack).add('stage', 'stage4');
const certificate = app.node.tryGetContext('certificate');
const stable = app.node.tryGetContext('stable');
const fixture = app.node.tryGetContext('fixture');
const vpc = new ec2.Vpc(stack, 'Vpc', {
  maxAzs: 2, natGateways: 0,
  subnetConfiguration: [
    { name: 'edge', subnetType: ec2.SubnetType.PUBLIC },
    { name: 'data', subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
  ],
});
const bucket = new s3.Bucket(stack, 'Bundles', {
  blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
  encryption: s3.BucketEncryption.S3_MANAGED,
  enforceSSL: true, versioned: true,
  removalPolicy: cdk.RemovalPolicy.DESTROY,
});
const repository = new ecr.Repository(stack, 'Images', {
  removalPolicy: cdk.RemovalPolicy.DESTROY,
  imageTagMutability: ecr.TagMutability.IMMUTABLE,
  imageScanOnPush: true, emptyOnDelete: true,
});
const db = new rds.DatabaseInstance(stack, 'Database', {
  vpc, vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
  engine: rds.DatabaseInstanceEngine.postgres({ version: rds.PostgresEngineVersion.VER_16 }),
  instanceType: new ec2.InstanceType('t4g.micro'),
  databaseName: 'rankflow', credentials: rds.Credentials.fromGeneratedSecret('rankflow'),
  storageEncrypted: true, allocatedStorage: 20, storageType: rds.StorageType.GP3,
  backupRetention: cdk.Duration.days(1), deleteAutomatedBackups: true,
  removalPolicy: cdk.RemovalPolicy.DESTROY,
});
const alb = new elb.ApplicationLoadBalancer(stack, 'Alb', { vpc, internetFacing: true });
const cluster = new ecs.Cluster(stack, 'Cluster', { vpc });
const group = new logs.LogGroup(stack, 'Logs', {
  retention: logs.RetentionDays.ONE_DAY, removalPolicy: cdk.RemovalPolicy.DESTROY,
});
const outputs = { AlbDns: alb.loadBalancerDnsName, BundleBucket: bucket.bucketName,
  Repository: repository.repositoryUri, DatabaseId: db.instanceIdentifier,
  DatabaseEndpoint: db.dbInstanceEndpointAddress, Cluster: cluster.clusterName, Logs: group.logGroupName };

if (certificate) {
  const task = new ecs.FargateTaskDefinition(stack, 'Task', { cpu: 512, memoryLimitMiB: 2048 });
  const appSecrets = {};
  for (const name of ['SESSION_KEY', 'ROUTING_KEY', 'RELEASE_SIGNING_KEY', 'ADMIN_BEARER',
    'OPERATOR_BEARER', 'VIEWER_BEARER']) {
    const secret = new secrets.Secret(stack, name, {
      generateSecretString: { passwordLength: 48, excludePunctuation: true },
    });
    appSecrets['RANKFLOW_' + name] = ecs.Secret.fromSecretsManager(secret);
  }
  const container = task.addContainer('api', {
    image: ecs.ContainerImage.fromEcrRepository(repository, app.node.getContext('imageTag')),
    logging: ecs.LogDrivers.awsLogs({ logGroup: group, streamPrefix: 'api' }),
    environment: {
      RANKFLOW_BUNDLE_BUCKET: bucket.bucketName,
      RANKFLOW_STABLE_ID: stable,
      RANKFLOW_FIXTURE_ID: fixture,
      RANKFLOW_DB_HOST: app.node.tryGetContext('restoreEndpoint') || db.dbInstanceEndpointAddress,
      RANKFLOW_MINIMUM_CAPACITY: '2',
      OPENBLAS_NUM_THREADS: '1', OMP_NUM_THREADS: '1',
    },
    secrets: {
      ...appSecrets,
      RANKFLOW_DB_USER: ecs.Secret.fromSecretsManager(db.secret, 'username'),
      RANKFLOW_DB_PASSWORD: ecs.Secret.fromSecretsManager(db.secret, 'password'),
    },
  });
  container.addPortMappings({ containerPort: 8000 });
  bucket.grantRead(task.taskRole, 'generations/*');
  const service = new ecs.FargateService(stack, 'Service', {
    cluster, taskDefinition: task, desiredCount: 2, assignPublicIp: true,
    vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
    minHealthyPercent: 100,
    circuitBreaker: { rollback: true },
    healthCheckGracePeriod: cdk.Duration.seconds(120),
    propagateTags: ecs.PropagatedTagSource.SERVICE, enableECSManagedTags: true,
  });
  db.connections.allowDefaultPortFrom(service);
  const listener = alb.addListener('Https', {
    port: 443, open: false, certificates: [elb.ListenerCertificate.fromArn(certificate)],
    sslPolicy: elb.SslPolicy.TLS13_RES,
  });
  listener.connections.allowDefaultPortFrom(ec2.Peer.ipv4(app.node.getContext('ingress')));
  const targets = listener.addTargets('Api', {
    port: 8000, targets: [service], deregistrationDelay: cdk.Duration.seconds(15),
    healthCheck: { path: '/health/routable', healthyHttpCodes: '200',
      interval: cdk.Duration.seconds(10), healthyThresholdCount: 2, unhealthyThresholdCount: 2 },
  });
  Object.assign(outputs, { Service: service.serviceName, DesiredTasks: '2',
    Targets: targets.targetGroupArn });
}
for (const [name, value] of Object.entries(outputs)) {
  new cdk.CfnOutput(stack, `Output${name}`, { value }).overrideLogicalId(name);
}
