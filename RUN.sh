#!/bin/bash

# RAYMOND v2.8 - One-Command Startup Script
# This script sets up and runs the trading system using Docker

set -e

echo "🚀 RAYMOND v2.8 Trading System - Starting..."
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    echo "   Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

echo "✓ Docker found"

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "⚠️  docker-compose not found, trying 'docker compose'..."
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

echo "✓ Using: $COMPOSE_CMD"
echo ""

# Build and start services
echo "📦 Building Docker image..."
$COMPOSE_CMD build

echo ""
echo "🔧 Starting services..."
$COMPOSE_CMD up -d

echo ""
echo "⏳ Waiting for backend to be ready..."

# Wait for the service to be healthy
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Backend is ready!"
        break
    fi
    echo -n "."
    sleep 1
done

echo ""
echo "==============================================="
echo "✅ RAYMOND v2.8 is RUNNING"
echo "==============================================="
echo ""
echo "📊 API Dashboard: http://localhost:8000/docs"
echo "💚 Health Check:  http://localhost:8000/health"
echo "😄 Joke Endpoint: http://localhost:8000/joke"
echo ""
echo "📖 API Endpoints Available:"
echo "   • Market Data:     /api/market/*"
echo "   • Trading:        /api/trading/*"
echo "   • Strategy:       /api/strategy/*"
echo "   • Risk Manager:   /api/risk/*"
echo "   • Admin:          /api/admin/*"
echo ""
echo "🛑 To stop the system:"
echo "   $COMPOSE_CMD down"
echo ""
echo "📋 To view logs:"
echo "   $COMPOSE_CMD logs -f backend"
echo ""
echo "🧪 Test the API:"
echo "   curl http://localhost:8000/health"
echo ""
echo "⚠️  IMPORTANT: Live trading is DISABLED by default (safe mode)"
echo ""
echo "==============================================="
