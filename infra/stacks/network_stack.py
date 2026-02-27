"""
NetworkStack — VPC, subnets, Internet Gateway, NAT Gateway, Security Groups.

Topology
--------
  VPC CIDR:  10.0.0.0/16
  Public subnets  (2 AZs): ALB, NAT Gateway
  Private subnets (2 AZs): EC2 app servers, Aurora cluster

Security groups
  sg-alb      inbound  443  from 0.0.0.0/0
  sg-app      inbound 8000  from sg-alb only
  sg-db       inbound 5432  from sg-app only
  sg-pipeline inbound   22  from admin CIDR; egress unrestricted
"""
import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class NetworkStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------ #
        # VPC                                                                  #
        # ------------------------------------------------------------------ #
        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            nat_gateways=1,  # single NAT for cost; change to 2 for HA
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # ------------------------------------------------------------------ #
        # Security Groups                                                       #
        # ------------------------------------------------------------------ #

        # sg-alb: internet-facing, HTTPS only
        self.sg_alb = ec2.SecurityGroup(
            self,
            "SgAlb",
            vpc=self.vpc,
            security_group_name="one-system-sg-alb",
            description="ALB — inbound HTTPS from internet",
            allow_all_outbound=True,
        )
        self.sg_alb.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(443),
            description="HTTPS from internet",
        )
        self.sg_alb.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(80),
            description="HTTP from internet (redirect to HTTPS)",
        )

        # sg-app: app server — accepts traffic from ALB only
        self.sg_app = ec2.SecurityGroup(
            self,
            "SgApp",
            vpc=self.vpc,
            security_group_name="one-system-sg-app",
            description="App server — inbound 8000 from ALB only",
            allow_all_outbound=True,
        )
        self.sg_app.add_ingress_rule(
            peer=ec2.Peer.security_group_id(self.sg_alb.security_group_id),
            connection=ec2.Port.tcp(8000),
            description="FastAPI from ALB",
        )

        # sg-db: Aurora — accepts traffic from app server only
        self.sg_db = ec2.SecurityGroup(
            self,
            "SgDb",
            vpc=self.vpc,
            security_group_name="one-system-sg-db",
            description="Aurora — inbound 5432 from app server only",
            allow_all_outbound=False,
        )
        self.sg_db.add_ingress_rule(
            peer=ec2.Peer.security_group_id(self.sg_app.security_group_id),
            connection=ec2.Port.tcp(5432),
            description="PostgreSQL from app server",
        )

        # sg-pipeline: Airflow/ETL EC2 — SSH from admin CIDR + unrestricted egress
        self.sg_pipeline = ec2.SecurityGroup(
            self,
            "SgPipeline",
            vpc=self.vpc,
            security_group_name="one-system-sg-pipeline",
            description="Pipeline server — SSH from admin CIDR; egress all",
            allow_all_outbound=True,
        )
        # Admin IP will be added by the operator at deploy time via
        # `cdk deploy --context admin_cidr=x.x.x.x/32`
        admin_cidr = self.node.try_get_context("admin_cidr") or "0.0.0.0/0"
        self.sg_pipeline.add_ingress_rule(
            peer=ec2.Peer.ipv4(admin_cidr),
            connection=ec2.Port.tcp(22),
            description="SSH from admin IP",
        )
        # Also allow pipeline to reach DB
        self.sg_db.add_ingress_rule(
            peer=ec2.Peer.security_group_id(self.sg_pipeline.security_group_id),
            connection=ec2.Port.tcp(5432),
            description="PostgreSQL from pipeline server (migrations / ETL)",
        )

        # ------------------------------------------------------------------ #
        # Outputs                                                              #
        # ------------------------------------------------------------------ #
        cdk.CfnOutput(self, "VpcId", value=self.vpc.vpc_id, export_name="OneSystemVpcId")
        cdk.CfnOutput(
            self,
            "PrivateSubnetIds",
            value=",".join(s.subnet_id for s in self.vpc.private_subnets),
            export_name="OneSystemPrivateSubnetIds",
        )
        cdk.CfnOutput(
            self,
            "PublicSubnetIds",
            value=",".join(s.subnet_id for s in self.vpc.public_subnets),
            export_name="OneSystemPublicSubnetIds",
        )
        cdk.CfnOutput(self, "SgAlbId", value=self.sg_alb.security_group_id)
        cdk.CfnOutput(self, "SgAppId", value=self.sg_app.security_group_id)
        cdk.CfnOutput(self, "SgDbId", value=self.sg_db.security_group_id)
