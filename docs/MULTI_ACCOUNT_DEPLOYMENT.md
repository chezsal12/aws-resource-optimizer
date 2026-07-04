# Multi-Account Deployment Guide

**For AWS Organizations with Multiple Accounts**

This guide explains how to deploy AWS Smart Resource Right-Sizer across an AWS Organization to optimize resources in all member accounts.

---

## 🏢 Architecture Overview

```
AWS Organization
│
├─ Management Account (Payer)
│  └─ (No deployment needed here)
│
├─ Shared Services / Tools Account
│  └─ 🎯 Resource Right-Sizer (DEPLOY HERE)
│     ├─ Lambda Function (central)
│     ├─ EventBridge Rule (daily)
│     ├─ DynamoDB Table (recommendations)
│     ├─ S3 Bucket (reports)
│     └─ Assumes roles into member accounts →
│
└─ Member Accounts
   ├─ Production Account
   │  └─ IAM Role (OptimizerAccessRole)
   ├─ Development Account  
   │  └─ IAM Role (OptimizerAccessRole)
   └─ Staging Account
      └─ IAM Role (OptimizerAccessRole)
```

---

## ✅ Deployment Options

### Option A: Centralized (Recommended)

**One Lambda in Shared Services account**
- ✅ Easier to manage (one codebase)
- ✅ Lower cost (one Lambda deployment)
- ✅ Central reporting
- ✅ Uses cross-account IAM roles

### Option B: Distributed

**Lambda in each member account**
- ✅ Better isolation
- ✅ No cross-account permissions needed
- ❌ More complex (N deployments)
- ❌ Higher cost
- ❌ Reports need aggregation

**This guide covers Option A (Centralized)**

---

## 🚀 Deployment Steps

### Step 1: Choose Central Account

Use one of:
- Shared Services account (recommended)
- Security/Tools account  
- Dedicated "FinOps" account

**NOT the management account** (keep it minimal)

### Step 2: Create Cross-Account IAM Roles

In **each member account**, create a role the central Lambda can assume:

```bash
# Run this in EACH member account
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "AWS": "arn:aws:iam::CENTRAL-ACCOUNT-ID:role/ResourceOptimizerRole"
    },
    "Action": "sts:AssumeRole",
    "Condition": {
      "StringEquals": {
        "sts:ExternalId": "resource-optimizer-12345"
      }
    }
  }]
}
EOF

aws iam create-role \
  --role-name OptimizerAccessRole \
  --assume-role-policy-document file://trust-policy.json

# Attach permissions policy
cat > optimizer-permissions.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeTags",
        "rds:DescribeDBInstances",
        "lambda:ListFunctions",
        "lambda:ListTags",
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name OptimizerAccessRole \
  --policy-name OptimizerPermissions \
  --policy-document file://optimizer-permissions.json
```

**Security Note:** Use an `ExternalId` to prevent confused deputy attacks!

### Step 3: Deploy in Central Account

```bash
# Switch to central account
aws sts get-caller-identity

# Clone repository
git clone https://github.com/chezsal12/aws-resource-optimizer.git
cd aws-resource-optimizer

# Deploy
aws cloudformation deploy \
  --template-file cloudformation/deployment-template.yaml \
  --stack-name resource-optimizer-org \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    AlertEmail=finops-team@company.com \
    ScheduleExpression="rate(1 day)"
```

### Step 4: Configure Multi-Account Scanning

Update Lambda environment with member account IDs:

```bash
aws lambda update-function-configuration \
  --function-name resource-optimizer \
  --environment Variables="{
    DYNAMODB_TABLE_NAME=optimizer-recommendations,
    S3_BUCKET_NAME=optimizer-reports-org,
    SNS_TOPIC_ARN=arn:aws:sns:us-east-1:CENTRAL-ACCOUNT:optimizer-alerts,
    MULTI_ACCOUNT_MODE=true,
    MEMBER_ACCOUNTS=111111111111,222222222222,333333333333,
    CROSS_ACCOUNT_ROLE_NAME=OptimizerAccessRole,
    EXTERNAL_ID=resource-optimizer-12345
  }"
```

---

## 🔧 Configuration

### config.yaml for Organizations

