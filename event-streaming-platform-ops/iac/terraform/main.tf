# Event streaming platform (MSK-style) — Terraform.
# Declarative only: this file is validated in CI by the local IaC
# checker and is never applied by this project against a real account.
terraform {
  required_version = ">= 1.5"
}

variable "environment" {
  type    = string
  default = "production"
}

resource "aws_msk_cluster" "messaging" {
  cluster_name           = "messaging-platform-${var.environment}"
  kafka_version          = "3.6.0"
  number_of_broker_nodes = 3

  broker_node_group_info {
    instance_type   = "kafka.m7g.large"
    storage_info {
      ebs_storage_info {
        volume_size = 100
      }
    }
    broker_az_distribution = "DEFAULT"
  }

  encryption_info {
    encryption_at_rest_kms_key_arn = "arn:aws:kms:us-east-1:000000000000:key/demo-only"
  }

  configuration_info {
    arn      = aws_msk_configuration.messaging.arn
    revision = aws_msk_configuration.messaging.latest_revision
  }

  tags = {
    Environment = var.environment
    Team        = "messaging-platform"
  }
}

resource "aws_msk_configuration" "messaging" {
  kafka_versions    = ["3.6.0"]
  name              = "messaging-platform-config"
  server_properties = <<PROPERTIES
auto.create.topics.enable=false
default.replication.factor=3
min.insync.replicas=2
num.partitions=6
log.retention.hours=168
PROPERTIES
}

resource "aws_sqs_queue" "order_notifications" {
  name                       = "order-notifications"
  visibility_timeout_seconds = 120
  message_retention_seconds  = 1209600
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.order_notifications_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue" "order_notifications_dlq" {
  name = "order-notifications-dlq"
}

resource "aws_sns_topic" "order_events" {
  name = "order-events"
}

resource "aws_cloudwatch_event_rule" "high_value_orders" {
  name        = "high-value-orders"
  description = "Route orders over $500 to the notifications queue"
  event_pattern = jsonencode({
    source      = ["com.store.orders"]
    detail-type = ["OrderPlaced"]
    detail = {
      total = [{ numeric = [">", 500] }]
    }
  })
}
