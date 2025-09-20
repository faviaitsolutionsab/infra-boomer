resource "local_file" "a" {
  content  = "a!"
  filename = "${path.module}/a.bar"
}

resource "local_file" "b" {
  content  = "b!"
  filename = "${path.module}/b.bar"
}

resource "local_sensitive_file" "test" {
  filename = "${path.module}/example.txt"
  content  = "Hello!"
}