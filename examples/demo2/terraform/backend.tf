terraform {
  required_version = ">= 1.11.0"

  backend "local" {
    path = "terraform.tfstate"
  }
}