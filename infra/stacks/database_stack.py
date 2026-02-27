"""
DatabaseStack — Aurora Serverless v2 (PostgreSQL 15).

Cluster settings
  Engine:    Aurora PostgreSQL 15
  Mode:      Serverless v2  (0.5 – 4 ACU)
  DB name:   one_system
  Subnets:   Private
  Backups:   7-day automated retention
  Credentials stored in Secrets Manager: /one-system/db/credentials
"""
import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_rds as rds
from aws_cdk import aws_secretsmanager as sm
from constructs import Construct


class DatabaseStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        sg_db: ec2.SecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------ #
        # DB credentials (auto-generated, stored in Secrets Manager)          #
        # ------------------------------------------------------------------ #
        self.db_secret = rds.DatabaseSecret(
            self,
            "DbSecret",
            username="postgres",
            secret_name="/one-system/db/credentials",
        )

        # ------------------------------------------------------------------ #
        # Subnet group — private subnets only                                 #
        # ------------------------------------------------------------------ #
        subnet_group = rds.SubnetGroup(
            self,
            "DbSubnetGroup",
            description="one-system Aurora private subnet group",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # ------------------------------------------------------------------ #
        # Aurora Serverless v2 cluster                                        #
        # ------------------------------------------------------------------ #
        self.cluster = rds.DatabaseCluster(
            self,
            "AuroraCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_4
            ),
            cluster_identifier="one-system-aurora",
            default_database_name="one_system",
            credentials=rds.Credentials.from_secret(self.db_secret),
            serverless_v2_min_capacity=0.5,
            serverless_v2_max_capacity=4,
            writer=rds.ClusterInstance.serverless_v2(
                "Writer",
                publicly_accessible=False,
            ),
            # No reader — single writer for this project
            readers=[],
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[sg_db],
            subnet_group=subnet_group,
            backup=rds.BackupProps(retention=cdk.Duration.days(7)),
            deletion_protection=True,
            storage_encrypted=True,
            removal_policy=cdk.RemovalPolicy.SNAPSHOT,
        )

        # ------------------------------------------------------------------ #
        # Outputs                                                              #
        # ------------------------------------------------------------------ #
        cdk.CfnOutput(
            self,
            "ClusterEndpoint",
            value=self.cluster.cluster_endpoint.hostname,
            export_name="OneSystemDbEndpoint",
        )
        cdk.CfnOutput(
            self,
            "DbSecretArn",
            value=self.db_secret.secret_arn,
            export_name="OneSystemDbSecretArn",
        )
        cdk.CfnOutput(
            self,
            "ClusterIdentifier",
            value=self.cluster.cluster_identifier,
            export_name="OneSystemDbClusterIdentifier",
        )
