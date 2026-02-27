"""
MessagingStack — SQS queues with Dead-Letter Queues.

Queues
  line-webhook-queue    Buffer LINE OA webhook events       visibility 300 s   DLQ maxReceive 3
  notification-queue    Async in-app / email / LINE push    visibility  60 s   DLQ maxReceive 3
  export-queue          Async CSV / Excel / PDF jobs        visibility 600 s   DLQ maxReceive 3

All queues are SSE-encrypted with SQS-managed keys.
"""
import aws_cdk as cdk
from aws_cdk import aws_sqs as sqs
from constructs import Construct


def _make_queue_pair(
    scope: Construct,
    logical_id: str,
    queue_name: str,
    visibility_timeout: cdk.Duration,
    retention: cdk.Duration = cdk.Duration.days(14),
) -> sqs.Queue:
    """Create a standard queue with an attached DLQ (max 3 receives)."""
    dlq = sqs.Queue(
        scope,
        f"{logical_id}Dlq",
        queue_name=f"{queue_name}-dlq",
        encryption=sqs.QueueEncryption.SQS_MANAGED,
        retention_period=cdk.Duration.days(14),
    )
    queue = sqs.Queue(
        scope,
        logical_id,
        queue_name=queue_name,
        encryption=sqs.QueueEncryption.SQS_MANAGED,
        visibility_timeout=visibility_timeout,
        retention_period=retention,
        dead_letter_queue=sqs.DeadLetterQueue(
            max_receive_count=3,
            queue=dlq,
        ),
    )
    return queue


class MessagingStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------ #
        # Queues                                                               #
        # ------------------------------------------------------------------ #
        self.line_webhook_queue = _make_queue_pair(
            self,
            "LineWebhookQueue",
            "one-system-line-webhook",
            visibility_timeout=cdk.Duration.seconds(300),
        )

        self.notification_queue = _make_queue_pair(
            self,
            "NotificationQueue",
            "one-system-notification",
            visibility_timeout=cdk.Duration.seconds(60),
        )

        self.export_queue = _make_queue_pair(
            self,
            "ExportQueue",
            "one-system-export",
            visibility_timeout=cdk.Duration.seconds(600),
        )

        # ------------------------------------------------------------------ #
        # Outputs                                                              #
        # ------------------------------------------------------------------ #
        cdk.CfnOutput(
            self,
            "LineWebhookQueueUrl",
            value=self.line_webhook_queue.queue_url,
            export_name="OneSystemLineWebhookQueueUrl",
        )
        cdk.CfnOutput(
            self,
            "NotificationQueueUrl",
            value=self.notification_queue.queue_url,
            export_name="OneSystemNotificationQueueUrl",
        )
        cdk.CfnOutput(
            self,
            "ExportQueueUrl",
            value=self.export_queue.queue_url,
            export_name="OneSystemExportQueueUrl",
        )
        cdk.CfnOutput(
            self,
            "LineWebhookQueueArn",
            value=self.line_webhook_queue.queue_arn,
            export_name="OneSystemLineWebhookQueueArn",
        )
        cdk.CfnOutput(
            self,
            "NotificationQueueArn",
            value=self.notification_queue.queue_arn,
            export_name="OneSystemNotificationQueueArn",
        )
        cdk.CfnOutput(
            self,
            "ExportQueueArn",
            value=self.export_queue.queue_arn,
            export_name="OneSystemExportQueueArn",
        )
