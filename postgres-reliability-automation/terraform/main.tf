# IaC EXAMPLE ONLY - not applied, no real infrastructure.
terraform { required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } } }
resource "aws_db_parameter_group" "postgres" {
  name = "demo-postgres-params"; family = "postgres15"
  parameter { name = "log_min_duration_statement"; value = "1000" }
}
resource "aws_db_instance" "postgres" {
  identifier = "demo-postgres"; engine = "postgres"; engine_version = "15"
  instance_class = "db.t3.micro"; allocated_storage = 20
  username = "demo_admin"; manage_master_user_password = true
  backup_retention_period = 7; multi_az = true
  monitoring_interval = 60; monitoring_role_arn = aws_iam_role.rds_monitoring.arn
  parameter_group_name = aws_db_parameter_group.postgres.name
  skip_final_snapshot = true
}
resource "aws_iam_role" "rds_monitoring" {
  name = "demo-rds-monitoring"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "monitoring.rds.amazonaws.com" } }] })
}
resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
