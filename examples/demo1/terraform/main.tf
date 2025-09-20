# .github/fixtures/terraform/main.tf
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "mock"
  secret_key                  = "mock"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  skip_region_validation      = true
}

variable "size_gb" {
  type    = number
  default = 10
}

resource "aws_ebs_volume" "test" {
  availability_zone = "us-east-1a"
  size              = var.size_gb
  type              = "gp3"
  tags = {
    Name = "infracost-local-ebs"
  }
}

variable "not_used" {
  type    = string
  default = "hello"
}

variable "no_type" {
  default = "no_type"
}