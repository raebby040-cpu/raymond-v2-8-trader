# RAYMOND v2.8 - Developer Setup Guide

## Prerequisites

- Python 3.11 or higher
- Flutter SDK 3.0+
- Docker & Docker Compose
- Git
- PostgreSQL 14+ (optional, for production)

## Backend Development Setup

### 1. Clone Repository

```bash
git clone https://github.com/raebby040-cpu/raymond-v2-8-trader.git
cd raymond-v2-8-trader/backend
```

### 2. Create Virtual Environment

```bash
python -m venv .venv

# Activate (Linux/macOS)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Setup Environment Variables

```bash
cp .env.example .env
# Edit .env with your values
```

### 5. Initialize Database

```bash
# Create tables
python app/migrations.py create

# Seed demo data
python app/migrations.py seed

# View database info
python app/migrations.py info
```

### 6. Run Backend Server

```bash
uvicorn app.main:app --reload --port 8000
```

Server runs at: `http://localhost:8000`
API Docs at: `http://localhost:8000/docs`

## Frontend Development Setup

### 1. Navigate to Flutter App

```bash
cd ../flutter_app
```

### 2. Get Flutter Dependencies

```bash
flutter pub get
```

### 3. Configure API Base URL

Edit `lib/services/api_client.dart`:
```dart
const String API_BASE_URL = 'http://localhost:8000';
```

### 4. Run on Emulator/Device

```bash
# List connected devices
flutter devices

# Run on Android
flutter run -d android

# Run on specific device
flutter run -d <device_id>
```

## Running Tests

### Backend Tests

```bash
cd backend

# Run all tests
pytest

# Run specific test file
pytest tests/test_strategy.py -v

# Run with coverage report
pytest --cov=app --cov-report=html tests/

# Run async tests
pytest -asyncio tests/test_api.py
```

### Frontend Tests

```bash
cd flutter_app

# Run widget tests
flutter test

# Run integration tests
flutter drive --target=test_driver/app.dart
```

## Code Style & Linting

### Python

```bash
# Lint with flake8
flake8 backend/app/ --max-line-length=127

# Format with black
black backend/app/

# Type checking with mypy
mypy backend/app/
```

### Dart/Flutter

```bash
cd flutter_app

# Analyze code
flutter analyze

# Format code
flutter format lib/

# Fix issues
dart fix --apply
```

## Docker Development

### Start Full Stack

```bash
docker-compose -f docker-compose.dev.yml up
```

Services:
- Backend: http://localhost:8000
- API Docs: http://localhost:8000/docs
- PostgreSQL: localhost:5432

### Rebuild Containers

```bash
docker-compose -f docker-compose.dev.yml up --build
```

### View Logs

```bash
# All services
docker-compose -f docker-compose.dev.yml logs -f

# Specific service
docker-compose -f docker-compose.dev.yml logs -f backend
```

## Database Management

### Connection Strings

**SQLite (Development):**
```
DATABASE_URL=sqlite:///./raymond_trading.db
```

**PostgreSQL (Production):**
```
DATABASE_URL=postgresql://user:password@localhost:5432/raymond_trading
```

### Common Tasks

```bash
# Create all tables
python app/migrations.py create

# Drop all tables (CAREFUL!)
python app/migrations.py drop

# Seed demo data
python app/migrations.py seed

# View database statistics
python app/migrations.py info
```

## Debugging

### Backend Debugging

```python
# Add breakpoint
breakpoint()  # Python 3.7+

# Or use pdb
import pdb; pdb.set_trace()
```

**Debug in VS Code:**
1. Install Python extension
2. Create `.vscode/launch.json`:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--reload"],
      "jinja": true,
      "cwd": "${workspaceFolder}/backend"
    }
  ]
}
```

### Frontend Debugging

```bash
# Run with debug mode
flutter run --debug

# DevTools
flutter pub global activate devtools
flutter pub global run devtools
```

## Common Issues & Solutions

### Issue: Port 8000 already in use

```bash
# Find process using port
lsof -i :8000

# Kill process
kill -9 <PID>

# Or use different port
uvicorn app.main:app --reload --port 8001
```

### Issue: Database locked error

```bash
# Close all connections and reinitialize
rm raymond_trading.db
python app/migrations.py create
python app/migrations.py seed
```

### Issue: Flutter can't connect to backend

```bash
# Check backend is running
curl http://localhost:8000/health

# For Android emulator, use:
http://10.0.2.2:8000

# Update API client in flutter_app/lib/services/api_client.dart
```

### Issue: Module import errors

```bash
# Reinstall dependencies
pip install --upgrade --force-reinstall -r requirements.txt

# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name '*.pyc' -delete
```

## Project Structure

```
raymond-v2-8-trader/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application
│   │   ├── database.py          # Database setup
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── schemas.py           # Pydantic schemas
│   │   ├── strategy.py          # Strategy engine & AI
│   │   ├── brokers.py           # Broker adapters
│   │   ├── risk_management.py   # Risk controls
│   │   ├── market_data.py       # Market data providers
│   │   ├── indicators.py        # Technical indicators
│   │   ├── streaming.py         # Real-time streaming
│   │   └── migrations.py        # Database migrations
│   ├── tests/
│   │   ├── conftest.py          # Test fixtures
│   │   ├── test_strategy.py
│   │   ├── test_brokers.py
│   │   ├── test_risk_management.py
│   │   └── test_api.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── flutter_app/
│   ├── lib/
│   │   ├── main.dart            # App entry point
│   │   ├── screens/
│   │   │   ├── home_screen.dart
│   │   │   ├── market_screen.dart
│   │   │   ├── trading_screen.dart
│   │   │   ├── strategy_screen.dart
│   │   │   └── portfolio_screen.dart
│   │   ├── providers/
│   │   │   ├── market_provider.dart
│   │   │   └── trading_provider.dart
│   │   └── services/
│   │       └── api_client.dart
│   └── pubspec.yaml
├── docker-compose.dev.yml
├── .github/workflows/
│   └── python-package.yml
├── API_DOCUMENTATION.md
├── DEVELOPER_SETUP.md
└── README.md
```

## Next Steps

1. **Read the API Documentation:** `API_DOCUMENTATION.md`
2. **Understand the Architecture:** See diagrams in README.md
3. **Run Tests:** `pytest` in backend folder
4. **Start Development:** Create a feature branch
5. **Submit PR:** Include tests and documentation

---

**Happy Coding!** 🚀
