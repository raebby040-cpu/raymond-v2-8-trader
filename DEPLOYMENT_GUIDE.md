# RAYMOND v2.8 - Deployment Guide

## Production Deployment

### Prerequisites

- Docker & Docker Compose installed
- PostgreSQL database (RDS recommended for AWS)
- Broker API credentials (MT5/Exness)
- SSL certificate for HTTPS
- GitHub Secrets configured (for CI/CD)

## Environment Setup

### 1. Production Environment Variables

Create `.env.production`:

```bash
# Application
RAYMOND_ENV=production
DEBUG=false
LIVE_TRADING_ENABLED=false  # Enable only after approval

# Database
DATABASE_URL=postgresql://prod_user:secure_password@rds-instance:5432/raymond_prod
SQL_ECHO=false

# Market Data
MARKET_DATA_PROVIDER=alpha_vantage
ALPHA_VANTAGE_API_KEY=your_actual_api_key

# Brokers
MT5_LOGIN=your_live_login
MT5_PASSWORD=your_live_password
MT5_SERVER=MT5-Live
MT5_ACCOUNT_TYPE=live

EXNESS_TOKEN=your_live_token
EXNESS_ACCOUNT_ID=your_live_account_id
EXNESS_ACCOUNT_TYPE=live

# Security
EMERGENCY_API_KEY=very_secure_emergency_key
SECRET_KEY=generate_with_secrets.token_urlsafe(32)

# Monitoring
LOG_LEVEL=INFO
LOG_FILE=/var/log/raymond/app.log

# CORS
ALLOW_ORIGINS=https://your-domain.com,https://app.your-domain.com

# API Server
API_HOST=0.0.0.0
API_PORT=8000

# Risk Parameters
MAX_DAILY_LOSS_PERCENT=2.0
MAX_SINGLE_TRADE_LOSS=1.0
EMERGENCY_STOP_THRESHOLD=5.0
```

### 2. Docker Compose Production

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  backend:
    image: raymond-trading:latest
    container_name: raymond-backend-prod
    restart: always
    ports:
      - "8000:8000"
    environment:
      - RAYMOND_ENV=production
      - DATABASE_URL=${DATABASE_URL}
      - LIVE_TRADING_ENABLED=${LIVE_TRADING_ENABLED}
    env_file:
      - .env.production
    volumes:
      - raymond_logs:/var/log/raymond
      - raymond_data:/data
    depends_on:
      - postgres
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    networks:
      - raymond-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  postgres:
    image: postgres:15-alpine
    container_name: raymond-postgres-prod
    restart: always
    environment:
      POSTGRES_DB: raymond_prod
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - raymond-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  nginx:
    image: nginx:alpine
    container_name: raymond-nginx-prod
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl/cert.pem:/etc/nginx/ssl/cert.pem:ro
      - ./ssl/key.pem:/etc/nginx/ssl/key.pem:ro
    depends_on:
      - backend
    networks:
      - raymond-network

volumes:
  postgres_data:
  raymond_logs:
  raymond_data:

networks:
  raymond-network:
    driver: bridge
```

### 3. Nginx Configuration

Create `nginx.conf`:

```nginx
http {
    upstream backend {
        server backend:8000;
    }

    server {
        listen 80;
        server_name your-domain.com www.your-domain.com;
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name your-domain.com www.your-domain.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;

        client_max_body_size 10M;

        location / {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_redirect off;
        }

        location /docs {
            proxy_pass http://backend/docs;
        }

        location /openapi.json {
            proxy_pass http://backend/openapi.json;
        }
    }
}
```

## Deployment Steps

### AWS EC2 Deployment

```bash
# 1. Launch EC2 instance (Ubuntu 22.04)
# - Type: t3.medium (2 vCPU, 4GB RAM minimum)
# - Security group: Allow 22, 80, 443
# - Storage: 50GB+ EBS

# 2. SSH into instance
ssh -i key.pem ubuntu@instance-ip

# 3. Install dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose git curl
sudo usermod -aG docker ubuntu

# 4. Clone repository
git clone https://github.com/raebby040-cpu/raymond-v2-8-trader.git
cd raymond-v2-8-trader

# 5. Setup environment
cp .env.example .env.production
# Edit .env.production with production values

# 6. Create SSL certificates (self-signed or from Let's Encrypt)
mkdir -p ssl
openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem -days 365

# 7. Build and deploy
sudo docker-compose -f docker-compose.prod.yml build
sudo docker-compose -f docker-compose.prod.yml up -d

