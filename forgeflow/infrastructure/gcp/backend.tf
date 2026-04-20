terraform {
  backend "gcs" {
    bucket = "sevaforge-unified-tfstate"
    prefix = "gcp"
  }
}
