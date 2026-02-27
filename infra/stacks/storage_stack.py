"""
StorageStack — S3 buckets with lifecycle policies, encryption, and access controls.

Buckets
  s3-raw-landing       Raw JSON from LINE / 1146               3-year retention
  s3-processed-zone    ETL processed output                    3-year retention
  s3-attachments       Case image attachments                  3-year retention
  s3-exports           CSV / Excel / PDF exports               7-day lifecycle expire
  s3-audit-logs        Immutable audit log (Object Lock)       3-year retention
"""
import aws_cdk as cdk
from aws_cdk import aws_s3 as s3
from constructs import Construct

THREE_YEARS = cdk.Duration.days(365 * 3)
SEVEN_DAYS = cdk.Duration.days(7)


def _base_bucket(
    scope,
    construct_id: str,
    bucket_name_suffix: str,
    removal_policy: cdk.RemovalPolicy = cdk.RemovalPolicy.RETAIN,
) -> s3.Bucket:
    """Helper to build a standard encrypted, private S3 bucket."""
    return s3.Bucket(
        scope,
        construct_id,
        bucket_name=f"one-system-{bucket_name_suffix}-{cdk.Aws.ACCOUNT_ID}",
        encryption=s3.BucketEncryption.S3_MANAGED,
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        enforce_ssl=True,
        versioned=False,
        removal_policy=removal_policy,
    )


class StorageStack(cdk.Stack):
    def __init__(self, scope, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------ #
        # s3-raw-landing                                                       #
        # ------------------------------------------------------------------ #
        self.raw_landing = _base_bucket(self, "RawLanding", "raw-landing")
        self.raw_landing.add_lifecycle_rule(
            id="ExpireAfter3Years",
            expiration=THREE_YEARS,
            enabled=True,
        )

        # ------------------------------------------------------------------ #
        # s3-processed-zone                                                    #
        # ------------------------------------------------------------------ #
        self.processed_zone = _base_bucket(self, "ProcessedZone", "processed-zone")
        self.processed_zone.add_lifecycle_rule(
            id="ExpireAfter3Years",
            expiration=THREE_YEARS,
            enabled=True,
        )

        # ------------------------------------------------------------------ #
        # s3-attachments                                                       #
        # ------------------------------------------------------------------ #
        self.attachments = _base_bucket(self, "Attachments", "attachments")
        self.attachments.add_lifecycle_rule(
            id="ExpireAfter3Years",
            expiration=THREE_YEARS,
            enabled=True,
        )

        # ------------------------------------------------------------------ #
        # s3-exports  (7-day auto-expire)                                      #
        # ------------------------------------------------------------------ #
        self.exports = _base_bucket(
            self,
            "Exports",
            "exports",
            removal_policy=cdk.RemovalPolicy.DESTROY,  # safe — short-lived objects
        )
        self.exports.add_lifecycle_rule(
            id="ExpireAfter7Days",
            expiration=SEVEN_DAYS,
            enabled=True,
        )

        # ------------------------------------------------------------------ #
        # s3-audit-logs  (Object Lock — Compliance mode, 3-year retention)    #
        # ------------------------------------------------------------------ #
        # Object Lock must be enabled at bucket creation; CDK L1 used here.
        audit_cfn = s3.CfnBucket(
            self,
            "AuditLogsCfn",
            bucket_name=f"one-system-audit-logs-{cdk.Aws.ACCOUNT_ID}",
            object_lock_enabled=True,
            object_lock_configuration=s3.CfnBucket.ObjectLockConfigurationProperty(
                object_lock_enabled="Enabled",
                rule=s3.CfnBucket.ObjectLockRuleProperty(
                    default_retention=s3.CfnBucket.DefaultRetentionProperty(
                        mode="COMPLIANCE",
                        years=3,
                    )
                ),
            ),
            bucket_encryption=s3.CfnBucket.BucketEncryptionProperty(
                server_side_encryption_configuration=[
                    s3.CfnBucket.ServerSideEncryptionRuleProperty(
                        server_side_encryption_by_default=s3.CfnBucket.ServerSideEncryptionByDefaultProperty(
                            sse_algorithm="AES256"
                        )
                    )
                ]
            ),
            public_access_block_configuration=s3.CfnBucket.PublicAccessBlockConfigurationProperty(
                block_public_acls=True,
                block_public_policy=True,
                ignore_public_acls=True,
                restrict_public_buckets=True,
            ),
            versioning_configuration=s3.CfnBucket.VersioningConfigurationProperty(
                status="Enabled"
            ),
            lifecycle_configuration=s3.CfnBucket.LifecycleConfigurationProperty(
                rules=[
                    s3.CfnBucket.RuleProperty(
                        id="RetainFor3Years",
                        status="Enabled",
                        expiration_in_days=365 * 3,
                    )
                ]
            ),
        )
        audit_cfn.apply_removal_policy(cdk.RemovalPolicy.RETAIN)
        # Wrap CfnBucket in an L2 reference for IAM grant helpers
        self.audit_logs = s3.Bucket.from_bucket_name(
            self,
            "AuditLogs",
            audit_cfn.ref,
        )

        # ------------------------------------------------------------------ #
        # Outputs                                                              #
        # ------------------------------------------------------------------ #
        for name, bucket in [
            ("RawLandingBucket", self.raw_landing),
            ("ProcessedZoneBucket", self.processed_zone),
            ("AttachmentsBucket", self.attachments),
            ("ExportsBucket", self.exports),
        ]:
            cdk.CfnOutput(self, name, value=bucket.bucket_name, export_name=f"OneSystem{name}")

        cdk.CfnOutput(
            self,
            "AuditLogsBucket",
            value=audit_cfn.ref,
            export_name="OneSystemAuditLogsBucket",
        )
