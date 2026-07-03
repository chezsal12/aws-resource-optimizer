"""
Metrics Collector

Collects CloudWatch metrics for EC2, RDS, and Lambda resources.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects CloudWatch metrics for resource analysis."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Metrics Collector.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.cloudwatch = boto3.client('cloudwatch')

    def collect_metrics(
        self,
        resource_type: str,
        resource_id: str,
        lookback_days: int = 30
    ) -> Dict[str, Any]:
        """
        Collect metrics for a resource.

        Args:
            resource_type: Type of resource (ec2, rds, lambda)
            resource_id: Resource identifier
            lookback_days: Days of historical data to collect

        Returns:
            Dictionary of metrics and statistics
        """
        if resource_type == 'ec2':
            return self._collect_ec2_metrics(resource_id, lookback_days)
        elif resource_type == 'rds':
            return self._collect_rds_metrics(resource_id, lookback_days)
        elif resource_type == 'lambda':
            return self._collect_lambda_metrics(resource_id, lookback_days)
        else:
            logger.error(f"Unknown resource type: {resource_type}")
            return {'has_data': False}

    def _collect_ec2_metrics(
        self,
        instance_id: str,
        lookback_days: int
    ) -> Dict[str, Any]:
        """
        Collect EC2 instance metrics.

        Args:
            instance_id: EC2 instance ID
            lookback_days: Days of historical data

        Returns:
            EC2 metrics dictionary
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=lookback_days)

        metrics = {
            'has_data': False,
            'resource_type': 'ec2',
            'resource_id': instance_id,
            'period_days': lookback_days
        }

        try:
            # CPU Utilization
            cpu_stats = self._get_metric_statistics(
                namespace='AWS/EC2',
                metric_name='CPUUtilization',
                dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                start_time=start_time,
                end_time=end_time,
                period=3600,  # 1 hour
                statistics=['Average', 'Maximum']
            )

            if cpu_stats:
                metrics['cpu'] = self._calculate_stats(cpu_stats)
                metrics['has_data'] = True

            # Network In
            network_in_stats = self._get_metric_statistics(
                namespace='AWS/EC2',
                metric_name='NetworkIn',
                dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                start_time=start_time,
                end_time=end_time,
                period=3600,
                statistics=['Average', 'Maximum']
            )

            if network_in_stats:
                metrics['network_in'] = self._calculate_stats(network_in_stats)

            # Network Out
            network_out_stats = self._get_metric_statistics(
                namespace='AWS/EC2',
                metric_name='NetworkOut',
                dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                start_time=start_time,
                end_time=end_time,
                period=3600,
                statistics=['Average', 'Maximum']
            )

            if network_out_stats:
                metrics['network_out'] = self._calculate_stats(network_out_stats)

        except Exception as e:
            logger.error(f"Error collecting EC2 metrics for {instance_id}: {e}")

        return metrics

    def _collect_rds_metrics(
        self,
        db_instance_id: str,
        lookback_days: int
    ) -> Dict[str, Any]:
        """
        Collect RDS database metrics.

        Args:
            db_instance_id: RDS instance identifier
            lookback_days: Days of historical data

        Returns:
            RDS metrics dictionary
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=lookback_days)

        metrics = {
            'has_data': False,
            'resource_type': 'rds',
            'resource_id': db_instance_id,
            'period_days': lookback_days
        }

        try:
            # CPU Utilization
            cpu_stats = self._get_metric_statistics(
                namespace='AWS/RDS',
                metric_name='CPUUtilization',
                dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_instance_id}],
                start_time=start_time,
                end_time=end_time,
                period=3600,
                statistics=['Average', 'Maximum']
            )

            if cpu_stats:
                metrics['cpu'] = self._calculate_stats(cpu_stats)
                metrics['has_data'] = True

            # Database Connections
            connections_stats = self._get_metric_statistics(
                namespace='AWS/RDS',
                metric_name='DatabaseConnections',
                dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_instance_id}],
                start_time=start_time,
                end_time=end_time,
                period=3600,
                statistics=['Average', 'Maximum']
            )

            if connections_stats:
                metrics['connections'] = self._calculate_stats(connections_stats)

            # Read IOPS
            read_iops_stats = self._get_metric_statistics(
                namespace='AWS/RDS',
                metric_name='ReadIOPS',
                dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_instance_id}],
                start_time=start_time,
                end_time=end_time,
                period=3600,
                statistics=['Average', 'Maximum']
            )

            if read_iops_stats:
                metrics['read_iops'] = self._calculate_stats(read_iops_stats)

            # Write IOPS
            write_iops_stats = self._get_metric_statistics(
                namespace='AWS/RDS',
                metric_name='WriteIOPS',
                dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_instance_id}],
                start_time=start_time,
                end_time=end_time,
                period=3600,
                statistics=['Average', 'Maximum']
            )

            if write_iops_stats:
                metrics['write_iops'] = self._calculate_stats(write_iops_stats)

        except Exception as e:
            logger.error(f"Error collecting RDS metrics for {db_instance_id}: {e}")

        return metrics

    def _collect_lambda_metrics(
        self,
        function_name: str,
        lookback_days: int
    ) -> Dict[str, Any]:
        """
        Collect Lambda function metrics.

        Args:
            function_name: Lambda function name
            lookback_days: Days of historical data

        Returns:
            Lambda metrics dictionary
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=lookback_days)

        metrics = {
            'has_data': False,
            'resource_type': 'lambda',
            'resource_id': function_name,
            'period_days': lookback_days
        }

        try:
            # Invocations
            invocations_stats = self._get_metric_statistics(
                namespace='AWS/Lambda',
                metric_name='Invocations',
                dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                start_time=start_time,
                end_time=end_time,
                period=86400,  # Daily
                statistics=['Sum']
            )

            if invocations_stats:
                metrics['invocations'] = self._calculate_stats(invocations_stats)
                metrics['has_data'] = True

                # Skip if too few invocations
                total_invocations = sum(
                    dp.get('Sum', 0) for dp in invocations_stats
                )
                min_invocations = self.config.get('min_lambda_invocations', 1000)

                if total_invocations < min_invocations:
                    logger.info(
                        f"Lambda {function_name} has only {total_invocations} "
                        f"invocations, skipping"
                    )
                    return {'has_data': False}

            # Duration
            duration_stats = self._get_metric_statistics(
                namespace='AWS/Lambda',
                metric_name='Duration',
                dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                start_time=start_time,
                end_time=end_time,
                period=3600,
                statistics=['Average', 'Maximum']
            )

            if duration_stats:
                metrics['duration'] = self._calculate_stats(duration_stats)

            # Errors
            errors_stats = self._get_metric_statistics(
                namespace='AWS/Lambda',
                metric_name='Errors',
                dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                start_time=start_time,
                end_time=end_time,
                period=86400,
                statistics=['Sum']
            )

            if errors_stats:
                metrics['errors'] = self._calculate_stats(errors_stats)

            # Throttles
            throttles_stats = self._get_metric_statistics(
                namespace='AWS/Lambda',
                metric_name='Throttles',
                dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                start_time=start_time,
                end_time=end_time,
                period=86400,
                statistics=['Sum']
            )

            if throttles_stats:
                metrics['throttles'] = self._calculate_stats(throttles_stats)

        except Exception as e:
            logger.error(f"Error collecting Lambda metrics for {function_name}: {e}")

        return metrics

    def _get_metric_statistics(
        self,
        namespace: str,
        metric_name: str,
        dimensions: List[Dict[str, str]],
        start_time: datetime,
        end_time: datetime,
        period: int,
        statistics: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Get metric statistics from CloudWatch.

        Args:
            namespace: CloudWatch namespace
            metric_name: Metric name
            dimensions: Metric dimensions
            start_time: Start time
            end_time: End time
            period: Period in seconds
            statistics: List of statistics to retrieve

        Returns:
            List of datapoints
        """
        try:
            response = self.cloudwatch.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=dimensions,
                StartTime=start_time,
                EndTime=end_time,
                Period=period,
                Statistics=statistics
            )

            return response.get('Datapoints', [])

        except ClientError as e:
            logger.error(
                f"Error getting metric {metric_name} from {namespace}: {e}"
            )
            return []

    def _calculate_stats(self, datapoints: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Calculate statistics from datapoints.

        Args:
            datapoints: CloudWatch datapoints

        Returns:
            Statistics dictionary
        """
        if not datapoints:
            return {}

        averages = [dp.get('Average') for dp in datapoints if 'Average' in dp]
        maximums = [dp.get('Maximum') for dp in datapoints if 'Maximum' in dp]
        sums = [dp.get('Sum') for dp in datapoints if 'Sum' in dp]

        stats = {}

        if averages:
            stats['average'] = sum(averages) / len(averages)
            stats['p50'] = sorted(averages)[len(averages) // 2]
            stats['p95'] = sorted(averages)[int(len(averages) * 0.95)]
            stats['p99'] = sorted(averages)[int(len(averages) * 0.99)]

        if maximums:
            stats['max'] = max(maximums)

        if sums:
            stats['total'] = sum(sums)

        return stats