# 8. Verify deployment
curl https://localhost/health
```

### Kubernetes Deployment

```bash
# 1. Create namespace
kubectl create namespace raymond-trading

# 2. Create secrets
kubectl create secret generic raymond-secrets \
  --from-literal=DATABASE_URL=postgresql://... \
  --from-literal=EMERGENCY_API_KEY=... \
  -n raymond-trading

# 3. Deploy
kubectl apply -f k8s/deployment.yaml -n raymond-trading
kubectl apply -f k8s/service.yaml -n raymond-trading
kubectl apply -f k8s/ingress.yaml -n raymond-trading

# 4. Check status
kubectl get pods -n raymond-trading
kubectl logs -f deployment/raymond-backend -n raymond-trading
```

## Monitoring & Maintenance

### Health Checks

```bash
# Check backend health
curl https://your-domain.com/health

# Check database connection
curl https://your-domain.com/api/admin/status

# View logs
sudo docker-compose -f docker-compose.prod.yml logs -f backend
```

### Database Backups

```bash
# Backup database
sudo docker-compose -f docker-compose.prod.yml exec postgres pg_dump \
  -U raymond_user raymond_prod > backup-$(date +%Y%m%d).sql

# Restore from backup
sudo docker-compose -f docker-compose.prod.yml exec -T postgres psql \
  -U raymond_user raymond_prod < backup-20240908.sql
```

### Log Rotation

Create `/etc/logrotate.d/raymond`:

```
/var/log/raymond/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

## Security Hardening

### 1. Network Security
- ✅ Use VPC with private subnets for database
- ✅ Enable WAF (Web Application Firewall)
- ✅ Use Security Groups to restrict access
- ✅ Enable VPC Flow Logs

### 2. Application Security
- ✅ Rotate API keys regularly
- ✅ Use secrets manager (AWS Secrets Manager)
- ✅ Enable HTTPS only
- ✅ Implement rate limiting
- ✅ Add request logging

### 3. Database Security
- ✅ Enable encryption at rest
- ✅ Enable encryption in transit (SSL/TLS)
- ✅ Regular backups to S3
- ✅ Enable audit logging
- ✅ Restrict database access by IP

## CI/CD Integration

### GitHub Actions Workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Run Tests
        run: |
          cd backend
          pip install -r requirements.txt
          pytest
      
      - name: Build Docker Image
        run: docker build -t raymond-trading:${{ github.sha }} .
      
      - name: Push to Docker Hub
        run: |
          echo ${{ secrets.DOCKER_PASSWORD }} | docker login -u ${{ secrets.DOCKER_USERNAME }} --password-stdin
          docker push raymond-trading:${{ github.sha }}
      
      - name: Deploy to EC2
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.EC2_HOST }}
          username: ubuntu
          key: ${{ secrets.EC2_PRIVATE_KEY }}
          script: |
            cd raymond-v2-8-trader
            git pull origin main
            docker-compose -f docker-compose.prod.yml down
            docker-compose -f docker-compose.prod.yml up -d
            docker-compose -f docker-compose.prod.yml exec backend python app/migrations.py create
```

## Rollback Procedure

```bash
# If deployment fails, rollback:

# 1. Stop current deployment
sudo docker-compose -f docker-compose.prod.yml down

# 2. Restore from backup
sudo docker-compose -f docker-compose.prod.yml exec -T postgres psql \
  -U raymond_user raymond_prod < backup-previous.sql

# 3. Redeploy previous version
git revert HEAD
sudo docker-compose -f docker-compose.prod.yml up -d

# 4. Verify
curl https://your-domain.com/health
```

## Troubleshooting

### Issue: High CPU/Memory Usage

```bash
# Check container stats
docker stats

# Restart service
sudo docker-compose -f docker-compose.prod.yml restart backend
```

### Issue: Database Connection Errors

```bash
# Check database logs
sudo docker-compose -f docker-compose.prod.yml logs postgres

# Verify connection
sudo docker-compose -f docker-compose.prod.yml exec postgres psql \
  -U raymond_user -d raymond_prod -c "SELECT 1"
```

### Issue: SSL Certificate Expired

```bash
# Renew with Let's Encrypt
sudo certbot certonly --standalone -d your-domain.com

# Copy to ssl folder
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ssl/key.pem

# Restart nginx
sudo docker-compose -f docker-compose.prod.yml restart nginx
```

---

**Last Updated:** September 8, 2024
