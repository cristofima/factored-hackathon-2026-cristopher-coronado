# Zip Deploy Strategy for Python Agent Stack

- Overview
- Hosted agent placement
- MCP API deployment
- Frontend deployment
- When to revisit containers
- References

## Overview

Zip deploy on App Service removes the Azure Container Registry dependency for the Python MCP APIs, Responses BFF, and web frontend. The root azd project uses the Terraform stack under [`infra`](../infra/README.md); the hosted agent has a separate azd project.

## Hosted agent placement

The Account/Transaction orchestrator runs through a Foundry Responses host. Its azd manifest lives at [app/backend/azure.yaml](../app/backend/azure.yaml), and commands should be run with `--cwd app/backend` from repository root. Local browser validation uses the local agent on port `8088` through the Responses BFF; hosted deployment is a separate operation.

## MCP API deployment

The Account and Transaction MCP servers are FastAPI projects that rely only on Python packages. The Payment App Service remains in the root infrastructure but is not connected to the active agent workflow. App Service build automation (`SCM_DO_BUILD_DURING_DEPLOYMENT=true`) restores dependencies during zip deploy. Select an App Service plan SKU (for example B1, B2, or P1v3) that aligns with expected concurrent tool calls.

For zip deploy, each Python API directory must include a `requirements.txt` file. In this repository, `pyproject.toml` remains the local development source of truth, and `requirements.txt` is the deployment artifact consumed by Oryx on App Service.

Generate or refresh the deployment artifact from each service folder:

```bash
cd app/business-api/account
uv pip compile pyproject.toml -o requirements.txt

cd ../transaction
uv pip compile pyproject.toml -o requirements.txt
```

## Frontend deployment

The banking web deployment workflow builds the Vite production assets, packages its App Service server, and injects the deployed Account, Transaction, and Responses BFF URLs. The browser calls the BFF `/responses` endpoint and never receives a Foundry credential.

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
