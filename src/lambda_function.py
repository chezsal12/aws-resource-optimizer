"""
AWS Smart Resource Right-Sizer - Main Lambda Handler

Orchestrates resource discovery, metrics analysis, AI-powered recommendations,
and alert delivery for cost optimization.
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, List

import boto3

from resource_scanner import ResourceScanner
from metrics_collector import MetricsCollector
from bedrock_analyzer import BedrockAnalyzer
from alerting import AlertManager
from utils import setup_logging, load_config, DynamoDBStore

logger = setup_logging(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for resource optimization analysis.

    Args:
        event: Lambda event (supports dry_run flag)
        context: Lambda context

    Returns:
        Summary of recommendations and savings
    """
    logger.info("Starting AWS Resource Optimizer")

    try:
        # Load configuration
        config = load_config()
        dry_run = event.get('dry_run', False)

        if dry_run:
            logger.info("Running in DRY RUN mode - no alerts will be sent")

        # Initialize components
        scanner = ResourceScanner(config)
        metrics_collector = MetricsCollector(config)
        analyzer = BedrockAnalyzer(config)
        alert_manager = AlertManager(config)

        # Initialize DynamoDB for storing recommendations
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(config['dynamodb_table_name'])
        db_store = DynamoDBStore(table)

        # Step 1: Discover resources
        logger.info("Discovering resources...")
        resources = scanner.discover_all_resources()

        logger.info(f"Found {len(resources)} resources to analyze")

        if not resources:
            logger.info("No resources found to analyze")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'No resources to analyze'})
            }

        # Step 2: Collect metrics and analyze each resource
        recommendations = []

        for resource in resources:
            try:
                recommendation = process_resource(
                    resource,
                    metrics_collector,
                    analyzer,
                    db_store,
                    config
                )

                if recommendation:
                    recommendations.append(recommendation)
                    logger.info(
                        f"Generated recommendation for {resource['id']}: "
                        f"Save ${recommendation['monthly_savings']:.2f}/month"
                    )

            except Exception as e:
                logger.error(f"Error processing {resource['id']}: {e}")
                continue

        # Step 3: Sort by savings potential (highest first)
        recommendations.sort(
            key=lambda x: x['monthly_savings'],
            reverse=True
        )

        # Step 4: Calculate total savings
        total_savings = sum(r['monthly_savings'] for r in recommendations)

        logger.info(
            f"Generated {len(recommendations)} recommendations, "
            f"total savings: ${total_savings:.2f}/month"
        )

        # Step 5: Send alerts (unless dry run)
        if not dry_run and recommendations:
            # Only alert if savings exceed minimum threshold
            min_savings = config.get('min_total_savings', 100)

            if total_savings >= min_savings:
                alert_sent = alert_manager.send_optimization_alert(
                    recommendations,
                    total_savings
                )

                if alert_sent:
                    logger.info("Optimization alert sent successfully")
            else:
                logger.info(
                    f"Total savings ${total_savings:.2f} below threshold "
                    f"${min_savings}, skipping alert"
                )

        # Step 6: Save summary report to S3
        if config.get('s3_bucket_name'):
            save_report_to_s3(
                recommendations,
                total_savings,
                config['s3_bucket_name']
            )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Analysis complete',
                'total_recommendations': len(recommendations),
                'total_monthly_savings': round(total_savings, 2),
                'total_annual_savings': round(total_savings * 12, 2),
                'top_3_opportunities': [
                    {
                        'resource_id': r['resource_id'],
                        'resource_type': r['resource_type'],
                        'monthly_savings': round(r['monthly_savings'], 2),
                        'confidence': r['confidence_score']
                    }
                    for r in recommendations[:3]
                ]
            })
        }

    except Exception as e:
        logger.error(f"Fatal error in lambda_handler: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def process_resource(
    resource: Dict[str, Any],
    metrics_collector: MetricsCollector,
    analyzer: BedrockAnalyzer,
    db_store: DynamoDBStore,
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Process a single resource: collect metrics → AI analysis → store.

    Args:
        resource: Resource metadata
        metrics_collector: Metrics collection component
        analyzer: Bedrock AI analyzer
        db_store: DynamoDB storage
        config: Configuration

    Returns:
        Recommendation dict or None if no optimization needed
    """
    logger.info(f"Processing resource: {resource['id']}")

    # Collect CloudWatch metrics (30-day window)
    metrics = metrics_collector.collect_metrics(
        resource_type=resource['type'],
        resource_id=resource['id'],
        lookback_days=config.get('lookback_days', 30)
    )

    if not metrics or not metrics.get('has_data'):
        logger.warning(f"No metrics data for {resource['id']}, skipping")
        return None

    # Analyze with Bedrock (Claude)
    analysis = analyzer.analyze_resource(
        resource=resource,
        metrics=metrics
    )

    if not analysis or not analysis.get('should_optimize'):
        logger.info(f"No optimization needed for {resource['id']}")
        return None

    # Build recommendation
    recommendation = {
        'resource_id': resource['id'],
        'resource_type': resource['type'],
        'resource_name': resource.get('name', 'Unnamed'),
        'current_config': analysis['current_config'],
        'recommended_config': analysis['recommended_config'],
        'monthly_savings': analysis['estimated_monthly_savings'],
        'annual_savings': analysis['estimated_monthly_savings'] * 12,
        'confidence_score': analysis['confidence_score'],
        'reasoning': analysis['reasoning'],
        'risk_assessment': analysis.get('risk_assessment', 'Low'),
        'implementation_steps': analysis.get('implementation_steps', []),
        'cloudformation_code': analysis.get('cloudformation_code'),
        'timestamp': datetime.utcnow().isoformat(),
        'status': 'pending'
    }

    # Store in DynamoDB
    db_store.store_recommendation(recommendation)

    return recommendation


def save_report_to_s3(
    recommendations: List[Dict[str, Any]],
    total_savings: float,
    bucket_name: str
) -> None:
    """
    Save detailed recommendations report to S3.

    Args:
        recommendations: List of recommendations
        total_savings: Total monthly savings
        bucket_name: S3 bucket name
    """
    try:
        s3_client = boto3.client('s3')

        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')

        report = {
            'generated_at': datetime.utcnow().isoformat(),
            'total_recommendations': len(recommendations),
            'total_monthly_savings': total_savings,
            'total_annual_savings': total_savings * 12,
            'recommendations': recommendations
        }

        # Save JSON report
        json_key = f"reports/{timestamp}-recommendations.json"
        s3_client.put_object(
            Bucket=bucket_name,
            Key=json_key,
            Body=json.dumps(report, indent=2),
            ContentType='application/json'
        )

        logger.info(f"Saved report to s3://{bucket_name}/{json_key}")

    except Exception as e:
        logger.error(f"Failed to save report to S3: {e}")


# Local testing
if __name__ == '__main__':
    # Mock context for local testing
    class MockContext:
        function_name = 'resource-optimizer'
        memory_limit_in_mb = 1024
        invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:resource-optimizer'
        aws_request_id = 'local-test'

    result = lambda_handler({'dry_run': True}, MockContext())
    print(json.dumps(result, indent=2))
