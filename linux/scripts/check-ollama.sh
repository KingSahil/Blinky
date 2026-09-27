#!/bin/bash
set -e # Stops the script immediately if any command fails (equivalent to $ErrorActionPreference = "Stop")

# Fetch the tags JSON and extract the model names into a list
if ! response=$(curl -s http://localhost:11434/api/tags); then
    echo "Error: Could not connect to Ollama. Is the service running?"
    exit 1
fi

# Extract model names using jq
models=$(echo "$response" | jq -r '.models[].name')

# Check if the specific model is in the list
if ! echo "$models" | grep -q "^gemma4:e4b$"; then
    echo "gemma4:e4b was not found. Run: ollama pull gemma4:e4b"
    exit 1
fi

echo "Ollama is running and gemma4:e4b is available."