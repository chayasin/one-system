#!/usr/bin/env python3
"""
Rural Roads One System — CDK App Entry Point

Usage:
  1. Copy .env.example to .env at the repo root and fill in all values.
  2. From the infra/ directory:
       pip install -r requirements.txt
       cdk bootstrap aws://ACCOUNT_ID/REGION
       cdk deploy --all
"""
import os
import sys

import aws_cdk as cdk
from dotenv import load_dotenv

# Load .env from repo root (one level up from infra/)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# ---------------------------------------------------------------------------
# Resolve required configuration
# ---------------------------------------------------------------------------

def _require(key: str) -> str:
    val = os.environ.get(key, "")
    if not val:
        print(f"ERROR: Required environment variable '{key}' is not set.", file=sys.stderr)
        print("       Copy .env.example → .env and fill in all values.", file=sys.stderr)
        sys.exit(1)
    return val


AWS_ACCOUNT_ID = _require("AWS_ACCOUNT_ID")
AWS_REGION = _require("AWS_REGION")
APP_DOMAIN = os.environ.get("APP_DOMAIN", "")          # Optional until deploy
ACM_CERT_ARN = os.environ.get("ACM_CERTIFICATE_ARN", "")  # Optional until deploy
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

env = cdk.Environment(account=AWS_ACCOUNT_ID, region=AWS_REGION)

# ---------------------------------------------------------------------------
# Import stacks after env is validated to avoid import-time errors
# ---------------------------------------------------------------------------
from stacks.network_stack import NetworkStack
from stacks.database_stack import DatabaseStack
from stacks.storage_stack import StorageStack
from stacks.auth_stack import AuthStack
from stacks.messaging_stack import MessagingStack
from stacks.compute_stack import ComputeStack
from stacks.cdn_stack import CdnStack

app = cdk.App()

prefix = "OneSystem"

# 1. Network (VPC, subnets, security groups)
network = NetworkStack(app, f"{prefix}Network", env=env)

# 2. Database (Aurora Serverless v2 PostgreSQL)
database = DatabaseStack(
    app,
    f"{prefix}Database",
    vpc=network.vpc,
    sg_db=network.sg_db,
    env=env,
)

# 3. Storage (S3 buckets)
storage = StorageStack(app, f"{prefix}Storage", env=env)

# 4. Auth (Cognito User Pool)
auth = AuthStack(app, f"{prefix}Auth", env=env)

# 5. Messaging (SQS queues)
messaging = MessagingStack(app, f"{prefix}Messaging", env=env)

# 6. Compute (EC2 app server)
compute = ComputeStack(
    app,
    f"{prefix}Compute",
    vpc=network.vpc,
    sg_app=network.sg_app,
    storage=storage,
    messaging=messaging,
    env=env,
)

# 7. CDN (ALB + CloudFront + WAF)  — requires domain + cert
cdn = CdnStack(
    app,
    f"{prefix}Cdn",
    vpc=network.vpc,
    sg_alb=network.sg_alb,
    app_instance=compute.instance,
    app_domain=APP_DOMAIN,
    acm_cert_arn=ACM_CERT_ARN,
    env=env,
)

# Ordering: database + storage + auth + messaging must be ready before compute
compute.add_dependency(database)
compute.add_dependency(storage)
compute.add_dependency(auth)
compute.add_dependency(messaging)
cdn.add_dependency(compute)

cdk.Tags.of(app).add("Project", "one-system")
cdk.Tags.of(app).add("Environment", ENVIRONMENT)

app.synth()
