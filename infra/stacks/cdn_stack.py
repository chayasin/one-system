"""
CdnStack — Application Load Balancer + CloudFront distribution + WAF Web ACL.

ALB
  Listeners:
    HTTP:80   → redirect to HTTPS
    HTTPS:443 → target group (EC2:8000)  [requires ACM cert]
  Health check: GET /health → 200

CloudFront
  Origins:
    /api/*    → ALB (no cache)
    /*        → S3 frontend static files bucket (to be wired in Phase 4)
  HTTPS only
  Price class: PriceClass.PRICE_CLASS_ALL (configurable)

WAF
  AWS Managed rules: AWSManagedRulesCommonRuleSet, AWSManagedRulesKnownBadInputsRuleSet
  Custom: rate limit 2000 req/5 min per IP

Note: ACM_CERT_ARN must be in us-east-1 for CloudFront, and in AWS_REGION for ALB.
      Pass empty strings to skip HTTPS wiring (HTTP only for local testing).
"""
import aws_cdk as cdk
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cf
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_wafv2 as waf
from constructs import Construct


class CdnStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        sg_alb: ec2.SecurityGroup,
        app_instance: ec2.Instance,
        app_domain: str,
        acm_cert_arn: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------ #
        # Application Load Balancer                                            #
        # ------------------------------------------------------------------ #
        self.alb = elbv2.ApplicationLoadBalancer(
            self,
            "Alb",
            load_balancer_name="one-system-alb",
            vpc=vpc,
            internet_facing=True,
            security_group=sg_alb,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        # Target group → EC2 port 8000
        target_group = elbv2.ApplicationTargetGroup(
            self,
            "AppTargetGroup",
            target_group_name="one-system-app-tg",
            vpc=vpc,
            port=8000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[elbv2.InstanceTarget(app_instance.instance_id, port=8000)],
            health_check=elbv2.HealthCheck(
                path="/health",
                healthy_http_codes="200",
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
            deregistration_delay=cdk.Duration.seconds(30),
        )

        # HTTP listener — redirect to HTTPS
        self.alb.add_listener(
            "HttpListener",
            port=80,
            default_action=elbv2.ListenerAction.redirect(
                port="443",
                protocol="HTTPS",
                permanent=True,
            ),
        )

        # HTTPS listener (only when cert is provided)
        if acm_cert_arn:
            cert = acm.Certificate.from_certificate_arn(
                self, "AlbCert", acm_cert_arn
            )
            self.alb.add_listener(
                "HttpsListener",
                port=443,
                certificates=[elbv2.ListenerCertificate.from_arn(cert.certificate_arn)],
                default_target_groups=[target_group],
                ssl_policy=elbv2.SslPolicy.RECOMMENDED_TLS,
            )
        else:
            # Fallback: HTTP-only (no TLS) for local/staging environments
            self.alb.add_listener(
                "HttpsListenerFallback",
                port=443,
                default_target_groups=[target_group],
            )

        # ------------------------------------------------------------------ #
        # WAF Web ACL (CloudFront scope = us-east-1)                          #
        # WAF for ALB uses REGIONAL scope — create separately.                 #
        # ------------------------------------------------------------------ #
        # CloudFront WAF must be in us-east-1 — use a CfnWebACL directly.
        waf_acl = waf.CfnWebACL(
            self,
            "WafAcl",
            name="one-system-waf",
            scope="CLOUDFRONT",
            default_action=waf.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="one-system-waf",
                sampled_requests_enabled=True,
            ),
            rules=[
                # AWS Managed: Common Rule Set (OWASP top 10)
                waf.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCommonRuleSet",
                    priority=10,
                    override_action=waf.CfnWebACL.OverrideActionProperty(none={}),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="AWSManagedRulesCommonRuleSet",
                        sampled_requests_enabled=True,
                    ),
                    statement=waf.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesCommonRuleSet",
                        )
                    ),
                ),
                # AWS Managed: Known Bad Inputs
                waf.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesKnownBadInputsRuleSet",
                    priority=20,
                    override_action=waf.CfnWebACL.OverrideActionProperty(none={}),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="AWSManagedRulesKnownBadInputsRuleSet",
                        sampled_requests_enabled=True,
                    ),
                    statement=waf.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesKnownBadInputsRuleSet",
                        )
                    ),
                ),
                # Custom: rate limit 2000 requests / 5 minutes per IP
                waf.CfnWebACL.RuleProperty(
                    name="RateLimitPerIp",
                    priority=30,
                    action=waf.CfnWebACL.RuleActionProperty(block={}),
                    visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="RateLimitPerIp",
                        sampled_requests_enabled=True,
                    ),
                    statement=waf.CfnWebACL.StatementProperty(
                        rate_based_statement=waf.CfnWebACL.RateBasedStatementProperty(
                            limit=2000,
                            aggregate_key_type="IP",
                        )
                    ),
                ),
            ],
        )

        # ------------------------------------------------------------------ #
        # CloudFront Distribution                                              #
        # ------------------------------------------------------------------ #
        cf_cert = None
        if acm_cert_arn:
            cf_cert = cf.Certificate.from_certificate_arn(
                self, "CfCert", acm_cert_arn
            )

        self.distribution = cf.Distribution(
            self,
            "Distribution",
            comment="one-system CloudFront",
            # API origin → ALB (no caching)
            default_behavior=cf.BehaviorOptions(
                origin=origins.LoadBalancerV2Origin(
                    self.alb,
                    protocol_policy=cf.OriginProtocolPolicy.HTTPS_ONLY
                    if acm_cert_arn
                    else cf.OriginProtocolPolicy.HTTP_ONLY,
                    http_port=80,
                    https_port=443,
                ),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cf.CachePolicy.CACHING_DISABLED,
                allowed_methods=cf.AllowedMethods.ALLOW_ALL,
                origin_request_policy=cf.OriginRequestPolicy.ALL_VIEWER,
            ),
            domain_names=[app_domain] if app_domain else None,
            certificate=cf_cert,
            http_version=cf.HttpVersion.HTTP2_AND_3,
            minimum_protocol_version=cf.SecurityPolicyProtocol.TLS_V1_2_2021,
            price_class=cf.PriceClass.PRICE_CLASS_ALL,
            web_acl_id=waf_acl.attr_arn,
            enable_logging=True,
        )

        # ------------------------------------------------------------------ #
        # Outputs                                                              #
        # ------------------------------------------------------------------ #
        cdk.CfnOutput(self, "AlbDnsName", value=self.alb.load_balancer_dns_name, export_name="OneSystemAlbDnsName")
        cdk.CfnOutput(self, "CloudFrontDomain", value=self.distribution.distribution_domain_name, export_name="OneSystemCfDomain")
        cdk.CfnOutput(self, "CloudFrontDistributionId", value=self.distribution.distribution_id, export_name="OneSystemCfDistributionId")
