#!/bin/bash

# Define paths
APP_DIR="/var/www/vhosts/capitaltrading.it/manu.capitaltrading.it"
VENV_DIR="$APP_DIR/venv"

echo "🚀 Starting Deployment for Manu Scalper..."

# 1. Create Virtual Environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv $VENV_DIR
else
    echo "✅ Virtual environment already exists."
fi

# 2. Activate and Install Requirements
echo "⬇️ Installing dependencies..."
source $VENV_DIR/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Fix Permissions (Crucial for Plesk/Systemd user)
# Assuming the user 'capitaltrading.it_fddcguc8kmf' needs access
echo "🔒 Fixing permissions..."
chown -R capitaltrading.it_fddcguc8kmf:psacln $APP_DIR
chmod -R 755 $APP_DIR

echo "✅ Deployment Setup Complete!"
echo "👉 Now run: systemctl restart manu-scalper"