```yaml
# Multi-Account Settings
multi_account:
  enabled: true
  central_account_id: "000000000000"  # Shared Services
  
  member_accounts:
    - account_id: "111111111111"
      account_name: "Production"
      role_name: "OptimizerAccessRole"
      external_id: "resource-optimizer-12345"
      
      # Account-specific settings
      min_age_days: 14  # More conservative in prod
      confidence_threshold: 85
      
    - account_id: "222222222222"
      account_name: "Development"
      role_name: "OptimizerAccessRole"
      external_id: "resource-optimizer-12345"
      
      # Less conservative in dev
      min_age_days: 3
      confidence_threshold: 60
    
    - account_id: "333333333333"
      account_name: "Staging"
      role_name: "OptimizerAccessRole"
      external_id: "resource-optimizer-12345"

# Alert routing by account
alerting:
  account_routing:
    "111111111111":  # Production
      slack_channel: "#prod-optimization"
      min_total_savings: 500
      
    "222222222222":  # Development  
      slack_channel: "#dev-optimization"
      min_total_savings: 50
      
    "333333333333":  # Staging
      slack_channel: "#staging-optimization"
      min_total_savings: 100
```

---

## 💻 Code Implementation

### Cross-Account Resource Scanning

Update `src/resource_scanner.py`:

```python
import boto3
from botocore.exceptions import ClientError

class MultiAccountResourceScanner:
    """Scans resources across multiple AWS accounts."""
    
    def __init__(self, config):
        self.config = config
        self.sts = boto3.client('sts')
    
    def assume_role(self, account_id, role_name, external_id):
        """
        Assume role in member account.
        
        Args:
            account_id: Target account ID
            role_name: Role to assume
            external_id: External ID for security
            
        Returns:
            Session credentials
        """
        role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
        
        response = self.sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName='ResourceOptimizer',
            ExternalId=external_id,
            DurationSeconds=3600
        )
        
        return response['Credentials']
    
    def get_ec2_client(self, account_id):
        """Get EC2 client for member account."""
        creds = self.assume_role(
            account_id,
            self.config['cross_account_role_name'],
            self.config['external_id']
        )
        
        return boto3.client(
            'ec2',
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken']
        )
    
    def discover_all_accounts(self):
        """Discover resources across all member accounts."""
        all_resources = []
        
        for account in self.config['member_accounts']:
            account_id = account['account_id']
            account_name = account['account_name']
            
            logger.info(f"Scanning account: {account_name} ({account_id})")
            
            try:
                # Get clients for this account
                ec2 = self.get_ec2_client(account_id)
                
                # Discover resources
                instances = self.discover_ec2_instances(ec2)
                
                # Tag with account info
                for instance in instances:
                    instance['account_id'] = account_id
                    instance['account_name'] = account_name
                
                all_resources.extend(instances)
                
            except ClientError as e:
                logger.error(f"Error scanning account {account_id}: {e}")
                continue
        
        return all_resources
```

---

## 📊 Example Alert (Multi-Account)

```
🎯 Optimization Recommendations (3 accounts, 47 opportunities)

💰 Total Potential Savings: $12,450/month

By Account:
• Production (111111111111): $8,200/month (18 opportunities)
• Development (222222222222): $3,100/month (22 opportunities)  
• Staging (333333333333): $1,150/month (7 opportunities)

Top Recommendation (Production):
🔴 RDS Instance: prod-database-1
   Current: db.r5.4xlarge ($2,920/mo)
   Recommended: db.r5.2xlarge ($1,460/mo)
   Savings: $1,460/month (50%)
   Confidence: High (95%)

[View Full Report by Account]
```

---

## 🔐 IAM Permissions

### Central Account Lambda Role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumeRoleInMemberAccounts",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::*:role/OptimizerAccessRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "resource-optimizer-12345"
        }
      }
    },
    {
      "Sid": "StorageAndAlerting",
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:Query",
        "s3:PutObject",
        "sns:Publish",
        "bedrock:InvokeModel"
      ],
      "Resource": [
        "arn:aws:dynamodb:*:CENTRAL-ACCOUNT:table/optimizer-recommendations",
        "arn:aws:s3:::optimizer-reports-org/*",
        "arn:aws:sns:*:CENTRAL-ACCOUNT:optimizer-alerts",
        "arn:aws:bedrock:*::foundation-model/anthropic.claude*"
      ]
    }
  ]
}
```

### Member Account OptimizerAccessRole

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeTags",
        "rds:DescribeDBInstances",
        "rds:ListTagsForResource",
        "lambda:ListFunctions",
        "lambda:ListTags",
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## 🎯 Account-Specific Optimization

### Different Strategies per Account

```python
def get_account_config(account_id):
    """Get optimization config for specific account."""
    
    configs = {
        # Production: Conservative
        "111111111111": {
            "min_age_days": 14,
            "confidence_threshold": 85,
            "auto_apply": False  # Require approval
        },
        # Development: Aggressive  
        "222222222222": {
            "min_age_days": 3,
            "confidence_threshold": 60,
            "auto_apply": True  # Auto-optimize
        },
        # Staging: Moderate
        "333333333333": {
            "min_age_days": 7,
            "confidence_threshold": 75,
            "auto_apply": False
        }
    }
    
    return configs.get(account_id, DEFAULT_CONFIG)
