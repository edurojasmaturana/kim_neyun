# DNS: zona Route 53 para el dominio principal + registro A apuntando al
# Elastic IP del frontend EC2. Una vez aplicado, copiar los 4 NS del output
# `route53_name_servers` al panel de nic.cl (Servidores de nombre) para delegar
# el dominio. La propagación suele completarse en < 4 h.

resource "aws_route53_zone" "main" {
  name = var.domain_name
  tags = local.tags
}

resource "aws_route53_record" "frontend" {
  zone_id = aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "A"
  ttl     = 300
  records = [aws_eip.frontend.public_ip]
}

output "route53_name_servers" {
  description = "Servidores NS a pegar en nic.cl (Servidores de nombre) para delegar el dominio a Route53."
  value       = aws_route53_zone.main.name_servers
}
