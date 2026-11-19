# Despliegue de TraceTrust en Azure Container Apps

Esta receta está pensada para una demo de pocos días: una Container App para
TraceTrust, PostgreSQL Flexible Server y un Azure Files share montado en
`/data`. El endpoint de ingesta queda protegido con `TRACETRUST_API_KEY`.

## Recursos

```powershell
$location = "eastus"
$resourceGroup = "rg-tracop-demo"
$environment = "tracop-demo-env"
$app = "tracetrust-api"
$apiKey = "genera-un-secreto-largo"

az group create --name $resourceGroup --location $location
az containerapp env create --name $environment --resource-group $resourceGroup --location $location
az postgres flexible-server create `
  --resource-group $resourceGroup --name tracop-demo-pg --location $location `
  --tier Burstable --sku-name Standard_B1ms --storage-size 32 --version 16 `
  --admin-user tracopadmin --admin-password "CAMBIA-ESTE-SECRETO"
```

Para esta primera demo TraceTrust puede usar snapshots en `/data`. El adaptador
PostgreSQL sigue disponible para persistir el modelo analítico en una fase
posterior.

## Azure Files

```powershell
az storage account create --name tracopdemostorage --resource-group $resourceGroup --sku Standard_LRS
$storageKey = az storage account keys list --account-name tracopdemostorage --resource-group $resourceGroup --query "[0].value" -o tsv
az storage share-rm create --resource-group $resourceGroup --storage-account tracopdemostorage --name tracetrust-data --quota 32
az containerapp env storage set `
  --name $environment --resource-group $resourceGroup --storage-name tracetrustfiles `
  --azure-file-account-name tracopdemostorage --azure-file-account-key $storageKey `
  --azure-file-share-name tracetrust-data --access-mode ReadWrite
```

## Imagen y aplicación

Desde la raíz de TraceTrust:

```powershell
az containerapp up --name $app --resource-group $resourceGroup --location $location `
  --environment $environment --source . --ingress external --target-port 8000
az containerapp secret set --name $app --resource-group $resourceGroup --secrets tracetrust-api-key=$apiKey
az containerapp update --name $app --resource-group $resourceGroup `
  --set-env-vars TRACETRUST_DATA_ROOT=/data TRACETRUST_API_KEY=secretref:tracetrust-api-key
```

Después de crear la app, aplicar el mount definido en
[`tracetrust-volume.yaml`](tracetrust-volume.yaml):

```powershell
az containerapp update --name $app --resource-group $resourceGroup --yaml deploy/azure/tracetrust-volume.yaml
```

El YAML conserva la imagen/variables existentes y añade el volumen Azure Files
en `/data`. Si el CLI exige el FQDN completo del registry, obtenerlo con
`az containerapp show` y mantener la imagen generada por `az containerapp up`.

## Conectar Trackup

```powershell
$tracetrustUrl = az containerapp show --name $app --resource-group $resourceGroup --query properties.configuration.ingress.fqdn -o tsv
Invoke-RestMethod "https://$tracetrustUrl/ready"
```

El worker de Trackup debe llamar a:

```text
POST https://<tracetrustUrl>/api/v1/ingest/trackup
X-API-Key: <apiKey>
Content-Type: application/json
```

El contrato y la regla de mapeo están en
[`docs/trackup-integration.md`](../../docs/trackup-integration.md). Solo se
aceptan eventos canónicos completos dentro de `canonical_event`.

## Limpieza

```powershell
az group delete --name $resourceGroup --yes --no-wait
```
