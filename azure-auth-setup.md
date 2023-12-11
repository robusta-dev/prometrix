# Azure managed Prometheus

In order to authenticate against the Azure Monitor Workspace Query endpoint, you have multiple options:

- Create an Azure Active Directory authentication app [Option #1](#option-1-create-an-azure-authentication-app)
  - Pros:
    - Quick setup. Just need to create an app, get the credentials and add them to the manifests
    - Other pods can't use the Service Principal without having the secret
  - Cons:
    - Requires a service principal (Azure AD permission)
    - Need the client secret in the kubernetes manifests
    - Client secret expires, you need to manage its rotation
- Use Kubelet's Managed Identity [Option #2](#option-2-use-kubelets-managed-identity)
  - Pros:
    - Quick setup. Get the Managed Identity Client ID and add them to the manifests
    - No need to manage secrets. Removing the password element decreases the risk of the credentials being compromised
  - Cons:
    - Managed Identity is bound to the AKS nodepool, so any pods can use it if they know/get the client ID
- Use Azure AD Workload Identity [Option #3](#option-3-use-azure-workload-identity-recommended)
  - Pros:
    - Most secure option as Managed Identity is only bound to the pod. No other pods can use it
    - No need to manage secrets. Removing the password element decreases the risk of the credentials being compromised
  - Cons:
    - Extra setup needed: need AKS cluster with Workload Identity add-on enabled, get the OIDC issuer URL and add it to the manifests

## Get the Azure prometheus query endpoint

1. Go to [Azure Monitor workspaces](https://portal.azure.com/#view/HubsExtension/BrowseResource/resourceType/microsoft.monitor%2Faccounts>) and choose your monitored workspace.
2. In your monitored workspace, `overview`, find the ``Query endpoint`` and copy it.

## Option #1: Create an Azure authentication app

We will now create an Azure authentication app and get the necesssary credentials so the prometrix client can access Prometheus data.

1. Follow this Azure guide to [Register an app with Azure Active Director](https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/prometheus-self-managed-grafana-azure-active-directory#register-an-app-with-azure-active-directory)

```python
    # Create a custom Prometheus client for Azure Prometheus using Service Principal Authentication
    azure_config = AzurePrometheusConfig(
        url="https://azure-prometheus.example.com", # Replace with your Azure Monitor workspace query endpoint
        azure_resource="https://prometheus.monitor.azure.com", # Default resource for Azure Monitor
        azure_token_endpoint="https://azure-token.example.com",
        azure_client_id="YOUR_AZURE_CLIENT_ID",
        azure_tenant_id="YOUR_AZURE_TENANT_ID",
        azure_client_secret="YOUR_AZURE_CLIENT_SECRET",
        additional_labels={"job": "azure-prometheus"},
    )
    azure_client = get_custom_prometheus_connect(azure_config)
```

3. Complete the [Allow your app access to your workspace](https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/prometheus-self-managed-grafana-azure-active-directory#allow-your-app-access-to-your-workspace>) step, so your app can query data from your Azure Monitor workspace.

## Option #2: Use Kubelet's Managed Identity

1. Get the AKS kubelet's Managed Identity Client ID:

```bash
  az aks show -g <resource-group> -n <cluster-name> --query identityProfile.kubeletidentity.clientId -o tsv
```

2. Set the following settings based from the previous step.

```python
  # Create a custom Prometheus client for Azure Prometheus using Azure Managed Identity
  azure_config = AzurePrometheusConfig(
      url="https://azure-prometheus.example.com", # Replace with your Azure Monitor workspace query endpoint
      azure_use_managed_id=True,
      azure_resource="https://prometheus.monitor.azure.com", # Default resource for Azure Monitor
      azure_metadata_endpoint="http://169.254.169.254/metadata/identity/oauth2/token", # Default endpoint for Managed Identity
      azure_client_id="YOUR_AZURE_CLIENT_ID", # Client ID from step 1
      azure_tenant_id="YOUR_AZURE_TENANT_ID",
      additional_labels={"job": "azure-prometheus"},
  )
  azure_client = get_custom_prometheus_connect(azure_config)
```

3. Give access to your Managed Identity on your Azure Monitor Workspace:
   - Open the Access Control (IAM) page for your Azure Monitor workspace in the Azure portal.
   - Select Add role assignment.
   - Select Monitoring Data Reader and select Next.
   - For Assign access to, select Managed identity.
   - Select + Select members.
   - Select the Managed Identity you got from step 1
   - Select Review + assign to save the configuration.

## Option #3: Use Azure Workload Identity (Recommended)

1. Requirements

AKS cluster needs to have Workload Identity add-on and OIDC issuer enabled. You can use `--enable-oidc-issuer --enable-workload-identity` with `az aks create` or `az aks update` to enable them.

2. Create a new Managed Identity. Change the Identity name, resource group and location to match your environment.

```bash
  export SUBSCRIPTION="$(az account show --query id --output tsv)"
  az identity create --name <identity-name> --resource-group <resource-group> --location "eastus" --subscription "${SUBSCRIPTION}" # keep the identity name for step 4
  az identity show --name <identity-name> --resource-group <resource-group> -query clientId -o tsv # keep this value for the step #3
```

3. Set the following settings based from the previous step.

```python
  # Create a custom Prometheus client for Azure Prometheus using Azure Managed Identity
  azure_config = AzurePrometheusConfig(
      url="https://azure-prometheus.example.com", # Replace with your Azure Monitor workspace query endpoint
      azure_use_workload_id=True,
      azure_resource="https://prometheus.monitor.azure.com", # Default resource for Azure Monitor
      azure_token_endpoint="https://azure-token.example.com",
      azure_client_id="YOUR_AZURE_CLIENT_ID", # Client ID from step 2
      azure_tenant_id="YOUR_AZURE_TENANT_ID",
      additional_labels={"job": "azure-prometheus"},
  )
  azure_client = get_custom_prometheus_connect(azure_config)
```

4. Federate the Service Account with the Managed Identity. Replace the values with the ones from the step #1.

```bash
  export AKS_OIDC_ISSUER="$(az aks show -g <resource-group> -n <cluster-name> --query "oidcIssuerProfile.issuerUrl" -otsv)" # Replace with the corresponding values of your AKS clusters.
  MY_NAMESPACE="mynamespace" # Replace with the namespace where your application is deployed
  MY_SERVICE_ACCOUNT="my-service-account" # Replace with the service account name used by your application
  az identity federated-credential create --name <federated-identity-name> --identity-name <identity-name> --resource-group <resource-group> --issuer ${AKS_OIDC_ISSUER} --subject system:serviceaccount:$MY_NAMESPACE:$MY_SERVICE_ACCOUNT # Use identity name from step 2
```

5. Give access to your Managed Identity on your workspace:
   - Open the Access Control (IAM) page for your Azure Monitor workspace in the Azure portal.
   - Select Add role assignment.
   - Select Monitoring Data Reader and select Next.
   - For Assign access to, select Managed identity.
   - Select + Select members.
   - Select the Managed Identity you got from step 2
   - Select Review + assign to save the configuration.