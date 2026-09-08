# RAYMOND v2.8 Deployment Guide

## Local Development Setup

### Prerequisites
- Python 3.10+
- pip or poetry
- SQLite (included with Python)
- Git

### Quick Start

```bash
# 1. Clone repository
git clone https://github.com/raebby040-cpu/raymond-v2-8-trader.git
cd raymond-v2-8-trader

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
cd backend
pip install -r requirements.txt
pip install -e .  # Install in development mode

# 4. Setup environment
cp .env.example .env
# Edit .env with your local settings

# 5. Initialize database
python -c "from app.models import create_tables; create_tables()"

# 6. Run server
uvicorn app.main:app --reload --port 8000

# 7. Run tests
cd ..
pytest tests/ -v
```

### Development Tools Setup

```bash
# Install dev dependencies
pip install black ruff isort pytest pytest-asyncio pytest-cov mypy

# Format code
black backend/app tests
isort backend/app tests

# Lint
ruff check backend/app tests
mypy backend/app --ignore-missing-imports

# Run tests with coverage
pytest tests/ -v --cov=backend/app --cov-report=html
```

---

## Docker Deployment

### Build Docker Image

```bash
# Build
docker build -f backend/Dockerfile -t raymond-v2.8:latest .

# Run
docker run -p 8000:8000 \
  -e LIVE_TRADING_ENABLED=false \
  -e RAYMOND_ENV=development \
  -e DATABASE_URL=sqlite:///./raymond.db \
  raymond-v2.8:latest
```

### Docker Compose (Production)

```bash
# Using docker-compose.yml
docker-compose up -d

# Check logs
docker-compose logs -f api

# Stop
docker-compose down
```

---

## Production Deployment

### Prerequisites
- PostgreSQL database
- Redis for caching (optional)
- Nginx or reverse proxy
- SSL certificate
- Monitoring & logging infrastructure

### Environment Setup

```bash
# 1. Create production environment
DATABASE_URL=postgresql://user:password@prod-db:5432/raymond
LIVE_TRADING_ENABLED=false  # Keep disabled until approved
RAYMOND_ENV=production
```

### Deployment Steps

```bash
# 1. Pull latest code
git pull origin main

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Run migrations (if needed)
alembic upgrade head

# 4. Run tests
pytest tests/ -v

# 5. Build Docker image
docker build -f backend/Dockerfile -t raymond-v2.8:prod-v1.0 .

# 6. Push to registry
docker push your-registry.com/raymond-v2.8:prod-v1.0

# 7. Deploy to Kubernetes or your container orchestration platform
kubectl apply -f k8s/raymond-deployment.yaml

# 8. Health check
curl https://your-domain.com/health
```

### Health Checks

```bash
# API health
curl -s http://localhost:8000/health | jq

# Database connectivity
curl -s http://localhost:8000/api/admin/status | jq

# Market data
curl -s http://localhost:8000/api/market/price | jq
```

### Monitoring & Logging

```bash
# Tail logs
tail -f logs/raymond.log

# Check error rate
grep ERROR logs/raymond.log | wc -l

# Monitor database
psql -c "SELECT * FROM trades ORDER BY opened_at DESC LIMIT 10;"
```

### Rollback Procedure

```bash
# If deployment fails:
# 1. Check logs
docker-compose logs api

# 2. Rollback to previous version
git checkout main~1
docker build -f backend/Dockerfile -t raymond-v2.8:rollback .

# 3. Restart with previous image
docker-compose up -d
```

---

## Security Checklist

- [ ] SSL/TLS certificate installed
- [ ] Database password changed from default
- [ ] API keys stored in secure vault (not in .env)
- [ ] `LIVE_TRADING_ENABLED=false` by default
- [ ] Emergency stop mechanism tested
- [ ] Rate limiting configured
- [ ] CORS origins restricted
- [ ] All dependencies updated
- [ ] Security scanning passed (Bandit, Trivy)
- [ ] Database backed up before deployment
- [ ] Monitoring and alerting configured

---

## Common Issues

### Port Already in Use
```bash
# Find process using port 8000
lsof -i :8000

# Kill process
kill -9 <PID>

# Or use different port
uvicorn app.main:app --port 8001
```

### Database Connection Error
```bash
# Check database is running
psql -h localhost -U postgres -d raymond

# Reset database
rm raymond.db  # SQLite
alembic downgrade base  # PostgreSQL
alembic upgrade head
```

### Import Errors
```bash
# Reinstall dependencies
pip install --force-reinstall -r backend/requirements.txt

# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} +
```

---

## Support

- **Issues:** https://github.com/raebby040-cpu/raymond-v2-8-trader/issues
- **Documentation:** See README.md
- **Runbook:** See docs/RUNBOOK.md
