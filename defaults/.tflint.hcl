config {
  format           = "compact"
  call_module_type = "local"
  force            = false
}

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

# These two are often managed via CI or wrappers; disable by default.
rule "terraform_required_providers" {
  enabled = false
}

rule "terraform_required_version" {
  enabled = false
}