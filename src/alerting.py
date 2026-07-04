"""
Alerting Module

Sends optimization recommendations via SNS (email) and Slack.
"""

import json
import logging
from typing import Dict, Any, List
from urllib.request import Request, urlopen
from urllib.error import URLError

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class AlertManager:
    """Manages alerting for optimization recommendations."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Alert Manager.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.sns_client = boto3.client('sns')

        # Risk emoji mapping
        self.risk_emojis = {
            'Low': '🟢',
            'Medium': '🟡',
            'High': '🔴'
        }

    def send_optimization_alert(
        self,
        recommendations: List[Dict[str, Any]],
        total_savings: float
    ) -> bool:
        """
        Send optimization recommendations alert.

        Args:
            recommendations: List of recommendations
            total_savings: Total monthly savings

        Returns:
            True if at least one channel succeeded
        """
        results = {'sns': False, 'slack': False}

        # Send SNS alert
        if self.config.get('sns_topic_arn'):
            results['sns'] = self._send_sns_alert(
                recommendations,
                total_savings
            )

        # Send Slack alert
        if self.config.get('slack_webhook_url'):
            results['slack'] = self._send_slack_alert(
                recommendations,
                total_savings
            )

        return results['sns'] or results['slack']

    def _send_sns_alert(
        self,
        recommendations: List[Dict[str, Any]],
        total_savings: float
    ) -> bool:
        """
        Send alert via Amazon SNS (email).

        Args:
            recommendations: List of recommendations
            total_savings: Total monthly savings

        Returns:
            True if successful
        """
        try:
            topic_arn = self.config['sns_topic_arn']

            # Build subject
            subject = (
                f"💰 AWS Optimization Alert: "
                f"{len(recommendations)} opportunities, "
                f"${total_savings:.0f}/month savings"
            )

            # Build body
            body = self._format_email_body(recommendations, total_savings)

            # Publish
            response = self.sns_client.publish(
                TopicArn=topic_arn,
                Subject=subject[:100],
                Message=body
            )

            logger.info(f"SNS alert sent: MessageId={response['MessageId']}")
            return True

        except ClientError as e:
            logger.error(f"SNS send failed: {e}")
            return False
        except KeyError as e:
            logger.error(f"Missing config for SNS: {e}")
            return False

    def _send_slack_alert(
        self,
        recommendations: List[Dict[str, Any]],
        total_savings: float
    ) -> bool:
        """
        Send alert via Slack webhook.

        Args:
            recommendations: List of recommendations
            total_savings: Total monthly savings

        Returns:
            True if successful
        """
        try:
            webhook_url = self.config['slack_webhook_url']

            # Build Slack blocks
            blocks = self._format_slack_blocks(recommendations, total_savings)

            payload = {
                'blocks': blocks,
                'text': f"AWS Optimization Alert: ${total_savings:.0f}/month savings"
            }

            # Send to Slack
            request = Request(
                webhook_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )

            response = urlopen(request, timeout=10)

            if response.status == 200:
                logger.info("Slack alert sent successfully")
                return True
            else:
                logger.warning(f"Slack returned status {response.status}")
                return False

        except URLError as e:
            logger.error(f"Slack webhook failed: {e}")
            return False
        except KeyError as e:
            logger.error(f"Missing config for Slack: {e}")
            return False

    def _format_email_body(
        self,
        recommendations: List[Dict[str, Any]],
        total_savings: float
    ) -> str:
        """Format alert as email body."""

        body = f"""🎯 AWS Resource Optimization Recommendations

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SUMMARY:
• Total Opportunities: {len(recommendations)}
• Potential Monthly Savings: ${total_savings:,.2f}
• Potential Annual Savings: ${total_savings * 12:,.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOP RECOMMENDATIONS:

"""

        # Show top 5 recommendations
        for i, rec in enumerate(recommendations[:5], 1):
            risk_emoji = self.risk_emojis.get(rec.get('risk_assessment', 'Medium'), '🟡')

            body += f"""
{i}. {risk_emoji} {rec['resource_type'].upper()}: {rec['resource_name']}

   Current: {rec['current_config']}
   Recommended: {rec['recommended_config']}

   💰 Savings: ${rec['monthly_savings']:,.2f}/month (${rec['annual_savings']:,.2f}/year)
   🎯 Confidence: {rec['confidence_score']}%
   ⚠️  Risk: {rec.get('risk_assessment', 'Medium')}

   Reasoning: {rec['reasoning']}

   Implementation:
"""
            for step in rec.get('implementation_steps', [])[:3]:
                body += f"   • {step}\n"

        if len(recommendations) > 5:
            body += f"\n... and {len(recommendations) - 5} more opportunities\n"

        body += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NEXT STEPS:
1. Review detailed recommendations in S3
2. Test changes in non-production first
3. Monitor metrics after implementation
4. Update resource tags to track optimizations

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This alert was generated by AWS Smart Resource Right-Sizer
Powered by Amazon Bedrock (Claude Sonnet 4.6)
"""

        return body

    def _format_slack_blocks(
        self,
        recommendations: List[Dict[str, Any]],
        total_savings: float
    ) -> List[Dict[str, Any]]:
        """Format alert as Slack blocks."""

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🎯 Resource Optimization Alert ({len(recommendations)} opportunities)"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*💰 Monthly Savings:*\n${total_savings:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*📅 Annual Savings:*\n${total_savings * 12:,.2f}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*📊 Opportunities:*\n{len(recommendations)}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*⚡ Avg Confidence:*\n{sum(r['confidence_score'] for r in recommendations) / len(recommendations):.0f}%"
                    }
                ]
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Top 3 Recommendations:*"
                }
            }
        ]

        # Add top 3 recommendations
        for i, rec in enumerate(recommendations[:3], 1):
            risk_emoji = self.risk_emojis.get(rec.get('risk_assessment', 'Medium'), '🟡')

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{i}. {risk_emoji} {rec['resource_type'].upper()}: "
                        f"{rec['resource_name']}*\n"
                        f"• *Current:* {rec['current_config']}\n"
                        f"• *Recommended:* {rec['recommended_config']}\n"
                        f"• *Savings:* ${rec['monthly_savings']:,.2f}/month\n"
                        f"• *Confidence:* {rec['confidence_score']}%\n"
                        f"• *Reason:* {rec['reasoning']}"
                    )
                }
            })

        # Add action buttons
        if self.config.get('s3_bucket_name'):
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Full Report"
                        },
                        "url": self._get_report_url(),
                        "style": "primary"
                    }
                ]
            })

        # Footer
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "🤖 Powered by Amazon Bedrock (Claude Sonnet 4.6)"
                }
            ]
        })

        return blocks

    def _get_report_url(self) -> str:
        """Generate S3 report URL."""
        bucket = self.config.get('s3_bucket_name', 'optimizer-reports')
        region = self.config.get('aws_region', 'us-east-1')
        return (
            f"https://s3.console.aws.amazon.com/s3/buckets/{bucket}"
            f"?region={region}&prefix=reports/"
        )
