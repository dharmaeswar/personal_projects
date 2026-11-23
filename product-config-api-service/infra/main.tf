terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "us-west-2"
}

variable "environment" {
  type    = string
  default = "dev"
}

# DynamoDB table: partition key product_id, sort key version.
resource "aws_dynamodb_table" "configs" {
  name         = "product-configs-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "product_id"
  range_key    = "version"

  attribute {
    name = "product_id"
    type = "S"
  }
  attribute {
    name = "version"
    type = "N"
  }
}

# Lambda execution role (least privilege: logs + the one table).
resource "aws_iam_role" "lambda_exec" {
  name = "product-config-lambda-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_exec" {
  role = aws_iam_role.lambda_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Effect   = "Allow"
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
        Effect   = "Allow"
        Resource = aws_dynamodb_table.configs.arn
      },
    ]
  })
}

# One Lambda function per handler (create / get / publish / suggest).
resource "aws_lambda_function" "handlers" {
  for_each         = toset(["create_config", "get_config", "publish_config", "suggest_config"])
  function_name    = "product-config-${each.key}-${var.environment}"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "product_config.handlers.${each.key}"
  runtime          = "python3.12"
  filename         = "lambda.zip"
  source_code_hash = filebase64sha256("lambda.zip")

  environment {
    variables = {
      CONFIG_TABLE = aws_dynamodb_table.configs.name
    }
  }
}

# HTTP API in front of the Lambdas.
resource "aws_apigatewayv2_api" "api" {
  name          = "product-config-${var.environment}"
  protocol_type = "HTTP"
}

# Step Functions state machine for the publish workflow:
# draft -> review (validation) -> published.
resource "aws_sfn_state_machine" "publish" {
  name     = "product-config-publish-${var.environment}"
  role_arn = aws_iam_role.lambda_exec.arn
  definition = jsonencode({
    Comment = "Product config publish workflow"
    StartAt = "Validate"
    States = {
      Validate = {
        Type     = "Task"
        Resource = aws_lambda_function.handlers["get_config"].arn
        Next     = "Review"
      }
      Review = {
        Type     = "Pass"
        Next     = "Publish"
      }
      Publish = {
        Type     = "Task"
        Resource = aws_lambda_function.handlers["publish_config"].arn
        End      = true
      }
    }
  })
}
