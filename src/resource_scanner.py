"""
Resource Scanner

Discovers EC2, RDS, and Lambda resources eligible for optimization analysis.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class ResourceScanner:
    """Scans AWS account for resources to optimize."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Resource Scanner.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.ec2_client = boto3.client('ec2')
        self.rds_client = boto3.client('rds')
        self.lambda_client = boto3.client('lambda')
        self.pricing_client = boto3.client('pricing', region_name='us-east-1')

    def discover_all_resources(self) -> List[Dict[str, Any]]:
        """
        Discover all resources eligible for optimization.

        Returns:
            List of resource metadata dictionaries
        """
        resources = []

        # Discover EC2 instances
        if self.config.get('ec2_enabled', True):
            try:
                ec2_resources = self.discover_ec2_instances()
                resources.extend(ec2_resources)
                logger.info(f"Discovered {len(ec2_resources)} EC2 instances")
            except Exception as e:
                logger.error(f"Error discovering EC2 instances: {e}")

        # Discover RDS databases
        if self.config.get('rds_enabled', True):
            try:
                rds_resources = self.discover_rds_instances()
                resources.extend(rds_resources)
                logger.info(f"Discovered {len(rds_resources)} RDS instances")
            except Exception as e:
                logger.error(f"Error discovering RDS instances: {e}")

        # Discover Lambda functions
        if self.config.get('lambda_enabled', True):
            try:
                lambda_resources = self.discover_lambda_functions()
                resources.extend(lambda_resources)
                logger.info(f"Discovered {len(lambda_resources)} Lambda functions")
            except Exception as e:
                logger.error(f"Error discovering Lambda functions: {e}")

        return resources

    def discover_ec2_instances(self) -> List[Dict[str, Any]]:
        """
        Discover EC2 instances for analysis.

        Returns:
            List of EC2 instance metadata
        """
        instances = []
        min_age_days = self.config.get('min_age_days', 7)
        cutoff_time = datetime.utcnow() - timedelta(days=min_age_days)

        try:
            response = self.ec2_client.describe_instances(
                Filters=[
                    {'Name': 'instance-state-name', 'Values': ['running']}
                ]
            )

            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    # Skip if too new
                    launch_time = instance['LaunchTime'].replace(tzinfo=None)
                    if launch_time > cutoff_time:
                        continue

                    # Check for exclusion tags
                    if self._should_exclude(instance.get('Tags', [])):
                        continue

                    # Get instance name
                    name = self._get_tag_value(instance.get('Tags', []), 'Name')

                    instances.append({
                        'type': 'ec2',
                        'id': instance['InstanceId'],
                        'name': name or instance['InstanceId'],
                        'instance_type': instance['InstanceType'],
                        'launch_time': instance['LaunchTime'].isoformat(),
                        'availability_zone': instance['Placement']['AvailabilityZone'],
                        'tags': instance.get('Tags', [])
                    })

        except ClientError as e:
            logger.error(f"Error describing EC2 instances: {e}")
            raise

        return instances

    def discover_rds_instances(self) -> List[Dict[str, Any]]:
        """
        Discover RDS database instances for analysis.

        Returns:
            List of RDS instance metadata
        """
        instances = []
        min_age_days = self.config.get('min_age_days', 7)
        cutoff_time = datetime.utcnow() - timedelta(days=min_age_days)
        exclude_aurora_serverless = self.config.get('exclude_aurora_serverless', True)

        try:
            response = self.rds_client.describe_db_instances()

            for db in response['DBInstances']:
                # Skip if too new
                create_time = db['InstanceCreateTime'].replace(tzinfo=None)
                if create_time > cutoff_time:
                    continue

                # Skip Aurora Serverless if configured
                if exclude_aurora_serverless and db['Engine'].startswith('aurora'):
                    if 'ServerlessV2ScalingConfiguration' in db:
                        continue

                # Check for exclusion tags
                if self._should_exclude(db.get('TagList', [])):
                    continue

                instances.append({
                    'type': 'rds',
                    'id': db['DBInstanceIdentifier'],
                    'name': db['DBInstanceIdentifier'],
                    'instance_class': db['DBInstanceClass'],
                    'engine': db['Engine'],
                    'engine_version': db['EngineVersion'],
                    'allocated_storage': db['AllocatedStorage'],
                    'availability_zone': db['AvailabilityZone'],
                    'create_time': db['InstanceCreateTime'].isoformat(),
                    'tags': db.get('TagList', [])
                })

        except ClientError as e:
            logger.error(f"Error describing RDS instances: {e}")
            raise

        return instances

    def discover_lambda_functions(self) -> List[Dict[str, Any]]:
        """
        Discover Lambda functions for analysis.

        Returns:
            List of Lambda function metadata
        """
        functions = []
        min_invocations = self.config.get('min_lambda_invocations', 1000)

        try:
            # Get all functions
            paginator = self.lambda_client.get_paginator('list_functions')

            for page in paginator.paginate():
                for func in page['Functions']:
                    # Check for exclusion tags
                    try:
                        tags_response = self.lambda_client.list_tags(
                            Resource=func['FunctionArn']
                        )
                        tags = [
                            {'Key': k, 'Value': v}
                            for k, v in tags_response.get('Tags', {}).items()
                        ]

                        if self._should_exclude(tags):
                            continue
                    except ClientError:
                        tags = []

                    # Skip if too little usage (check later with CloudWatch)
                    # For now, include all non-excluded functions

                    functions.append({
                        'type': 'lambda',
                        'id': func['FunctionName'],
                        'name': func['FunctionName'],
                        'memory_size': func['MemorySize'],
                        'timeout': func['Timeout'],
                        'runtime': func['Runtime'],
                        'last_modified': func['LastModified'],
                        'tags': tags
                    })

        except ClientError as e:
            logger.error(f"Error listing Lambda functions: {e}")
            raise

        return functions

    def _should_exclude(self, tags: List[Dict[str, str]]) -> bool:
        """
        Check if resource should be excluded based on tags.

        Args:
            tags: Resource tags

        Returns:
            True if should be excluded
        """
        exclude_tags = self.config.get('exclude_tags', [])

        for exclude_tag in exclude_tags:
            for tag in tags:
                if (tag.get('Key') == exclude_tag.get('Key') and
                    tag.get('Value') == exclude_tag.get('Value')):
                    return True

        return False

    def _get_tag_value(self, tags: List[Dict[str, str]], key: str) -> str:
        """
        Get tag value by key.

        Args:
            tags: List of tags
            key: Tag key to find

        Returns:
            Tag value or empty string
        """
        for tag in tags:
            if tag.get('Key') == key:
                return tag.get('Value', '')

        return ''
