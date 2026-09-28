# Zip Deploy Strategy for Python Agent Stack

- Overview
- Hosted agent placement
- MCP API deployment
- Frontend deployment
- When to revisit containers
- References

## Overview

Zip deploy on App Service is the intended way to remove the Azure Container Registry dependency for the Python MCP APIs. This is a target architecture, not a verified deployment: [the current Bicep infrastructure](../infra/main.bicep) still provisions Container Apps and ACR, while the application manifest and CI target App Service.

## Hosted agent placement

The orchestrator is intended to run as a Foundry Hosted Agent. The hosted-agent azd manifest now lives at [app/backend/azure.yaml](../app/backend/azure.yaml), and commands should be run with `--cwd app/backend` from repository root. The current [ChatKit server](../app/backend/app/main_chatkit_server.py) is a FastAPI app, not an AgentServer Responses entry point, so hosted deployment still depends on completing that runtime integration.

## MCP API deployment

The account, transaction, and payment MCP servers are FastAPI projects that only rely on Python packages. App Service build automation (set the SCM_DO_BUILD_DURING_DEPLOYMENT setting to true) restores dependencies during zip deploy, which matches the requirements captured in [plan/00-decisions.md](plan/00-decisions.md). Select an App Service plan SKU (for example B1, B2, or P1v3) that aligns with the expected concurrent tool calls. The plan choice determines available cores and memory, so no additional CPU tuning step is required.

For zip deploy, each Python API directory must include a `requirements.txt` file. In this repository, `pyproject.toml` remains the local development source of truth, and `requirements.txt` is the deployment artifact consumed by Oryx on App Service.

Generate or refresh the deployment artifact from each service folder:

```bash
cd app/business-api/account
uv pip compile pyproject.toml -o requirements.txt

cd ../transaction
uv pip compile pyproject.toml -o requirements.txt

cd ../payment
uv pip compile pyproject.toml -o requirements.txt
```

## Frontend deployment

The banking web frontend can target App Service once production assets are built and a static serving strategy, including SPA routing, is configured. The current workflow packages source files without running the Vite build, and removing nginx did not provide a replacement server. Do not treat the frontend ZIP as deployable yet.

## When to revisit containers

Stay with zip deploy while workloads remain single instance, use pure Python wheels, and avoid OS level dependencies. Switch back to Container Apps backed by ACR if any of these scenarios appear:

- Native libraries that require system packages not present in the App Service Python image
- Autoscaling past the limits of the selected plan or needing custom horizontal rules
- Long running background jobs or sidecars that must share a Container Apps environment

## References

- [Quickstart: Deploy a Python web app to Azure App Service](https://learn.microsoft.com/azure/app-service/quickstart-python#deploy-your-application-code-to-azure)
- [Configure a Linux Python app for Azure App Service](https://learn.microsoft.com/azure/app-service/configure-language-python)
- [Run your app from a ZIP package in Azure App Service](https://learn.microsoft.com/azure/app-service/deploy-run-package)
- [Deploy a Python Flask app with azd](https://learn.microsoft.com/azure/app-service/tutorial-python-postgresql-app-flask#modify-sample-code-and-redeploy)
