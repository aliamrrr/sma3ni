data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# AWS Deep Learning Base AMI: NVIDIA driver, Docker and nvidia-container-toolkit preinstalled.
data "aws_ami" "gpu" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "random_id" "suffix" {
  byte_length = 4
}

# --------------------------------------------------------------------------- S3: temporary audio
resource "aws_s3_bucket" "audio" {
  bucket = "${var.project}-audio-${random_id.suffix.hex}"
}

resource "aws_s3_bucket_public_access_block" "audio" {
  bucket                  = aws_s3_bucket.audio.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "audio" {
  bucket = aws_s3_bucket.audio.id

  rule {
    object_ownership = "BucketOwnerEnforced" # ACLs disabled
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audio" {
  bucket = aws_s3_bucket.audio.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms" # AWS managed key aws/s3; set S3_KMS_KEY_ID to use a customer key
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "audio" {
  bucket = aws_s3_bucket.audio.id

  rule {
    id     = "expire-voice-notes"
    status = "Enabled"

    filter {
      prefix = "${var.s3_prefix}/"
    }

    expiration {
      days = var.audio_retention_days + 1
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

data "aws_iam_policy_document" "bucket" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.audio.arn,
      "${aws_s3_bucket.audio.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "audio" {
  bucket     = aws_s3_bucket.audio.id
  policy     = data.aws_iam_policy_document.bucket.json
  depends_on = [aws_s3_bucket_public_access_block.audio]
}

# S3 traffic stays on the AWS network.
resource "aws_vpc_endpoint" "s3" {
  count             = var.create_s3_gateway_endpoint ? 1 : 0
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [data.aws_vpc.default.main_route_table_id]
}

# --------------------------------------------------------------------------- IAM: instance role
data "aws_iam_policy_document" "assume_ec2" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name               = "${var.project}-instance"
  assume_role_policy = data.aws_iam_policy_document.assume_ec2.json
}

# Least privilege: objects under the audio prefix only. ListBucket (same prefix) lets S3
# answer 404 instead of 403 for a purged object, which the app treats as "audio gone".
data "aws_iam_policy_document" "audio_access" {
  statement {
    sid       = "AudioObjects"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.audio.arn}/${var.s3_prefix}/*"]
  }

  statement {
    sid       = "AudioPrefixListing"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.audio.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${var.s3_prefix}/*"]
    }
  }
}

resource "aws_iam_role_policy" "audio_access" {
  name   = "audio-bucket"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.audio_access.json
}

# Shell access through SSM Session Manager: no open SSH port needed.
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.project}-instance"
  role = aws_iam_role.instance.name
}

# --------------------------------------------------------------------------- network
resource "aws_security_group" "instance" {
  name_prefix = "${var.project}-"
  description = "Sma3ni: HTTP/HTTPS in, HTTP/HTTPS out"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP (ACME challenge, redirect to HTTPS)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP/3"
    from_port   = 443
    to_port     = 443
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  dynamic "ingress" {
    for_each = length(var.ssh_cidrs) > 0 ? [1] : []

    content {
      description = "SSH (admin networks only)"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = var.ssh_cidrs
    }
  }

  # Outbound limited to HTTP/HTTPS: S3 (through the endpoint), Let's Encrypt, Hugging Face,
  # package mirrors, SSM. DNS and NTP use link-local AWS services, not filtered here.
  egress {
    description = "HTTPS out"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "HTTP out (package mirrors)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

# --------------------------------------------------------------------------- compute
resource "aws_instance" "app" {
  ami                    = data.aws_ami.gpu.id
  instance_type          = var.instance_type
  subnet_id              = coalesce(var.subnet_id, data.aws_subnets.default.ids[0])
  vpc_security_group_ids = [aws_security_group.instance.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name
  key_name               = var.key_name
  user_data              = file("${path.module}/../bootstrap.sh")

  # IMDSv2 only. Hop limit 2 so containers (one extra network hop) can fetch role credentials.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_size           = var.root_volume_gb
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = false # PostgreSQL lives here: keep the volume if the instance is destroyed
  }

  tags = {
    Name = var.project
  }

  lifecycle {
    ignore_changes = [ami, user_data] # a newer AMI must not replace the running server
  }
}

resource "aws_eip" "app" {
  domain   = "vpc"
  instance = aws_instance.app.id
}
