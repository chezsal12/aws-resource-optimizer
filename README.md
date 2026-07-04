# AWS Smart Resource Right-Sizer 🎯💰

**AI-Powered Resource Optimization with Amazon Bedrock**

Automatically analyze CloudWatch metrics and get intelligent right-sizing recommendations for EC2, RDS, and Lambda resources using Claude 3.5 Sonnet. Stop overpaying for unused capacity.

[![License: MIT-0](https://img.shields.io/badge/License-MIT--0-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![AWS](https://img.shields.io/badge/AWS-Bedrock%20%7C%20CloudWatch%20%7C%20Compute%20Optimizer-orange.svg)](https://aws.amazon.com/)

> **Note**: This is a sample project for demonstration purposes. Review and test thoroughly before using in production.

---

## 🌟 What Makes This Different?

**Traditional Right-Sizing Tools:**
- ❌ Generic recommendations based on simple thresholds
- ❌ No context about workload patterns
- ❌ Overwhelming lists with no prioritization
- ❌ Technical jargon only engineers understand

**Smart Resource Right-Sizer:**
- ✅ AI analyzes 30-day usage patterns and workload characteristics
- ✅ Understands peak vs baseline, seasonal patterns, growth trends
- ✅ Prioritizes by potential savings (biggest wins first)
- ✅ Executive summaries: "This RDS instance is 85% idle, save $4,200/year"
- ✅ Confidence scores: "High confidence" vs "Monitor first"
- ✅ Auto-generates Terraform/CloudFormation for changes

---

## 🏗️ Architecture

```
EventBridge (daily) → Lambda Orchestrator
                         ↓
              ┌──────────┴──────────┐
              │                     │
         Resource Scanner      Metrics Collector
         • EC2 instances      • CloudWatch (30 days)
         • RDS databases      • CPU, Memory, IOPS
         • Lambda functions   • Network, Invocations
                                    │
                              ┌─────┴─────┐
                              │  Bedrock  │
                              │  Claude   │
                              │  3.5      │
                              └─────┬─────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                 DynamoDB        S3 Reports      SNS/Slack
              (recommendations)  (detailed)      (alerts)
```

---

## 💡 Example Output

### Slack Alert
```
🎯 Resource Optimization Recommendations (15 opportunities)

💰 Total Potential Savings: $8,450/month

Top 3 Recommendations:

1. 🔴 RDS Instance: prod-database-1
   • Current: db.r5.4xlarge ($2,920/mo)
   • Recommended: db.r5.2xlarge ($1,460/mo)
   • Savings: $1,460/month (50%)
   • Confidence: High (95%)
   • Reason: CPU avg 12%, max 28% over 30 days
   
2. 🟡 EC2 Instance: web-server-3
   • Current: m5.4xlarge ($560/mo)
   • Recommended: m5.2xlarge ($280/mo)
   • Savings: $280/month (50%)
   • Confidence: Medium (75%)
   • Reason: Consistent low usage, but weekend spikes to 65%
   
3. 🟢 Lambda Function: data-processor
   • Current: 3GB memory
   • Recommended: 1GB memory
   • Savings: $145/month (67%)
   • Confidence: High (92%)
   • Reason: Peak memory usage 850MB, over-provisioned

[View Full Report] [Apply Changes]
```

---

## 🚀 Quick Start

> **Using AWS Organizations?** See our [Multi-Account Deployment Guide](docs/MULTI_ACCOUNT_DEPLOYMENT.md) for cross-account optimization.

### Prerequisites

- AWS Account with Bedrock enabled
- AWS CLI configured
- Python 3.12+
- Permissions: EC2, RDS, Lambda, CloudWatch, Compute Optimizer, Bedrock

### 1-Click Deploy (CloudFormation)

```bash
# Clone repository
git clone https://github.com/chezsal12/aws-resource-optimizer.git
cd aws-resource-optimizer

# Deploy stack
aws cloudformation deploy \
  --template-file cloudformation/deployment-template.yaml \
  --stack-name resource-optimizer \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    AlertEmail=your-email@example.com \
    ScheduleExpression="rate(1 day)"
```

### Manual Deploy

```bash
# Install dependencies
cd src
pip install -r ../requirements.txt -t .

# Create deployment package
zip -r ../function.zip .

# Create Lambda function
aws lambda create-function \
  --function-name resource-optimizer \
  --runtime python3.12 \
  --role arn:aws:iam::YOUR_ACCOUNT:role/OptimizerRole \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://../function.zip \
  --timeout 900 \
  --memory-size 1024
```

---

## 🎯 How It Works

### 1. Resource Discovery
Scans your AWS account for:
- **EC2**: Running instances with age > 7 days
- **RDS**: Database instances (excludes Aurora Serverless)
- **Lambda**: Functions with > 1000 invocations/month

### 2. Metrics Analysis (30-Day Window)
For each resource, collects:
- **CPU Utilization**: Average, P50, P95, P99, Max
- **Memory Usage**: Average, peak, trends
- **Network**: Bytes in/out, packet rates
- **Disk I/O**: Read/write IOPS, throughput
- **Lambda**: Duration, memory used, invocation patterns

### 3. AI-Powered Analysis
Claude analyzes:
- Usage patterns (baseline vs peaks)
- Workload characteristics (steady vs bursty)
- Growth trends (increasing or stable)
- Cost vs performance trade-offs

Generates:
- Right-sized recommendation
- Confidence score (based on pattern consistency)
- Savings estimate (monthly & annual)
- Risk assessment (performance impact)
- Migration steps (CloudFormation code)

### 4. Prioritization
Recommendations sorted by:
1. **Potential savings** (highest first)
2. **Confidence score** (higher = safer)
3. **Implementation ease** (instance resize vs architecture change)

---

## 📊 Supported Resources

| Resource Type | Metrics Analyzed | Recommendation Types |
|---------------|------------------|---------------------|
| **EC2 Instances** | CPU, Memory, Network, Disk | Instance type, family change, termination |
| **RDS Databases** | CPU, IOPS, Connections, Storage | Instance size, storage optimization |
| **Lambda Functions** | Duration, Memory, Invocations | Memory allocation, timeout adjustment |

**Coming Soon:**
- ECS/EKS containers
- ElastiCache clusters
- DynamoDB tables (provisioned)
- EBS volumes

---

## 🔧 Configuration

Copy `config.yaml.example` to `config.yaml` and customize:

```yaml
# Analysis Settings
analysis:
  lookback_days: 30              # Metric history window
  min_age_days: 7                # Skip resources newer than this
  min_monthly_cost: 10.0         # Ignore cheap resources
  confidence_threshold: 70       # Only show recommendations >= 70%

# Resource Types
resources:
  ec2:
    enabled: true
    exclude_tags:
      - Key: "Optimizer"
        Value: "Exclude"
  
  rds:
    enabled: true
    exclude_aurora_serverless: true
  
  lambda:
    enabled: true
    min_invocations: 1000        # Skip rarely-used functions

# Bedrock Settings
bedrock:
  region: us-east-1
  model_id: anthropic.claude-3-5-sonnet-20241022-v2:0
  max_tokens: 4000
  temperature: 0.2

# Alerting
alerting:
  sns_topic_arn: arn:aws:sns:us-east-1:123456789012:optimizer-alerts
  slack_webhook_url: https://hooks.slack.com/services/YOUR/WEBHOOK/URL
  
  # Only alert if total savings exceed threshold
  min_total_savings: 100         # Don't alert for < $100/month
```

---

## 💰 Cost Breakdown

**Operating Costs (Monthly):**
- Lambda execution (1 run/day, 5 min): ~$2
- CloudWatch API calls (metrics retrieval): ~$10
- Bedrock API (Claude 3.5 Sonnet): ~$15
- DynamoDB on-demand: ~$1
- S3 storage: ~$0.50
- **Total: ~$30/month**

**Typical Savings:**
- Small accounts (10-50 resources): $500-2,000/month
- Medium accounts (50-200 resources): $2,000-10,000/month
- Large accounts (200+ resources): $10,000+/month

**ROI: 15-300x**

---

## 🛡️ Safety Features

### Conservative Recommendations
- Only suggests changes with clear metrics support
- Flags risky changes (confidence < 70%)
- Respects resource tags (`Optimizer: Exclude`)
- Never recommends changes for resources < 7 days old

### Dry-Run Mode
```bash
# Generate recommendations without alerts
aws lambda invoke \
  --function-name resource-optimizer \
  --payload '{"dry_run": true}' \
  response.json
```

### Approval Workflows
- Recommendations stored in DynamoDB with status: `pending`
- Slack alerts include "Approve" button
- Only applies changes after human approval
- Audit trail of all changes

---

## 📚 Workshop & Blog

- **Workshop**: [Optimize Your AWS Costs in 60 Minutes](docs/WORKSHOP.md)
- **Blog Post**: [Building AI-Powered Resource Optimization](docs/BLOG.md)

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📞 Support

- **Issues & Questions**: [GitHub Issues](https://github.com/chezsal12/aws-resource-optimizer/issues)
- **AWS Support**: For production issues, contact AWS Support

---

## 📄 License

This project is licensed under the MIT-0 License - see the [LICENSE](LICENSE) file for details.

---

**⭐ If this project helps you save costs, give it a star!**

Built with ❤️ using Amazon Bedrock (Claude 3.5 Sonnet)
