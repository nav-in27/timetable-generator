#!/usr/bin/env bash
# Render build script for backend

# Install dependencies
pip install -r requirements.txt

# Run database migrations/seeding if needed
python -c "from app.db.base import init_db; init_db()"
