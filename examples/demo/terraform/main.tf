terraform {
  required_version = ">= 1.5.0"
  backend "local" {}
  required_providers {
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

resource "null_resource" "hello" {
  triggers = { msg = var.bad_name }
}

resource "null_resource" "hi" {
  triggers = { msg = var.bad_name }
}