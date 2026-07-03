"""
Utility Functions

Helper functions for logging, configuration, and DynamoDB operations.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List
from decimal import Decimal


def setup_logging(name: str) -> logging.Logger:
    """
    Setup standardized logging.

    Args:
        name: Logger name

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)

    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def load_config() -> Dict[str, Any]:
    """
    Load configuration from environment variables.

    Returns:
        Configuration dictionary
    """
    config = {
        # Resource scanning
        'ec2_enabled': os.environ.get('EC2_ENABLED', 'true').lower() == 'true',
        'rds_enabled': os.environ.get('RDS_ENABLED', 'true').lower() == 'true',
        'lambda_enabled': os.environ.get('LAMBDA_ENABLED', 'true').lower() == 'true',

        'min_age_days': int(os.environ.get('MIN_AGE_DAYS', '7')),
        'lookback_days': int(os.environ.get('LOOKBACK_DAYS', '30')),
        'min_lambda_invocations': int(os.environ.get('MIN_LAMBDA_INVOCATIONS', '1000')),

        # Exclusion tags
        'exclude_tags': [
            {'Key': 'Optimizer', 'Value': 'Exclude'}
        ],

        'exclude_aurora_serverless': os.environ.get('EXCLUDE_AURORA_SERVERLESS', 'true').lower() == 'true',

        # Bedrock settings
        'bedrock_region': os.environ.get('BEDROCK_REGION', 'us-east-1'),
        'bedrock_model_id': os.environ.get(
            'BEDROCK_MODEL_ID',
            'anthropic.claude-3-5-sonnet-20241022-v2:0'
        ),
        'max_tokens': int(os.environ.get('MAX_TOKENS', '4000')),
        'temperature': float(os.environ.get('TEMPERATURE', '0.2')),
        'confidence_threshold': int(os.environ.get('CONFIDENCE_THRESHOLD', '70')),

        # Storage
        'dynamodb_table_name': os.environ.get('DYNAMODB_TABLE_NAME', 'optimizer-recommendations'),
        's3_bucket_name': os.environ.get('S3_BUCKET_NAME'),

        # Alerting
        'sns_topic_arn': os.environ.get('SNS_TOPIC_ARN'),
        'slack_webhook_url': os.environ.get('SLACK_WEBHOOK_URL'),
        'min_total_savings': float(os.environ.get('MIN_TOTAL_SAVINGS', '100')),

        # AWS settings
        'aws_region': os.environ.get('AWS_REGION', 'us-east-1')
    }

    return config


class DynamoDBStore:
    """DynamoDB operations for recommendation storage and retrieval."""

    def __init__(self, table: Any):
        """
        Initialize DynamoDB store.

        Args:
            table: Boto3 DynamoDB Table resource
        """
        self.table = table
        self.logger = logging.getLogger(__name__)

    def store_recommendation(self, recommendation: Dict[str, Any]) -> bool:
        """
        Store recommendation in DynamoDB.

        Args:
            recommendation: Recommendation data

        Returns:
            True if successful
        """
        try:
            # Convert floats to Decimal for DynamoDB
            item = self._prepare_for_dynamodb(recommendation)

            # Add primary key
            timestamp = recommendation['timestamp']
            resource_id = recommendation['resource_id']

            item['PK'] = f"REC#{timestamp}"
            item['SK'] = f"RESOURCE#{resource_id}"
            item['GSI1PK'] = f"RESOURCE#{resource_id}"  # For querying by resource
            item['GSI1SK'] = timestamp

            self.table.put_item(Item=item)

            self.logger.info(f"Stored recommendation: {resource_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error storing recommendation: {e}")
            return False

    def get_recommendations(
        self,
        resource_id: str = None,
        status: str = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get recommendations from DynamoDB.

        Args:
            resource_id: Optional resource ID filter
            status: Optional status filter (pending, approved, rejected)
            limit: Maximum results

        Returns:
            List of recommendations
        """
        try:
            recommendations = []

            if resource_id:
                # Query by resource
                response = self.table.query(
                    IndexName='GSI1',
                    KeyConditionExpression='GSI1PK = :resource',
                    ExpressionAttributeValues={
                        ':resource': f"RESOURCE#{resource_id}"
                    },
                    Limit=limit,
                    ScanIndexForward=False  # Most recent first
                )
                items = response.get('Items', [])
            else:
                # Scan all (expensive, use carefully)
                response = self.table.scan(Limit=limit)
                items = response.get('Items', [])

            # Convert from DynamoDB format
            for item in items:
                rec = self._prepare_from_dynamodb(item)

                # Apply status filter
                if status and rec.get('status') != status:
                    continue

                recommendations.append(rec)

            return recommendations

        except Exception as e:
            self.logger.error(f"Error retrieving recommendations: {e}")
            return []

    def update_recommendation_status(
        self,
        pk: str,
        sk: str,
        status: str
    ) -> bool:
        """
        Update recommendation status (e.g., approved, rejected, applied).

        Args:
            pk: Primary key
            sk: Sort key
            status: New status

        Returns:
            True if successful
        """
        try:
            self.table.update_item(
                Key={'PK': pk, 'SK': sk},
                UpdateExpression='SET #status = :status, updated_at = :updated',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': status,
                    ':updated': datetime.utcnow().isoformat()
                }
            )

            self.logger.info(f"Updated recommendation {pk}/{sk} to status: {status}")
            return True

        except Exception as e:
            self.logger.error(f"Error updating recommendation status: {e}")
            return False

    def _prepare_for_dynamodb(self, data: Any) -> Any:
        """
        Convert floats to Decimal for DynamoDB storage.

        Args:
            data: Data structure

        Returns:
            DynamoDB-compatible data
        """
        if isinstance(data, dict):
            return {k: self._prepare_for_dynamodb(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._prepare_for_dynamodb(item) for item in data]
        elif isinstance(data, float):
            return Decimal(str(data))
        else:
            return data

    def _prepare_from_dynamodb(self, data: Any) -> Any:
        """
        Convert Decimal back to float from DynamoDB.

        Args:
            data: Data structure

        Returns:
            Python-native data types
        """
        if isinstance(data, dict):
            return {k: self._prepare_from_dynamodb(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._prepare_from_dynamodb(item) for item in data]
        elif isinstance(data, Decimal):
            return float(data)
        else:
            return data


def format_currency(amount: float) -> str:
    """Format amount as currency."""
    return f"${amount:,.2f}"


def calculate_annual_savings(monthly_savings: float) -> float:
    """Calculate annual savings from monthly."""
    return monthly_savings * 12
