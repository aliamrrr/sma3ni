variable "project" {
  description = "Name prefix for every resource."
  type        = string
  default     = "sma3ni"
}

variable "region" {
  description = "AWS region. Check GPU availability first (see docs/TECHNICAL.md, AWS deployment)."
  type        = string
  default     = "eu-west-3"
}

variable "instance_type" {
  description = "GPU instance. g6.2xlarge = 1x NVIDIA L4 24 GB, 8 vCPU, 32 GiB RAM. Fallback: g5.2xlarge (A10G 24 GB)."
  type        = string
  default     = "g6.2xlarge"
}

variable "subnet_id" {
  description = "Public subnet for the instance. Empty = first subnet of the default VPC."
  type        = string
  default     = ""
}

variable "root_volume_gb" {
  description = "Encrypted gp3 root volume: Docker images (~8 GB with CUDA), models (~9 GB), PostgreSQL."
  type        = number
  default     = 150
}

variable "key_name" {
  description = "Existing EC2 key pair for SSH. Null = no SSH key, use SSM Session Manager."
  type        = string
  default     = null
}

variable "ssh_cidrs" {
  description = "CIDRs allowed on port 22. Empty list = SSH closed (recommended, use SSM)."
  type        = list(string)
  default     = []
}

variable "s3_prefix" {
  description = "Key prefix of the voice notes in the bucket (must match S3_PREFIX in .env)."
  type        = string
  default     = "audio"
}

variable "audio_retention_days" {
  description = "Must match AUDIO_RETENTION_DAYS. The lifecycle rule expires objects one day later as a safety net."
  type        = number
  default     = 7
}

variable "create_s3_gateway_endpoint" {
  description = "Create an S3 gateway endpoint on the VPC main route table (set false if one already exists)."
  type        = bool
  default     = true
}
