# CI-Sage

An agentic system that analyzes GitHub Actions failures and provides intelligent remediation.

## Features

- **Intelligent Analysis**: Uses Claude AI to analyze workflow failures and identify root causes
- **Automated Remediation**: Provides specific remediation steps and can propose patches
- **Learning System**: Stores error signatures to improve future analysis
- **Issue Management**: Automatically creates/updates issues with triage labels
- **Check Runs**: Posts detailed analysis as GitHub Check Runs

## Architecture

```
GitHub Webhook → FastAPI Server → Claude Analysis → GitHub API Actions
     ↓              ↓                ↓                    ↓
  Log Ingestion → Error Storage → Learning System → Remediation
```

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. Run the application:
   ```bash
   uvicorn app.main:app --reload
   ```

## GitHub App Configuration

1. Create a GitHub App with the following permissions:
   - Actions: Read
   - Checks: Write
   - Issues: Write
   - Pull requests: Write
   - Contents: Read

2. Subscribe to webhook events:
   - `workflow_run`

3. Set webhook URL to your deployed endpoint

## Environment Variables

create `.env` for required configuration.
