"""
ComputeStack — EC2 application server.

Instance
  Type:    t3.small
  AMI:     Amazon Linux 2023 (latest)
  Subnet:  Private (behind ALB)
  IAM:     Access S3, SQS, Secrets Manager, SES, Cognito admin
  UserData: Install Docker + Docker Compose
"""
import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from constructs import Construct

from .storage_stack import StorageStack
from .messaging_stack import MessagingStack


class ComputeStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        sg_app: ec2.SecurityGroup,
        storage: StorageStack,
        messaging: MessagingStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------ #
        # IAM Role for EC2                                                     #
        # ------------------------------------------------------------------ #
        role = iam.Role(
            self,
            "AppServerRole",
            role_name="one-system-app-server-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
        )

        # S3 — project buckets only
        for bucket in [
            storage.raw_landing,
            storage.processed_zone,
            storage.attachments,
            storage.exports,
            storage.audit_logs,
        ]:
            bucket.grant_read_write(role)

        # SQS — project queues only
        for queue in [
            messaging.line_webhook_queue,
            messaging.notification_queue,
            messaging.export_queue,
        ]:
            queue.grant_consume_messages(role)
            queue.grant_send_messages(role)

        # Secrets Manager — read DB credentials
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SecretsManagerReadDb",
                actions=["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:/one-system/*"
                ],
            )
        )

        # SES — send email notifications
        role.add_to_policy(
            iam.PolicyStatement(
                sid="SesSendEmail",
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=["*"],
            )
        )

        # Cognito — admin user management
        role.add_to_policy(
            iam.PolicyStatement(
                sid="CognitoAdminActions",
                actions=[
                    "cognito-idp:AdminCreateUser",
                    "cognito-idp:AdminSetUserPassword",
                    "cognito-idp:AdminGetUser",
                    "cognito-idp:AdminUpdateUserAttributes",
                    "cognito-idp:AdminDisableUser",
                    "cognito-idp:AdminEnableUser",
                    "cognito-idp:ListUsers",
                    "cognito-idp:AdminAddUserToGroup",
                    "cognito-idp:AdminRemoveUserFromGroup",
                    "cognito-idp:AdminListGroupsForUser",
                ],
                resources=[
                    f"arn:aws:cognito-idp:{self.region}:{self.account}:userpool/*"
                ],
            )
        )

        # SSM Session Manager (optional but useful for secure shell access)
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
        )

        # ------------------------------------------------------------------ #
        # EC2 User Data — Docker + Docker Compose                             #
        # ------------------------------------------------------------------ #
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "set -eux",
            "dnf update -y",
            "dnf install -y docker",
            "systemctl enable --now docker",
            "usermod -aG docker ec2-user",
            # Docker Compose v2 plugin
            'mkdir -p /usr/local/lib/docker/cli-plugins',
            (
                'curl -SL "https://github.com/docker/compose/releases/latest/download/'
                'docker-compose-linux-x86_64" '
                '-o /usr/local/lib/docker/cli-plugins/docker-compose'
            ),
            "chmod +x /usr/local/lib/docker/cli-plugins/docker-compose",
            # Application directory
            "mkdir -p /opt/one-system",
            "chown ec2-user:ec2-user /opt/one-system",
        )

        # ------------------------------------------------------------------ #
        # EC2 Instance                                                         #
        # ------------------------------------------------------------------ #
        self.instance = ec2.Instance(
            self,
            "AppServer",
            instance_name="one-system-app-server",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.SMALL
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_group=sg_app,
            role=role,
            user_data=user_data,
            user_data_causes_replacement=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        30,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True,
                        delete_on_termination=True,
                    ),
                )
            ],
        )

        # ------------------------------------------------------------------ #
        # Outputs                                                              #
        # ------------------------------------------------------------------ #
        cdk.CfnOutput(
            self,
            "AppServerInstanceId",
            value=self.instance.instance_id,
            export_name="OneSystemAppServerInstanceId",
        )
        cdk.CfnOutput(
            self,
            "AppServerPrivateIp",
            value=self.instance.instance_private_ip,
            export_name="OneSystemAppServerPrivateIp",
        )
        cdk.CfnOutput(
            self,
            "AppServerRoleArn",
            value=role.role_arn,
            export_name="OneSystemAppServerRoleArn",
        )
