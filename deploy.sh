#!/bin/bash
# filepath: /opt/update_app.sh

# Configuration
APP_DIR="/opt/dynamic-image-genapp"
LOG_FILE="/opt/app_update.log"

# Start logging
echo "Starting update at $(date)" > $LOG_FILE

# Update repository
cd "$APP_DIR" || { echo "App directory not found" >> $LOG_FILE; exit 1; }
echo "Pulling latest changes..." >> $LOG_FILE
git pull >> $LOG_FILE 2>&1

# Kill existing app instances
echo "Stopping existing app..." >> $LOG_FILE
pkill -f "streamlit run app.py" || true

# Check for existing screen sessions and clean up if needed
screen -wipe >> $LOG_FILE 2>&1

# Activate virtual environment and start the app
echo "Starting app in background..." >> $LOG_FILE
screen -dmS streamlit-app bash -c "cd $APP_DIR && source venv/bin/activate && streamlit run app.py --server.port 80 --server.address 0.0.0.0"

echo "Update completed at $(date)" >> $LOG_FILE
echo "App restarted at http://$(hostname -I | awk '{print $1}'):80" >> $LOG_FILE

screen -S streamlit-app
source venv/bin/activate
streamlit run app.py --server.port 80 --server.address 0.0.0.0