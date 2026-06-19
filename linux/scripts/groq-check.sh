#!/bin/bash
set -e

# Verify that the GROQ_API_KEY environment variable is set
if [ -z "$GROQ_API_KEY" ]; then
  echo "Error: GROQ_API_KEY environment variable not set."
  exit 1
fi

# Query the Groq models endpoint (lightweight request)
response=$(curl -s -H "Authorization: Bearer $GROQ_API_KEY" https://api.groq.com/openai/v1/models)

# Simple check for a successful JSON payload
if echo "$response" | grep -q '"object":"list"'; then
  echo "Groq API reachable and authentication succeeded."
else
  echo "Failed to communicate with Groq API. Response was:"
  echo "$response"
  exit 1
fi
