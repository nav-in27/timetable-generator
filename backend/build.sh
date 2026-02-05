#!/usr/bin/env bash
# Render build script for backend
# Exit on error
set -o errexit

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install --no-cache-dir -r requirements.txt

# Run database migrations/seeding if needed
# python seed_data.py
