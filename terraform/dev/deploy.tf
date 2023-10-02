provider "aws" {
  profile = "default"
  region  = var.region
}

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "3.74.0"
    }
  }
  backend "http" {

  }
}

locals {
  subdomain_name_safe = substr(lower(replace(var.subdomain_name, ".", "-")), 0, (40 - length(var.app_name) - 16))
}

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "beanstalk_service" {
  name = "${var.app_name}-${var.subdomain_name}-${random_string.random.result}-iam"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF
}

resource "aws_iam_role_policy_attachment" "beanstalk_log_attach" {
  role       = aws_iam_role.beanstalk_service.name
  policy_arn = "arn:aws:iam::aws:policy/AWSElasticBeanstalkWebTier"
}

resource "aws_iam_instance_profile" "beanstalk_iam_instance_profile" {
  name = "${var.app_name}-${var.subdomain_name}-${random_string.random.result}-prof"
  role = aws_iam_role.beanstalk_service.name
}

resource "random_uuid" "uuid" {}
resource "random_string" "random" {
  length  = 8
  special = false
  upper   = false
  numeric = false
}

resource "random_string" "dbUser" {
  length  = 8
  special = false
  upper   = false
  numeric = false
}

resource "random_password" "dbPass" {
  length = 16
  special = false
}

resource "random_password" "secret_key" {
  length = 32
}

resource "aws_s3_bucket" "my_app_ebs" {
  bucket = "${var.app_name}-${var.subdomain_name}-${random_string.random.result}"
  acl    = "private"
}

data "template_file" "ecs_config" {
  template = file("Dockerrun.aws.json")

  vars = {
    app_name = var.app_name
    app_tag  = var.app_tag
    repo_url = var.repo_url
  }
}

resource "aws_s3_bucket_object" "my_app_deployment" {
  bucket  = aws_s3_bucket.my_app_ebs.id
  key     = "Dockerrun.aws.json"
  content = data.template_file.ecs_config.rendered
}

resource "aws_elastic_beanstalk_application" "my_app" {
  name        = "${var.app_name}-${var.subdomain_name}-${random_string.random.result}-app"
  description = "${var.app_name}-${var.subdomain_name}-${random_string.random.result}"
}

data "aws_elastic_beanstalk_hosted_zone" "current" {}

resource "aws_elastic_beanstalk_environment" "dev_env" {
  name          = "${var.app_name}-${local.subdomain_name_safe}-${random_string.random.result}-env"
  application   = aws_elastic_beanstalk_application.my_app.name
  cname_prefix  = "${var.app_name}-${local.subdomain_name_safe}-${random_string.random.result}"
  version_label = aws_elastic_beanstalk_application_version.my_app_ebs_version.name

  solution_stack_name = "64bit Amazon Linux 2 v3.5.9 running Docker"

  setting {
    namespace = "aws:autoscaling:launchconfiguration"
    name      = "IamInstanceProfile"
    value     = aws_iam_instance_profile.beanstalk_iam_instance_profile.arn
  }

  setting {
    namespace = "aws:autoscaling:launchconfiguration"
    name      = "SSHSourceRestriction"
    value     = "tcp, 22, 22, 0.0.0.0/0"
  }

  setting {
    namespace = "aws:elasticbeanstalk:environment:process:default"
    name      = "HealthCheckPath"
    value     = "/ping"
  }

  setting {
    namespace = "aws:elasticbeanstalk:environment"
    name      = "LoadBalancerType"
    value     = "application"
  }

  setting {
    namespace = "aws:elbv2:listener:default"
    name      = "ListenerEnabled"
    value     = "false"
  }

  setting {
    namespace = "aws:elbv2:listener:443"
    name      = "Protocol"
    value     = "HTTPS"
  }

  setting {
    namespace = "aws:elbv2:listener:443"
    name      = "SSLCertificateArns"
    value     = aws_acm_certificate.cert.arn
  }

  # setting {
  #   namespace = "aws:elbv2:listener:443"
  #   name = "InstanceProtocol"
  #   value = "HTTP"
  # }

  # setting {
  #   namespace = "aws:elbv2:listener:443"
  #   name = "InstancePort"
  #   value = "8000"
  # }

  ### Define RDS values
  setting {
    namespace = "aws:rds:dbinstance"
    name      = "DBAllocatedStorage"
    value     = "5"
  }

  setting {
    namespace = "aws:rds:dbinstance"
    name      = "DBDeletionPolicy"
    value     = "Delete"
  }

  setting {
    namespace = "aws:rds:dbinstance"
    name      = "HasCoupledDatabase"
    value     = "true"
  }

  setting {
    namespace = "aws:rds:dbinstance"
    name      = "DBEngine"
    value     = "mysql"
  }

  setting {
    namespace = "aws:rds:dbinstance"
    name      = "DBEngineVersion"
    value     = "8.0"
  }

  setting {
    namespace = "aws:rds:dbinstance"
    name      = "DBInstanceClass"
    value     = "db.t3.micro"
  }

  setting {
    namespace = "aws:rds:dbinstance"
    name      = "DBPassword"
    value     = random_password.dbPass.result
  }

  setting {
    namespace = "aws:rds:dbinstance"
    name      = "DBUser"
    value     = random_string.dbUser.result
  }
  ### END RDS


  setting {
    namespace = "aws:autoscaling:launchconfiguration"
    name      = "EC2KeyName"
    value     = var.keypair
  }
  setting {
    namespace = "aws:elb:listener:${var.ssh_listener_port}"
    name      = "ListenerProtocol"
    value     = "TCP"
  }
  setting {
    namespace = "aws:elb:listener:${var.ssh_listener_port}"
    name      = "InstancePort"
    value     = "22"
  }
  setting {
    namespace = "aws:elb:listener:${var.ssh_listener_port}"
    name      = "ListenerEnabled"
    value     = var.ssh_listener_enabled
  }

  dynamic "setting" {
    for_each = local.app_env
    content {
      namespace = "aws:elasticbeanstalk:application:environment"
      name      = setting.key
      value     = setting.value
    }
  }
}

data "aws_route53_zone" "parent" {
  name = var.domain_name
}

resource "aws_route53_record" "www" {
  zone_id = data.aws_route53_zone.parent.id
  name    = var.subdomain_name
  type    = "CNAME"
  records = [aws_elastic_beanstalk_environment.dev_env.cname]
  ttl     = 5
}

resource "aws_route53_record" "certValidation" {
  for_each = {
    for dvo in aws_acm_certificate.cert.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.parent.id
}

resource "aws_acm_certificate" "cert" {
  domain_name       = "${var.subdomain_name}.${var.domain_name}"
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_elastic_beanstalk_application_version" "my_app_ebs_version" {
  name        = "${var.app_name}-${var.subdomain_name}-${random_string.random.result}-version"
  application = aws_elastic_beanstalk_application.my_app.name
  bucket      = aws_s3_bucket.my_app_ebs.id
  key         = aws_s3_bucket_object.my_app_deployment.id
}
