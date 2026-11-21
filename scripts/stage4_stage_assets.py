"""Stage the recorded stable bundle and a labeled rule-only routing fixture."""
import json
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.exceptions import ClientError

from rankflow.generation import encoded, identity


region = "ca-central-1"
aws = boto3.Session(region_name=region)
stack = aws.client("cloudformation").describe_stacks(StackName="RankFlowStage4")["Stacks"][0]
outputs = {item["OutputKey"]: item["OutputValue"] for item in stack["Outputs"]}
work = Path("artifacts/stage4")
registry = Path("artifacts/stage1/generations")
stable = (registry / "alpha.txt").read_text().strip()
source = registry / stable
manifest = json.loads((source / "manifest.json").read_bytes())
fixture_manifest = dict(manifest, test_only="Stage 4 routing fixture, rule strategy")
fixture = identity(fixture_manifest)
s3 = aws.client("s3")


def upload(item):
    generation, name, body = item
    object_id = {"Bucket": outputs["BundleBucket"], "Key": f"generations/{generation}/{name}"}
    try:
        s3.put_object(**object_id, Body=body, IfNoneMatch="*", Tagging="project=rankflow&stage=stage4")
    except ClientError as error:
        if error.response["ResponseMetadata"]["HTTPStatusCode"] != 412:
            raise
        with s3.get_object(**object_id)["Body"] as stored:
            if stored.read() != body:
                raise ValueError("Existing generation object differs from its immutable bundle") from error


def files():
    for generation, definition in ((stable, manifest), (fixture, fixture_manifest)):
        for name in definition["checksums"]:
            yield generation, name, (source / name).read_bytes()
        yield generation, "manifest.json", encoded(definition)


with ThreadPoolExecutor(6) as executor:
    list(executor.map(upload, files()))
openssl = sys.argv[1]
key = work / "alb-key.pem"
cert = work / "alb-cert.pem"
dns = outputs["AlbDns"]
try:
    subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-keyout", str(key), "-out", str(cert), "-subj", "/CN=RankFlow Stage 4",
                    "-addext", f"subjectAltName=DNS:{dns}"], check=True, capture_output=True)
    certificate = aws.client("acm").import_certificate(
        Certificate=cert.read_bytes(), PrivateKey=key.read_bytes(),
        Tags=[{"Key": "project", "Value": "rankflow"}, {"Key": "stage", "Value": "stage4"}],
    )["CertificateArn"]
finally:
    key.unlink(missing_ok=True)
(work / "deployment.json").write_text(json.dumps(
    dict(outputs, Stable=stable, Fixture=fixture, Certificate=certificate), indent=2), encoding="utf-8")
