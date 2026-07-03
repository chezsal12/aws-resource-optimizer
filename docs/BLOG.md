# Building AI-Powered Resource Optimization with Amazon Bedrock

**Author**: Chezsal Kamaray  
**Date**: July 2026  
**Reading Time**: 10 minutes

---

## At a Glance

Most AWS cost optimization tools tell you "this instance is underutilized." We built a system using Amazon Bedrock (Claude 3.5 Sonnet) that tells you "this instance averages 12% CPU with a P95 of 28%, recommend downsizing to m5.2xlarge for $280/month savings with 92% confidence." Open source, production-ready, ~$30/month to run.

**[GitHub Repository →](https://github.com/chezsal12/aws-resource-optimizer)**

---

## The Problem: Generic Recommendations Without Context

Traditional right-sizing tools give you lists like this:

```
⚠️ Optimization Opportunity
EC2 Instance: i-1234567890
Current: m5.4xlarge
Recommendation: Consider downsizing
Reason: Low CPU utilization
```

Now what? Is "low" 10% or 40%? What about peak usage? Will downsizing break production? How much will you actually save?

**What if the tool just told you all of that upfront?**

---

## The Solution: AI-Powered Context-Aware Optimization

Here's what the same recommendation looks like with AI analysis:

```
🎯 Optimization Recommendation: web-server-3

💰 Cost Impact:
• Current: m5.4xlarge ($560/month)
• Recommended: m5.2xlarge ($280/month)
• Savings: $280/month ($3,360/year)

📊 Usage Analysis (30 days):
• CPU Average: 15.2%
• CPU P95: 28.5%
• CPU Max: 42.1%
• Pattern: Consistent low usage with weekend spikes to 35%

🎯 Confidence: 85% (High)

⚠️ Risk: Medium
Weekend traffic creates periodic spikes. Recommendation:
1. Test in staging first
2. Monitor for 2 weeks
3. Configure auto-scaling for weekend peaks

🔧 Implementation:
terraform apply -var="instance_type=m5.2xlarge"

Expected outcome: 50% cost reduction, performance maintained
```

**That's the difference between data and intelligence.**

---

## Architecture: Multi-Source Analysis Pipeline

### High-Level Flow

```
EventBridge (daily trigger)
    ↓
Lambda Orchestrator
    ↓
    ├─→ Resource Scanner (EC2, RDS, Lambda)
    ├─→ CloudWatch Metrics (30-day history)
    ├─→ Compute Optimizer (AWS recommendations)
    ↓
Amazon Bedrock (Claude 3.5 Sonnet)
    ↓
    ├─→ Pattern analysis
    ├─→ Confidence scoring
    ├─→ Risk assessment
    ↓
    ├─→ Slack/SNS Alerts
    ├─→ DynamoDB (recommendation history)
    └─→ S3 (detailed reports)
```

### Why This Architecture?

**Event-Driven**: Daily analysis, not continuous scanning (cost-efficient)  
**Decoupled**: Each component has one job (maintainable)  
**AI-Powered**: Claude correlates multiple signals (accurate)  
**Auditable**: All recommendations stored in DynamoDB (traceable)

---

## Implementation Deep Dive

### 1. Resource Discovery

We don't analyze everything. Filter criteria:

```python
def discover_ec2_instances(self):
    instances = []
    min_age = timedelta(days=7)  # Skip new resources
    
    for instance in ec2.describe_instances():
        # Skip if too new (not enough metrics)
        if instance.launch_time > datetime.now() - min_age:
            continue
        
        # Skip if tagged for exclusion
        if has_tag(instance, 'Optimizer', 'Exclude'):
            continue
        
        # Skip if in exclusion list (prod databases, etc)
        if instance.id in exclusion_list:
            continue
        
        instances.append(instance)
    
    return instances
```

**Why 7 days minimum?** CloudWatch needs enough history to establish patterns. Optimizing based on 2 days of data is risky.

### 2. Metrics Collection (The Foundation)

```python
def collect_ec2_metrics(instance_id, lookback_days=30):
    metrics = {}
    
    # CPU Utilization
    cpu_data = cloudwatch.get_metric_statistics(
        Namespace='AWS/EC2',
        MetricName='CPUUtilization',
        Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
        StartTime=datetime.now() - timedelta(days=lookback_days),
        EndTime=datetime.now(),
        Period=3600,  # Hourly data points
        Statistics=['Average', 'Maximum']
    )
    
    # Calculate percentiles
    averages = [dp['Average'] for dp in cpu_data]
    metrics['cpu'] = {
        'average': mean(averages),
        'p50': percentile(averages, 50),
        'p95': percentile(averages, 95),
        'p99': percentile(averages, 99),
        'max': max(averages)
    }
    
    # Network, Disk I/O, Memory (from CloudWatch Agent)...
    
    return metrics
```

**Why 30 days?** Captures weekly patterns (weekday vs weekend) and monthly cycles (month-end processing). Too short misses patterns, too long is stale.

**Why percentiles?** Average alone is misleading. A server averaging 20% CPU with a P99 of 95% will break if downsized. P95/P99 show real peak behavior.

### 3. The AI Prompt: Structured Context Wins

Bad prompt:
```
This EC2 instance has low CPU. Should we downsize it?
```

Good prompt:
```python
prompt = f"""You are an AWS FinOps expert analyzing resource optimization.

## Resource
- Type: EC2 Instance
- ID: {instance_id}
- Current: {instance_type}
- Monthly Cost: ${monthly_cost}
- Age: {age_days} days

## Usage Metrics (30-Day Window)
### CPU Utilization
- Average: {cpu_avg}%
- P50: {cpu_p50}%
- P95: {cpu_p95}%
- P99: {cpu_p99}%
- Max: {cpu_max}%

### Pattern Analysis
- Baseline (off-hours): {baseline_cpu}%
- Peak (business hours): {peak_cpu}%
- Variability: {std_dev}%

### Network
- Avg Bytes In: {net_in_avg}
- Avg Bytes Out: {net_out_avg}

## Task
Determine if this instance should be right-sized. Respond with JSON:

{{
  "should_optimize": true/false,
  "confidence_score": 0-100,
  "reasoning": "1-2 sentences explaining the recommendation",
  "current_config": "m5.4xlarge",
  "recommended_config": "m5.2xlarge or 'no change'",
  "estimated_monthly_savings": 0.00,
  "risk_assessment": "Low/Medium/High",
  "implementation_steps": ["Step 1", "Step 2"],
  "cloudformation_code": "optional CF snippet"
}}

Guidelines:
- confidence_score >= 70 to recommend
- Consider P95/P99, not just average
- Factor in workload variability
- For CPU < 30% avg AND P95 < 60%, likely over-provisioned
- For bursty workloads (high std_dev), recommend auto-scaling instead

Respond with ONLY the JSON, no other text.
"""
```

**Why JSON output?** Forces structured response, easy to parse, reduces hallucination. Claude is less likely to make up data when constrained to specific fields.

**Why temperature 0.2?** We want consistent, deterministic analysis. High temperature (1.0) produces creative responses that vary run-to-run. For cost optimization, consistency > creativity.

### 4. Confidence Scoring Logic

Claude generates confidence scores, but we validate them:

```python
def validate_confidence(analysis, metrics):
    score = analysis['confidence_score']
    
    # Reduce confidence if limited data
    if metrics['data_points'] < 500:  # < 3 weeks hourly data
        score *= 0.8
    
    # Reduce confidence if high variability
    if metrics['cpu_std_dev'] > 20:  # Bursty workload
        score *= 0.9
    
    # Increase confidence if pattern is clear
    if metrics['cpu_p99'] < 50 and metrics['cpu_avg'] < 20:
        score *= 1.1
    
    # Cap at 100
    return min(score, 100)
```

### 5. Prioritization Algorithm

Not all recommendations are equal:

```python
def prioritize_recommendations(recommendations):
    # Score based on multiple factors
    for rec in recommendations:
        rec['priority_score'] = (
            rec['monthly_savings'] * 0.5 +        # Bigger savings = higher priority
            rec['confidence_score'] * 0.3 +       # Higher confidence = safer
            (100 - risk_score(rec)) * 0.2         # Lower risk = easier
        )
    
    # Sort by priority score
    return sorted(recommendations, key=lambda r: r['priority_score'], reverse=True)
```

---

## Real-World Results

We've been running this in our AWS Organization (150+ accounts) for 2 months.

### Cost Savings

| Month | Opportunities Found | Implemented | Monthly Savings | Notes |
|-------|---------------------|-------------|-----------------|-------|
| Month 1 | 47 | 12 | $2,800 | Focused on high-confidence (>90%) only |
| Month 2 | 32 | 18 | $4,100 | Expanded to medium-confidence (70-89%) |
| **Total** | **79** | **30** | **$6,900/month** | **$82,800/year** |

**Operating cost**: ~$35/month (Lambda + Bedrock + DynamoDB)

**ROI**: 197x

### Alert Quality

**Before** (using AWS Compute Optimizer alone):
- 200+ recommendations/week
- 60% false positives
- Engineers ignored them

**After** (with AI analysis):
- 15-20 recommendations/week
- 92% implemented within 30 days
- Engineers request more frequent runs

### Interesting Findings

**1. Lambda Memory Over-Provisioning is Rampant**
- 68% of Lambda functions configured with more memory than P99 usage
- Average savings: $145/month per function
- Root cause: Developers set memory high "just in case"

**2. RDS Instance Types Rarely Optimized**
- Many customers start with db.r5.4xlarge and never revisit
- 23% of RDS instances analyzed were oversized by 2+ tiers
- Average savings: $1,200/month per instance

**3. Weekend vs Weekday Patterns Matter**
- 40% of recommendations had significant weekend usage drops
- AI correctly identified these as auto-scaling candidates, not static downsizing
- Prevented potential weekend outages

---

## Lessons Learned

### 1. Prompt Engineering is 50% of the Work

Our first prompts were too vague. Claude gave generic responses like "consider downsizing based on metrics." We spent 2 weeks iterating on prompt structure, adding:
- Explicit percentile thresholds
- Pattern analysis instructions
- Risk assessment criteria
- JSON schema validation

**Result**: Recommendation quality improved 3x.

### 2. Temperature Matters More Than You Think

We started with temperature 1.0 (default). Same resource analyzed twice gave different confidence scores (72% vs 85%). Lowered to 0.2 and suddenly scores were consistent ±2%.

**Takeaway**: For analytical workloads, use temperature 0.1-0.3.

### 3. Humans Must Stay in the Loop

We originally planned auto-remediation (AI recommends → Lambda auto-applies). In testing, it nearly terminated a prod database that was "idle" (maintenance window).

**Solution**: AI recommends, humans approve, automation applies.

### 4. Historical Context Reduces False Positives

Initially we only analyzed current metrics. Got recommendations like "downsize this instance" for servers that had just finished a deployment (temporarily idle).

**Fix**: Store recommendations in DynamoDB, check if resource was optimized in past 90 days. If yes, skip.

### 5. CloudWatch Agent is Critical for Lambda

Lambda memory optimization is impossible without CloudWatch Agent or Lambda Insights. The standard CloudWatch metrics don't include actual memory usage, only allocated memory.

**Lesson**: Deploy Lambda Insights on all production functions before using this tool.

---

## Open Source & What's Next

**The code is live**: [github.com/chezsal12/aws-resource-optimizer](https://github.com/chezsal12/aws-resource-optimizer)

### Roadmap

- **Multi-account support**: Analyze entire AWS Organization in one run
- **Cost forecasting**: "At current growth, this instance will need upsizing in 3 months"
- **Auto-apply mode**: Human approves, Lambda executes the change
- **ECS/EKS support**: Kubernetes pod right-sizing
- **DynamoDB optimization**: Switch provisioned tables to on-demand where appropriate
- **Custom integrations**: Jira tickets, ServiceNow, PagerDuty

### Try It Yourself

Deploy in 5 minutes:
```bash
git clone https://github.com/chezsal12/aws-resource-optimizer.git
cd aws-resource-optimizer

# Package and deploy
cd src && pip install -r ../requirements.txt -t . && zip -r ../function.zip .

aws lambda create-function \
  --function-name resource-optimizer \
  --runtime python3.12 \
  --role YOUR_ROLE_ARN \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://../function.zip \
  --timeout 900 \
  --memory-size 1024
```

---

## Conclusion: AI for FinOps, Not Just Features

Everyone's building AI chatbots and copilots. But some of the highest-ROI AI applications are operational: better monitoring, faster optimization, smarter resource management.

**AWS Smart Resource Right-Sizer** is our proof point. $35/month Bedrock spend, $7,000+/month savings, hours recovered from manual analysis.

That's the power of AI in operations.

---

## About the Author

**Chezsal Kamaray** is a Solutions Architect at AWS, focused on emergent technologies and AI/ML. He helps customers build production AI systems that deliver real business value.

**Connect**: [GitHub](https://github.com/chezsal12)

---

## Feedback & Questions

- **GitHub Issues**: [Report bugs, request features, or ask questions](https://github.com/chezsal12/aws-resource-optimizer/issues)

---

*This solution is provided as a sample. Review and test thoroughly before production use.*
