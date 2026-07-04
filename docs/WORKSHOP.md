# Workshop: Optimize Your AWS Costs in 60 Minutes

**Duration**: 60-90 minutes  
**Level**: Intermediate  
**Prerequisites**: AWS account, basic CloudWatch/Lambda knowledge

---

## Learning Objectives

By the end of this workshop, you will:
- Deploy AI-powered resource optimization using Amazon Bedrock
- Analyze CloudWatch metrics for right-sizing decisions
- Understand confidence scoring and risk assessment
- Generate actionable cost savings recommendations

---

## Architecture Overview

```
EventBridge (daily) → Lambda → CloudWatch Metrics
                         ↓
                    Bedrock (Claude)
                         ↓
              Recommendations + Alerts
```

---

## Module 1: Setup (10 minutes)

### 1.1 Verify Amazon Bedrock Access

> **Note**: As of 2026, Bedrock models are automatically enabled when first invoked. No manual activation needed!

Verify you can access Bedrock:

```bash
# List available Claude models
aws bedrock list-foundation-models \
  --region us-east-1 \
  --by-provider anthropic \
  --query 'modelSummaries[?contains(modelId, `haiku`)].{ModelId:modelId,Name:modelName}' \
  --output table
```

You should see Claude Haiku 4.5 and others. Models are ready to use!

### 1.2 Clone Repository

```bash
git clone https://github.com/chezsal12/aws-resource-optimizer.git
cd aws-resource-optimizer
```

---

## Module 2: Manual Deployment (20 minutes)

### 2.1 Create IAM Role

```bash
# Create trust policy
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name ResourceOptimizerRole \
  --assume-role-policy-document file://trust-policy.json

# Attach policies
aws iam attach-role-policy \
  --role-name ResourceOptimizerRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Create inline policy for resource access
cat > optimizer-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "rds:DescribeDBInstances",
        "lambda:ListFunctions",
        "lambda:ListTags",
        "cloudwatch:GetMetricStatistics",
        "bedrock:InvokeModel",
        "dynamodb:PutItem",
        "dynamodb:Query",
        "s3:PutObject",
        "sns:Publish"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name ResourceOptimizerRole \
  --policy-name OptimizerPolicy \
  --policy-document file://optimizer-policy.json
```

### 2.2 Create DynamoDB Table

```bash
aws dynamodb create-table \
  --table-name optimizer-recommendations \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
    AttributeName=GSI1PK,AttributeType=S \
    AttributeName=GSI1SK,AttributeType=S \
  --key-schema \
    AttributeName=PK,KeyType=HASH \
    AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes \
    "IndexName=GSI1,KeySchema=[{AttributeName=GSI1PK,KeyType=HASH},{AttributeName=GSI1SK,KeyType=RANGE}],Projection={ProjectionType=ALL}" \
  --billing-mode PAY_PER_REQUEST
```

### 2.3 Create SNS Topic

```bash
aws sns create-topic --name optimizer-alerts

# Subscribe your email
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:YOUR_ACCOUNT:optimizer-alerts \
  --protocol email \
  --notification-endpoint your-email@example.com

# Check email and confirm subscription
```

### 2.4 Package and Deploy Lambda

```bash
# Install dependencies
cd src
pip install -r ../requirements.txt -t .

# Create deployment package
zip -r ../function.zip .
cd ..

# Create Lambda function
ROLE_ARN=$(aws iam get-role --role-name ResourceOptimizerRole --query 'Role.Arn' --output text)

aws lambda create-function \
  --function-name resource-optimizer \
  --runtime python3.12 \
  --role $ROLE_ARN \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://function.zip \
  --timeout 900 \
  --memory-size 1024 \
  --environment Variables="{
    DYNAMODB_TABLE_NAME=optimizer-recommendations,
    SNS_TOPIC_ARN=arn:aws:sns:us-east-1:YOUR_ACCOUNT:optimizer-alerts,
    BEDROCK_REGION=us-east-1,
    LOG_LEVEL=INFO
  }"
```

---

## Module 3: Test the System (15 minutes)

### 3.1 Dry Run Test

```bash
aws lambda invoke \
  --function-name resource-optimizer \
  --payload '{"dry_run": true}' \
  response.json

cat response.json | jq .
```

**Expected output:**
```json
{
  "statusCode": 200,
  "body": {
    "message": "Analysis complete",
    "total_recommendations": 3,
    "total_monthly_savings": 450.50,
    "total_annual_savings": 5406.00,
    "top_3_opportunities": [...]
  }
}
```

### 3.2 Check CloudWatch Logs

```bash
aws logs tail /aws/lambda/resource-optimizer --follow
```

### 3.3 Review Recommendations

```bash
# Query DynamoDB for stored recommendations
aws dynamodb scan \
  --table-name optimizer-recommendations \
  --max-items 5 | jq '.Items'
```

---

## Module 4: Understanding the Analysis (15 minutes)

### 4.1 How Claude Analyzes Resources

The AI receives:
1. **Resource metadata** (type, size, configuration)
2. **30-day CloudWatch metrics** (CPU, memory, IOPS, invocations)
3. **Statistical analysis** (average, P50, P95, P99, max)

