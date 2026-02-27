"""
AuthStack — AWS Cognito User Pool.

Configuration
  Pool name:           one-system-users
  Sign-in attribute:   email
  Self-registration:   disabled (admin creates users only)
  MFA:                 OPTIONAL (admin-configurable)
  App client:          one-system-web (no secret — SPA)
  Token expiry:        Access 1 h  |  Refresh 30 d
  Groups:              ADMIN | DISPATCHER | OFFICER | EXECUTIVE
"""
import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito
from constructs import Construct


class AuthStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------ #
        # User Pool                                                            #
        # ------------------------------------------------------------------ #
        self.user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name="one-system-users",
            # Sign-in with email only
            sign_in_aliases=cognito.SignInAliases(email=True),
            sign_in_case_sensitive=False,
            # Admin creates users — no self-registration
            self_sign_up_enabled=False,
            # Account recovery via email
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            # Standard attributes
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
                fullname=cognito.StandardAttribute(required=False, mutable=True),
            ),
            # Password policy (Cognito defaults)
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_digits=True,
                require_lowercase=True,
                require_uppercase=True,
                require_symbols=True,
                temp_password_validity=cdk.Duration.days(7),
            ),
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(sms=False, otp=True),
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # ------------------------------------------------------------------ #
        # App Client (SPA — no client secret)                                 #
        # ------------------------------------------------------------------ #
        self.app_client = self.user_pool.add_client(
            "WebClient",
            user_pool_client_name="one-system-web",
            generate_secret=False,  # SPA cannot keep a secret
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
                admin_user_password=True,
            ),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                    implicit_code_grant=False,
                ),
                scopes=[
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.PROFILE,
                ],
            ),
            access_token_validity=cdk.Duration.hours(1),
            refresh_token_validity=cdk.Duration.days(30),
            id_token_validity=cdk.Duration.hours(1),
            enable_token_revocation=True,
            prevent_user_existence_errors=True,
        )

        # ------------------------------------------------------------------ #
        # Groups (roles)                                                       #
        # ------------------------------------------------------------------ #
        for group_name, description in [
            ("ADMIN", "System administrators — full access"),
            ("DISPATCHER", "Dispatchers — verify and assign cases"),
            ("OFFICER", "Officers — handle assigned cases"),
            ("EXECUTIVE", "Executives — read-only dashboard and exports"),
        ]:
            cognito.CfnUserPoolGroup(
                self,
                f"Group{group_name.title()}",
                user_pool_id=self.user_pool.user_pool_id,
                group_name=group_name,
                description=description,
            )

        # ------------------------------------------------------------------ #
        # Outputs                                                              #
        # ------------------------------------------------------------------ #
        cdk.CfnOutput(
            self,
            "UserPoolId",
            value=self.user_pool.user_pool_id,
            export_name="OneSystemUserPoolId",
        )
        cdk.CfnOutput(
            self,
            "AppClientId",
            value=self.app_client.user_pool_client_id,
            export_name="OneSystemAppClientId",
        )
        cdk.CfnOutput(
            self,
            "UserPoolArn",
            value=self.user_pool.user_pool_arn,
            export_name="OneSystemUserPoolArn",
        )