```

---

## 📈 Reporting

### Organization-Wide Dashboard

Generate consolidated reports:

```bash
# Weekly org-wide report
aws lambda invoke \
  --function-name resource-optimizer \
  --payload '{
    "report_type": "org_summary",
    "period": "weekly",
    "group_by": "account"
  }' \
  response.json
```

Report includes:
- Savings by account
- Top opportunities org-wide
- Account-by-account breakdown
- Optimization velocity (recommendations applied)

### Per-Account Reports

```bash
# Production account only
aws lambda invoke \
  --function-name resource-optimizer \
  --payload '{
    "account_id": "111111111111",
    "report_type": "detailed"
  }' \
  response.json
```

---

## 💰 Cost Breakdown (Organization)

**For an org with 5 accounts, 200 total resources:**

| Component | Cost | Notes |
|-----------|------|-------|
| Lambda (1 run/day) | $5/month | Scans 5 accounts |
| CloudWatch API | $25/month | 200 resources × metrics |
| Bedrock API | $40/month | AI analysis |
| DynamoDB | $3/month | Recommendations |
| S3 | $2/month | Reports |
| **Total** | **~$75/month** | For entire organization |

**Per-account cost**: ~$15/account/month

**Typical savings**: $5,000-20,000/month across org  
**ROI**: 65-265x

---

## 🚨 Common Issues

### Issue 1: "Access Denied" Assuming Role

**Problem**: Can't assume role in member account

**Solutions**:
```bash
# 1. Verify trust relationship in member account
aws iam get-role --role-name OptimizerAccessRole \
  --query 'Role.AssumeRolePolicyDocument'

# 2. Check External ID matches
# 3. Verify central account ID in trust policy
# 4. Check SCPs don't block sts:AssumeRole
```

### Issue 2: Partial Account Scanning

**Problem**: Some accounts scanned, others skipped

**Solution**: Check Lambda timeout (increase to 15 min for many accounts):
```bash
aws lambda update-function-configuration \
  --function-name resource-optimizer \
  --timeout 900
```

### Issue 3: Duplicate Recommendations

**Problem**: Same resource recommended multiple times

**Solution**: DynamoDB deduplication by account + resource ID:
```python
def get_recommendation_key(account_id, resource_id):
    return f"{account_id}#{resource_id}"
```

---

## 🎓 Best Practices

### 1. Stagger Account Scanning

For many accounts, scan in batches:

```python
import time

for i, account in enumerate(accounts):
    if i > 0 and i % 5 == 0:
        time.sleep(10)  # Pause every 5 accounts
    
    scan_account(account)
```

### 2. Account Tagging

Tag accounts for organized reporting:

```yaml
member_accounts:
  - account_id: "111111111111"
    tags:
      Environment: "Production"
      CostCenter: "Engineering"
      Criticality: "High"
```

### 3. Notification Routing

Route by account owner:

```python
account_owners = {
    "111111111111": "engineering-leads@company.com",
    "222222222222": "dev-team@company.com"
}

def send_alert(account_id, recommendations):
    owner = account_owners.get(account_id)
    send_email(owner, recommendations)
```

### 4. Gradual Rollout

Start with 1-2 accounts, then expand:

```yaml
# Week 1: Dev accounts only
member_accounts:
  - account_id: "222222222222"

# Week 2: Add staging
# Week 3: Add production
```

---

## 🔄 Migration Strategy

### From Single-Account to Multi-Account

1. **Deploy central Lambda**
2. **Keep existing deployments running** (parallel)
3. **Verify central Lambda finds same resources**
4. **Switch alerting to central**
5. **Delete member account deployments**

```bash
# Verification script
for account in 111111111111 222222222222; do
  echo "Checking $account..."
  aws lambda invoke \
    --function-name resource-optimizer \
    --payload "{\"account_id\": \"$account\", \"dry_run\": true}" \
    result-$account.json
done
```

---

## 📞 Support

For multi-account deployment questions:
- **GitHub Issues**: https://github.com/chezsal12/aws-resource-optimizer/issues  
- **Tag**: `multi-account` or `cross-account`

---

## 🎯 Summary

✅ **Deploy in shared services account** for centralized management  
✅ **Use cross-account IAM roles** with ExternalId for security  
✅ **Account-specific configs** for production vs dev  
✅ **~$75/month** for 5-account organization  
✅ **$5-20K/month savings** typical  

**Ready to deploy? Follow the steps above!** 🚀