Example prompt structure:
```
Resource: EC2 i-1234567890
Instance Type: m5.4xlarge
CPU Metrics (30 days):
- Average: 15.2%
- P95: 28.5%
- Max: 42.1%

Should we optimize? Provide confidence score and reasoning.
```

### 4.2 Confidence Scoring

- **90-100%**: Very consistent low usage, safe to optimize
- **70-89%**: Generally low usage, some variation
- **50-69%**: Mixed signals, recommend monitoring first
- **<50%**: Don't recommend optimization

### 4.3 Risk Assessment

- **Low Risk**: Metrics show consistent low usage, no performance degradation expected
- **Medium Risk**: Some variability, test in non-prod first
- **High Risk**: Significant spikes or limited data, manual review needed

---

## Module 5: Configure Slack Alerts (10 minutes)

### 5.1 Create Slack Webhook

1. Go to https://api.slack.com/apps
2. Create New App → From scratch
3. Name: "Resource Optimizer"
4. Select workspace
5. Features → Incoming Webhooks → Activate
6. Add New Webhook to Workspace
7. Copy webhook URL

### 5.2 Update Lambda Environment

```bash
aws lambda update-function-configuration \
  --function-name resource-optimizer \
  --environment Variables="{
    DYNAMODB_TABLE_NAME=optimizer-recommendations,
    SNS_TOPIC_ARN=arn:aws:sns:us-east-1:YOUR_ACCOUNT:optimizer-alerts,
    SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL,
    BEDROCK_REGION=us-east-1,
    MIN_TOTAL_SAVINGS=100,
    LOG_LEVEL=INFO
  }"
```

### 5.3 Test Slack Alert

```bash
aws lambda invoke \
  --function-name resource-optimizer \
  --payload '{"dry_run": false}' \
  response.json
```

Check your Slack channel for the optimization alert!

---

## Module 6: Schedule Daily Runs (10 minutes)

### 6.1 Create EventBridge Rule

```bash
aws events put-rule \
  --name daily-optimizer \
  --schedule-expression "rate(1 day)" \
  --description "Run resource optimizer daily"

# Get Lambda ARN
LAMBDA_ARN=$(aws lambda get-function --function-name resource-optimizer --query 'Configuration.FunctionArn' --output text)

# Add Lambda as target
aws events put-targets \
  --rule daily-optimizer \
  --targets "Id"="1","Arn"="$LAMBDA_ARN"

# Grant EventBridge permission to invoke Lambda
aws lambda add-permission \
  --function-name resource-optimizer \
  --statement-id allow-eventbridge \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:us-east-1:YOUR_ACCOUNT:rule/daily-optimizer
```

---

## Module 7: Customization (10 minutes)

### 7.1 Exclude Specific Resources

Tag resources you don't want optimized:
```bash
aws ec2 create-tags \
  --resources i-1234567890 \
  --tags Key=Optimizer,Value=Exclude
```

### 7.2 Adjust Thresholds

Update Lambda environment:
```bash
aws lambda update-function-configuration \
  --function-name resource-optimizer \
  --environment Variables="{
    MIN_AGE_DAYS=14,
    CONFIDENCE_THRESHOLD=80,
    MIN_TOTAL_SAVINGS=200
  }"
```

### 7.3 Add S3 Report Storage

```bash
# Create S3 bucket
aws s3 mb s3://my-optimizer-reports-$(aws sts get-caller-identity --query Account --output text)

# Update Lambda to write reports
aws lambda update-function-configuration \
  --function-name resource-optimizer \
  --environment Variables="{
    S3_BUCKET_NAME=my-optimizer-reports-$(aws sts get-caller-identity --query Account --output text)
  }"
```

---

## Module 8: Cleanup (5 minutes)

```bash
# Delete Lambda function
aws lambda delete-function --function-name resource-optimizer

# Delete EventBridge rule
aws events remove-targets --rule daily-optimizer --ids 1
aws events delete-rule --name daily-optimizer

# Delete DynamoDB table
aws dynamodb delete-table --table-name optimizer-recommendations

# Delete SNS topic
aws sns delete-topic --topic-arn arn:aws:sns:us-east-1:YOUR_ACCOUNT:optimizer-alerts

# Delete IAM role
aws iam delete-role-policy --role-name ResourceOptimizerRole --policy-name OptimizerPolicy
aws iam detach-role-policy --role-name ResourceOptimizerRole --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name ResourceOptimizerRole
```

---

## 🎓 Key Takeaways

1. **AI analyzes patterns**, not just thresholds
2. **Confidence scoring** helps prioritize safe optimizations
3. **30-day metrics** provide reliable baseline
4. **Risk assessment** prevents performance issues
5. **Cost efficiency**: ~$30/month to potentially save thousands

---

## 📚 Additional Resources

- [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [CloudWatch Metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/)
- [AWS Compute Optimizer](https://docs.aws.amazon.com/compute-optimizer/)

---

## 🤝 Questions & Feedback

- **GitHub Issues**: https://github.com/chezsal12/aws-resource-optimizer/issues

---

**Workshop Complete!** 🎉

You now have AI-powered resource optimization running in your AWS account.
