---
page_type: sample
languages:
  - azdeveloper
  - python
  - bicep
  - typescript
  - html
products:
  - ai-services
  - azure
  - azure-openai
  - active-directory
  - azure-cognitive-search
  - azure-container-apps
  - azure-sdks
  - github
  - azure-monitor
  - azure-pipelines
urlFragment: agent-openai-python-banking-assistant
name: Multi Agents Banking Assistant with Python and Microsoft Agent Framework
description: A Python sample app emulating a personal banking AI-powered assistant to inquire about account balances, review recent transactions, or initiate payments
---

<!-- YAML front-matter schema: https://review.learn.microsoft.com/en-us/help/contribute/samples/process/onboarding?branch=main#supported-metadata-fields-for-readmemd -->
<!-- prettier-ignore -->
<div align="center">

![](./docs/assets/robot-agents-small.png)

</div>

# Multi Agent Banking Assistant

This hackathon prototype extends Microsoft's public [Azure-Samples/agent-openai-python-banking-assistant](https://github.com/Azure-Samples/agent-openai-python-banking-assistant) sample. The current work focuses on the Account / Transaction / Payment inquiry workflow; planned data, authentication, localization, and evaluation changes are tracked in [the prototype plan](./plan/README.md).

A banking personal assistant designed to revolutionize the way users interact with their bank account information, transaction history, and payment functionalities. Utilizing the power of generative AI within a multi-agent architecture, this assistant aims to provide a seamless, conversational interface through which users can effortlessly access and manage their financial data.

Even if specific to banking scenarios, this sample can be used for other business use cases as technical reference architecture concerning customer support chatbots or virtual assistants using Microsoft Agent Framework to implement supervisor based orchestration for multiple domains agents that need to integrate with business domains API through MCP. AI-powered assistants in other domains by adapting the agents tools and backend services to your specific business needs.

<div align="center">
  
[**BUSINESS SCENARIO**](#business-scenario)  \| [**SOLUTION OVERVIEW**](#solution-overview)  \| [**QUICK DEPLOY**](#quick-deploy)  \| [**SUPPORTING DOCUMENTATION**](#supporting-documentation)

</div>
<br/>

**Note:** With any AI solutions you create using these templates, you are responsible for assessing all associated risks and for complying with all applicable laws and safety standards. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).
<br/>

<h2><img src="./docs/assets/business-scenario.png" width="48" />
Business scenario
</h2>

<div align="center">  
<img src="./docs/assets/banking-web.gif" alt="Banking Web Demo">
</div>
<br/>

Revolutionize the way users interact with their bank account information, transaction history, and payment functionalities.
Instead of navigating through traditional web interfaces and menus, users can simply converse with the AI-powered assistant to inquire about their account balances, credit cards, review recent transactions, or initiate payments. This approach not only enhances user experience by making financial management more intuitive and accessible but also leverages the existing workload data and APIs to ensure a reliable and secure service.

The payment agent can initiate payments using bill details supplied in text by the user. Invoice samples remain in the data folder, but automated invoice-image extraction is not enabled. The business APIs currently serve sample account, transaction, and payment data through REST endpoints and MCP tools; the PostgreSQL migration is planned, not deployed.

### Key Features

<details open>
  <summary>Click to learn more about the key features this solution enables</summary>
 
 - **Add agentic conversational experience to your existing website** <br/>
