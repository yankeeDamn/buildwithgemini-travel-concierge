#!/bin/bash
set -e

# Change to the frontend directory
cd "$(dirname "$0")"

# Install requirements
pip install -r requirements.txt

# Extract AGENT_ENGINE_RESOURCE_NAME from deployment_metadata.json
export AGENT_ENGINE_RESOURCE_NAME=$(python -c "import json; print(json.load(open('../deployment_metadata.json'))['remote_agent_runtime_id'])" 2>/dev/null)
export AGENT_DIRECTORY="app"
export PORT=8080

echo "Starting proxy against: $AGENT_ENGINE_RESOURCE_NAME"
python main.py
