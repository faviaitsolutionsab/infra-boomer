terraform {
  required_providers {
    local = {
      source = "hashicorp/local"
    }
  }
  required_version = ">= 1.12"
}

provider "local" {
}