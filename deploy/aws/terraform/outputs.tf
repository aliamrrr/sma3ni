output "public_ip" {
  description = "Point the DOMAIN A record here before the first `docker compose up`."
  value       = aws_eip.app.public_ip
}

output "instance_id" {
  value = aws_instance.app.id
}

output "ssm_session" {
  description = "Shell on the instance without SSH."
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.app.id}"
}

output "env_lines" {
  description = "Paste into .env on the instance."
  value       = <<-EOT
    STORAGE_BACKEND=s3
    S3_BUCKET=${aws_s3_bucket.audio.bucket}
    S3_PREFIX=${var.s3_prefix}
    AWS_REGION=${var.region}
    AUDIO_RETENTION_DAYS=${var.audio_retention_days}
  EOT
}
