"""
Bedrock Analyzer

Uses Amazon Bedrock (Claude 3.5 Sonnet) to analyze resource metrics
and generate intelligent right-sizing recommendations.
"""

import json
import logging
from typing import Dict, Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class BedrockAnalyzer:
    """AI-powered resource optimization analyzer using Amazon Bedrock."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Bedrock Analyzer.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.bedrock = boto3.client(
            'bedrock-runtime',
            region_name=config.get('bedrock_region', 'us-east-1')
        )
        self.model_id = config.get(
            'bedrock_model_id',
            'anthropic.claude-3-5-sonnet-20241022-v2:0'
        )

    def analyze_resource(
        self,
        resource: Dict[str, Any],
        metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze resource metrics and generate optimization recommendation.

        Args:
            resource: Resource metadata
            metrics: CloudWatch metrics

        Returns:
            Analysis with recommendation or None if no optimization needed
        """
        logger.info(f"Analyzing resource with Bedrock: {resource['id']}")

        try:
            # Build analysis prompt
            prompt = self._build_analysis_prompt(resource, metrics)

            # Call Bedrock
            response = self._invoke_bedrock(prompt)

            # Parse response
            analysis = self._parse_response(response)

            return analysis

        except Exception as e:
            logger.error(f"Bedrock analysis failed for {resource['id']}: {e}")
            return self._fallback_analysis(resource, metrics)

    def _build_analysis_prompt(
        self,
        resource: Dict[str, Any],
        metrics: Dict[str, Any]
    ) -> str:
        """
        Build AI analysis prompt with resource and metrics data.

        Args:
            resource: Resource metadata
            metrics: Metrics data

        Returns:
            Formatted prompt string
        """
        resource_type = resource['type'].upper()

        prompt = f"""You are an AWS FinOps expert specializing in resource optimization. Analyze this {resource_type} resource and provide right-sizing recommendations.

## Resource Information
- Type: {resource_type}
- ID: {resource['id']}
- Name: {resource.get('name', 'Unnamed')}
"""

        # Add resource-specific details
        if resource['type'] == 'ec2':
            prompt += f"""- Instance Type: {resource['instance_type']}
- Availability Zone: {resource['availability_zone']}
"""
        elif resource['type'] == 'rds':
            prompt += f"""- Instance Class: {resource['instance_class']}
- Engine: {resource['engine']}
- Storage: {resource['allocated_storage']} GB
"""
        elif resource['type'] == 'lambda':
            prompt += f"""- Memory: {resource['memory_size']} MB
- Timeout: {resource['timeout']} seconds
- Runtime: {resource['runtime']}
"""

        # Add metrics analysis
        prompt += f"""
## Usage Metrics (Past {metrics.get('period_days', 30)} Days)
"""

        if resource['type'] == 'ec2':
            cpu = metrics.get('cpu', {})
            prompt += f"""
### CPU Utilization
- Average: {cpu.get('average', 0):.1f}%
- P50 (Median): {cpu.get('p50', 0):.1f}%
- P95: {cpu.get('p95', 0):.1f}%
- P99: {cpu.get('p99', 0):.1f}%
- Maximum: {cpu.get('max', 0):.1f}%

### Network
- Network In (Avg): {metrics.get('network_in', {}).get('average', 0):.0f} bytes
- Network Out (Avg): {metrics.get('network_out', {}).get('average', 0):.0f} bytes
"""

        elif resource['type'] == 'rds':
            cpu = metrics.get('cpu', {})
            connections = metrics.get('connections', {})
            prompt += f"""
### CPU Utilization
- Average: {cpu.get('average', 0):.1f}%
- P95: {cpu.get('p95', 0):.1f}%
- Maximum: {cpu.get('max', 0):.1f}%

### Connections
- Average: {connections.get('average', 0):.0f}
- Maximum: {connections.get('max', 0):.0f}

### IOPS
- Read IOPS (Avg): {metrics.get('read_iops', {}).get('average', 0):.0f}
- Write IOPS (Avg): {metrics.get('write_iops', {}).get('average', 0):.0f}
"""

        elif resource['type'] == 'lambda':
            invocations = metrics.get('invocations', {})
            duration = metrics.get('duration', {})
            prompt += f"""
### Invocations
- Total: {invocations.get('total', 0):.0f}
- Average per day: {invocations.get('average', 0):.0f}

### Duration
- Average: {duration.get('average', 0):.0f} ms
- P95: {duration.get('p95', 0):.0f} ms
- Maximum: {duration.get('max', 0):.0f} ms

### Errors & Throttles
- Errors: {metrics.get('errors', {}).get('total', 0):.0f}
- Throttles: {metrics.get('throttles', {}).get('total', 0):.0f}
"""

        # Add analysis instructions
        prompt += """
## Analysis Task

Based on the metrics above, determine if this resource should be optimized. Provide your analysis as a JSON object with the following structure:

```json
{
  "should_optimize": true/false,
  "confidence_score": 0-100,
  "reasoning": "1-2 sentence explanation of the recommendation",
  "current_config": "description of current configuration",
  "recommended_config": "description of recommended configuration",
  "estimated_monthly_savings": 0.00,
  "risk_assessment": "Low/Medium/High",
  "implementation_steps": [
    "Step 1...",
    "Step 2..."
  ],
  "cloudformation_code": "optional CloudFormation snippet for the change"
}
```

**Guidelines:**
- should_optimize: true only if clear optimization opportunity exists
- confidence_score:
  - 90-100: Very consistent low usage, safe to optimize
  - 70-89: Generally low usage, some variation
  - 50-69: Mixed signals, recommend monitoring first
  - <50: Don't recommend optimization
- Only recommend optimization if confidence >= 70
- Consider workload patterns (steady vs bursty)
- Factor in safety margins (don't optimize to exactly P95)
- For EC2/RDS: CPU < 30% avg suggests downsizing
- For Lambda: Duration vs Memory, throttles indicate under-provisioned

Respond with ONLY the JSON object, no additional text.
"""

        return prompt

    def _invoke_bedrock(self, prompt: str) -> Dict[str, Any]:
        """
        Invoke Bedrock API with the analysis prompt.

        Args:
            prompt: Analysis prompt

        Returns:
            Bedrock response
        """
        max_tokens = self.config.get('max_tokens', 4000)
        temperature = self.config.get('temperature', 0.2)

        request_body = {
            'anthropic_version': 'bedrock-2023-05-31',
            'max_tokens': max_tokens,
            'temperature': temperature,
            'messages': [
                {
                    'role': 'user',
                    'content': prompt
                }
            ]
        }

        try:
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )

            response_body = json.loads(response['body'].read())

            return response_body

        except ClientError as e:
            logger.error(f"Bedrock API error: {e}")
            raise

    def _parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse and validate Bedrock response.

        Args:
            response: Raw Bedrock response

        Returns:
            Parsed analysis dictionary
        """
        try:
            # Extract text content
            content = response['content'][0]['text']

            # Try to extract JSON from markdown code blocks
            if '```json' in content:
                start = content.find('```json') + 7
                end = content.find('```', start)
                json_str = content[start:end].strip()
            elif '```' in content:
                start = content.find('```') + 3
                end = content.find('```', start)
                json_str = content[start:end].strip()
            else:
                json_str = content.strip()

            # Parse JSON
            analysis = json.loads(json_str)

            # Validate required fields
            required_fields = [
                'should_optimize',
                'confidence_score',
                'reasoning',
                'current_config',
                'recommended_config',
                'estimated_monthly_savings'
            ]

            for field in required_fields:
                if field not in analysis:
                    logger.warning(f"Missing field in analysis: {field}")
                    return None

            # Apply confidence threshold
            min_confidence = self.config.get('confidence_threshold', 70)
            if analysis['confidence_score'] < min_confidence:
                logger.info(
                    f"Confidence {analysis['confidence_score']}% below "
                    f"threshold {min_confidence}%, skipping recommendation"
                )
                analysis['should_optimize'] = False

            return analysis

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error(f"Error parsing Bedrock response: {e}")
            logger.debug(f"Response content: {response}")
            return None

    def _fallback_analysis(
        self,
        resource: Dict[str, Any],
        metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Provide basic rule-based analysis if Bedrock fails.

        Args:
            resource: Resource metadata
            metrics: Metrics data

        Returns:
            Basic analysis
        """
        logger.info("Using fallback rule-based analysis")

        # Simple rule-based logic
        should_optimize = False
        reasoning = "Bedrock analysis unavailable, using basic rules"

        if resource['type'] == 'ec2':
            cpu_avg = metrics.get('cpu', {}).get('average', 100)
            if cpu_avg < 20:
                should_optimize = True
                reasoning = f"CPU average {cpu_avg:.1f}% is very low"

        elif resource['type'] == 'rds':
            cpu_avg = metrics.get('cpu', {}).get('average', 100)
            if cpu_avg < 25:
                should_optimize = True
                reasoning = f"CPU average {cpu_avg:.1f}% is very low"

        elif resource['type'] == 'lambda':
            # Lambda is harder to analyze without AI
            should_optimize = False

        return {
            'should_optimize': should_optimize,
            'confidence_score': 50,  # Low confidence for fallback
            'reasoning': reasoning,
            'current_config': f"{resource.get('instance_type', 'Current config')}",
            'recommended_config': "Manual analysis recommended",
            'estimated_monthly_savings': 0.0,
            'risk_assessment': 'Medium',
            'implementation_steps': ['Manual review required'],
            'cloudformation_code': None
        }