The React frontend supports attachment uploads backed by Blob storage; the payment agent cannot extract fields from uploaded invoices.
 - **Multi-agent supervisor architecture** <br/>
 Use agents-as-tools or hand-off orchestration to implement supervisor agent to understand user intents and delegate tasks to specific domain agents. Agents are using **gpt-4.1** on [Azure AI Foundry](https://azure.microsoft.com/en-us/products/ai-foundry)
 - **Reusing existing business APIs as MCP tools** <br/>
 Business service logic is exposed to agents through MCP using [fastmcp](https://gofastmcp.com/getting-started/welcome) 
 - **Microsoft Agent Framework First** <br/>
 Use [MAF](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview) chat agents to flexibly support AzureOpenAI or Foundry Agent Service based agents
 - **Human-In-The-Loop (HITL) patterns** <br/>
 Rich human-in-the-loop experience supporting agents progress notification and tool approval using [Open AI chatkit protocol](https://platform.openai.com/docs/guides/chatkit).
- **Separate hosted agent and App Services** <br/>
The Foundry hosted agent uses its own azd project; the root Terraform stack defines four App Services for the web and business APIs.
- **Automated IaC and App build & Deployment**
Automated Azure resources creation and solution deployment leveraging [Azure Developer CLI](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/).

</details>
<br/>

<h2><img src="./docs/assets/solution-overview.png" width="48" />
Solution overview
</h2>

### Solution architecture

| ![image](docs/assets/HLA-Agent-Framework.png) |
| --------------------------------------------- |

The home banking assistant is designed as conversational multi-agent system with each agent specializing in a specific functional domain (e.g., account management, transaction history, payments).Business services logic is exposed to agents through MCP endpoint running on domain driven microservice.
Agents-to-Chat communication protocol is based on [OpenAI Chatkit protocol](<(https://github.com/openai/chatkit-js)>) handling SSE streams from a unified POST endpoint; It extends original ChatKit Microsoft agent-framework implementation in order support client-managed widgets and multi-agent workflows.

### Additional resources

- [Skilling-Presentation](./docs/Home%20Banking%20Assistant.pdf)
- [Technical Architecture](./docs/technical-architecture.md)
- [Chat-to-Agent Conversational protocol implementation](./docs/chat-server-protocol.md)
- For Semantic Kernel version check this [branch](https://github.com/Azure-Samples/agent-openai-python-banking-assistant/tree/semantic-kernel)

<br /><br />

<h2><img src="./docs/assets/quick-deploy.png" width="48" />
Quick Deploy 
</h2>

| [![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/Azure-Samples/agent-openai-python-banking-assistant) | [![Open in Dev Containers](https://img.shields.io/static/v1?style=for-the-badge&label=Dev%20Containers&message=Open&color=blue&logo=visualstudiocode)](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/Azure-Samples/agent-openai-python-banking-assistant) |
| --------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

<br/>

### Prerequisites

- [Python >= 3.11](https://www.python.org/downloads/release/python-31113/)
- [uv](https://github.com/astral-sh/uv)
- [Azure Developer CLI](https://aka.ms/azure-dev/install)
- [Node.js](https://nodejs.org/en/download/)
- [Git](https://git-scm.com/downloads)
- [Powershell 7+ (pwsh)](https://github.com/powershell/powershell) - For Windows users only.
  - **Important**: Ensure you can run `pwsh.exe` from a PowerShell command. If this fails, you likely need to upgrade PowerShell.

> [!WARNING]
> Your Azure Account must have `Microsoft.Authorization/roleAssignments/write` permissions, such as [User Access Administrator](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles#user-access-administrator) or [Owner](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles#owner).

Clone this repository and select an azd environment. Before provisioning the root stack, prepare an existing resource group and Terraform remote-state storage as described in [Terraform provisioning](./infra/README.md). Import existing resources and review the Terraform plan before provisioning a previously deployed environment.

### Deploy targets in this repository

This repository intentionally uses two separate Azure Developer CLI project roots:

- Root project (`./azure.yaml`): Terraform provisions the shared Linux plan, four App Services, monitoring, Blob attachment storage, and a dedicated Foundry account and project; root `azd deploy` deploys only the App Service workloads.
- Backend project (`./app/backend/azure.yaml`): the `microsoft.foundry` provider deploys the hosted agent to the existing Foundry project. Set its `FOUNDRY_PROJECT_ENDPOINT` from the root environment output before deploying; the two azd environments are separate.

Naming note for the App Service stack: the frontend app uses `app-banking-web-<env>` (for example, `app-banking-web-development`) so the web workload name is explicit and distinct from backend services.

Use these commands from the repository root:

```shell
# Provision the App Service and dedicated Foundry resources after remote state setup and plan review
azd provision
azd deploy

# Configure and deploy the separate hosted-agent project after local agent validation
# azd env set FOUNDRY_PROJECT_ENDPOINT <root FOUNDRY_PROJECT_ENDPOINT> --cwd app/backend
azd up --cwd app/backend
```

For iterative agent updates only:

```shell
azd deploy --cwd app/backend
```

The current ChatKit server keeps threads, items, and attachment metadata in local SQLite; Blob storage holds uploaded attachment bytes. Foundry Responses history, linked by `conversation` or `previous_response_id`, is separate and does not replace ChatKit persistence. No Cosmos DB is provisioned, and a durable per-user ChatKit store is still required before production deployment.

For more info about deployment click [here](./docs/deployment-guide.md)

🛠️ **Need Help?** Check our [Troubleshooting Guide](./docs/troubleshooting.md) for solutions to common deployment issues.
<br/><br/>

### Prerequisites and costs

Pricing varies per region and usage, so it isn't possible to predict exact costs for your usage.
However, you can try the [Azure pricing calculator](https://azure.com/e/8ffbe5b1919c4c72aed89b022294df76) for the resources below.

- Azure App Service: a shared Linux B1 plan for the four apps. [Pricing](https://azure.microsoft.com/en-us/pricing/details/app-service/linux/)
- Azure Blob Storage: Standard LRS for ChatKit attachment bytes. [Pricing](https://azure.microsoft.com/pricing/details/storage/blobs/)
- Azure Monitor: Log Analytics and Application Insights, billed by usage. [Pricing](https://azure.microsoft.com/en-us/pricing/details/monitor/)
- The separate Foundry project and model usage have their own costs.

Do not run `azd down` against an existing shared resource group as a rollback strategy; review the Terraform plan and resource ownership first.

### Local development (VS Code)

Start the account (8070), transaction (8071), and payment (8072) MCP services, the ChatKit backend (8080), and the Vite frontend in separate terminals. The commands and environment variables are in the [business API](./app/business-api/README.md), [backend](./app/backend/README.md), and [frontend](./app/frontend/banking-web/README.md) guides. Open the URL printed by Vite, normally `http://localhost:5170/`.

In VS Code, press `F5` with `DEV - Full Stack Ordered` to start all five services and open the frontend at `http://localhost:5170/`. The frontend task waits for Vite to report that URL; port `5170` must be available for this launch configuration.

The backend ChatKit server at `http://localhost:8080/` only exposes API endpoints, so the root path returns `404 Not Found` by design.

For local Azure OpenAI inference with `PROFILE=dev`, sign in with `az login` using an identity that has the `Cognitive Services OpenAI User` role on the configured Azure AI Services resource. The Azure account selected in VS Code is independent of the Azure CLI identity used by the backend; a successful `/chatkit` HTTP 200 alone does not confirm model access.

**Local verification (2026-09-26):** A browser request to `/chatkit` completed a transaction-history inquiry: the supervisor handed off to `TransactionHistoryAgent`, `getAccountsByUserName` and `getTransactionsByRecipientName` succeeded through the local MCP services, and Azure OpenAI returned HTTP 200. The UI displayed the payment history and final answer. This verifies that inquiry path locally, not payment execution, end-user authorization, or a deployed environment.

<h2><img src="./docs/assets/supporting-documentation.png" width="48" />
Supporting documentation
</h2>

### Restrict access to the public web app

The root Terraform stack does not configure end-user authentication or access restrictions for the web app. Do not expose real customer data until the planned email/password JWT authentication and service-layer resource ownership checks are implemented.

### Security guidelines

> [!IMPORTANT]
> **This sample is a proof-of-concept and does not implement app authentication or authorization**.

The sample does not cover the following aspects, essential to the security of the solution:

- **No isolation of user conversations**: After app deployment on Azure, the platform does not isolate conversations or other persisted state by end user.
- **No authentication or authorization of end users**: The planned JWT authentication and customer ownership checks are not implemented yet.

When deploying to production with real customer data, consider implementing:

- **End-user authentication and authorization integrated with your identity provider**
- **Conversation and data isolation per user and per account**
- **Audit logging of all access and operations**
- **Compliance with applicable regulations (PCI-DSS, GDPR, local banking regulations)**

### Resources

Here are some resources to learn more about multi-agent architectures and technologies used in this sample:

- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- [AI agents For Beginners](https://github.com/microsoft/ai-agents-for-beginners)
- [Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-azure-ai-foundry)
- [Develop AI apps using Azure services](https://aka.ms/azai)
- [Building Effective Agents - Anthropic](https://www.anthropic.com/engineering/building-effective-agents)
- [AI agent orchestration patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

You can also find [more Microsoft Foundry agents samples here](https://aka.ms/aiapps)

## Getting Help

If you get stuck or have any questions about building AI apps, join:

[![Azure AI Foundry Discord](https://img.shields.io/badge/Discord-Azure_AI_Foundry_Community_Discord-blue?style=for-the-badge&logo=discord&color=5865f2&logoColor=fff)](https://aka.ms/foundry/discord)

If you have product feedback or errors while building visit:

[![Azure AI Foundry Developer Forum](https://img.shields.io/badge/GitHub-Azure_AI_Foundry_Developer_Forum-blue?style=for-the-badge&logo=github&color=000000&logoColor=fff)](https://aka.ms/foundry/forum)

## Troubleshooting

If you have any issue when running or deploying this sample [open an issue](https://https://github.com/Azure-Samples/agent-openai-python-banking-assistant/issues) in this repository.

## Contributing

This project welcomes contributions and suggestions. Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.opensource.microsoft.com.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.

## Responsible AI Transparency

This AI multi-agent Banking Assistant template is provided ‘as-is’ and ‘without warranty’ under the MIT license. Any AI solutions developed or deployed using these types of agentic templates require that you and your organization carefully evaluate all relevant requirements and risks, and ensure compliance with applicable laws, guidelines, and safety standards. Caution is strongly advised when utilizing this template—particularly in [sensitive domains](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note?view=foundry-classic#disclaimer-about-agents-in-sensitive-domains)—to develop autonomous agentic AI actions that may be irreversible. For further details, please consult the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note?view=foundry-classic) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).”

## Disclaimers

To the extent that the Software includes components or code used in or derived from Microsoft products or services, including without limitation Microsoft Azure Services (collectively, “Microsoft Products and Services”), you must also comply with the Product Terms applicable to such Microsoft Products and Services. You acknowledge and agree that the license governing the Software does not grant you a license or other right to use Microsoft Products and Services. Nothing in the license or this ReadMe file will serve to supersede, amend, terminate or modify any terms in the Product Terms for any Microsoft Products and Services.

You must also comply with all domestic and international export laws and regulations that apply to the Software, which include restrictions on destinations, end users, and end use. For further information on export restrictions, visit https://aka.ms/exporting.

You acknowledge that the Software and Microsoft Products and Services (1) are not designed, intended or made available as a medical device(s), and (2) are not designed or intended to be a substitute for professional medical advice, diagnosis, treatment, or judgment and should not be used to replace or as a substitute for professional medical advice, diagnosis, treatment, or judgment. Customer is solely responsible for displaying and/or obtaining appropriate consents, warnings, disclaimers, and acknowledgements to end users of Customer’s implementation of the Online Services.

You acknowledge the Software is not subject to SOC 1 and SOC 2 compliance audits. No Microsoft technology, nor any of its component technologies, including the Software, is intended or made available as a substitute for the professional advice, opinion, or judgement of a certified financial services professional. Do not use the Software to replace, substitute, or provide professional financial advice or judgment.

BY ACCESSING OR USING THE SOFTWARE, YOU ACKNOWLEDGE THAT THE SOFTWARE IS NOT DESIGNED OR INTENDED TO SUPPORT ANY USE IN WHICH A SERVICE INTERRUPTION, DEFECT, ERROR, OR OTHER FAILURE OF THE SOFTWARE COULD RESULT IN THE DEATH OR SERIOUS BODILY INJURY OF ANY PERSON OR IN PHYSICAL OR ENVIRONMENTAL DAMAGE (COLLECTIVELY, “HIGH-RISK USE”), AND THAT YOU WILL ENSURE THAT, IN THE EVENT OF ANY INTERRUPTION, DEFECT, ERROR, OR OTHER FAILURE OF THE SOFTWARE, THE SAFETY OF PEOPLE, PROPERTY, AND THE ENVIRONMENT ARE NOT REDUCED BELOW A LEVEL THAT IS REASONABLY, APPROPRIATE, AND LEGAL, WHETHER IN GENERAL OR IN A SPECIFIC INDUSTRY. BY ACCESSING THE SOFTWARE, YOU FURTHER ACKNOWLEDGE THAT YOUR HIGH-RISK USE OF THE SOFTWARE IS AT YOUR OWN RISK.
