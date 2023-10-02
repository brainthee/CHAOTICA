
variable "region" {
  type    = string
  default = "eu-west-2"
}

variable "domain_name" {
  type = string
}

variable "app_name" {
  type    = string
  default = "chaotica"
}

variable "app_tag" {
  type    = string
  default = "latest"
}

variable "repo_url" {
  type    = string
  default = "public.ecr.aws/w7j6w2q4"
}

variable "keypair" {
  type    = string
  default = "adrian-desktop"
}

variable "ssh_listener_port" {
  type    = string
  default = "9822"
}

variable "ssh_listener_enabled" {
  type    = bool
  default = true
}

variable "subdomain_name" {
  type = string
}

variable "SENTRY_DSN" {
  type    = string
  default = ""
}

variable "EMAIL_HOST" {
  type    = string
  default = ""
}

variable "EMAIL_HOST_USER" {
  type    = string
  default = ""
}

variable "EMAIL_HOST_PASSWORD" {
  type    = string
  default = ""
}

locals {
  app_env = {
    # General Site Settings
    SECRET_KEY  = "${random_password.secret_key.result}"
    SITE_DOMAIN = "${var.subdomain_name}.${var.domain_name}"
    SITE_PROTO  = "https"
    DJANGO_ENV  = "Dev-${var.subdomain_name}"
    # Debugging
    SENTRY_DSN = "${var.SENTRY_DSN}"
    DEBUG      = 0
    # Email Settings
    EMAIL_HOST          = "${var.EMAIL_HOST}"
    EMAIL_PORT          = 587
    EMAIL_HOST_USER     = "${var.EMAIL_HOST_USER}"
    EMAIL_HOST_PASSWORD = "${var.EMAIL_HOST_PASSWORD}"
    # DB Settings
    SQL_ENGINE = "django.db.backends.mysql"
  }
}