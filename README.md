# Agente TDAH

Sistema de recordatorios por llamada telefónica construido sobre AWS. Apuntas una tarea en Notion con fecha, hora y tipo. El sistema envía una notificación push cinco minutos antes, llama por teléfono a la hora indicada, e insiste según la importancia de la tarea si no contestas.

Cuando descuelgas, un agente de voz dice la tarea, ofrece ayuda para empezar, y actúa según lo que respondas.

## Estado

Funcional salvo la llamada saliente a números españoles, pendiente de aprobación de cuota por parte de AWS Support. El resto del circuito está desplegado y probado.

## Arquitectura

```
Notion ──webhook──> API Gateway ──> Lambda receptor
                                          │
                                          ▼
                                   Lambda programador
                                          │
                                          ▼
                                    Step Functions
                                          │
                        ┌─────────────────┼─────────────────┐
                        ▼                 ▼                 ▼
                  Lambda notificador  Lambda verificador  Amazon Connect
                        │                                   │
                     ntfy push                          Amazon Lex
                                                            │
                                                       Lambda voz
                                                            │
                                                   Bedrock · Notion API
```

| Componente | Función |
|---|---|
| API Gateway | Endpoint público para el webhook de Notion y el atajo manual |
| Lambda `receptor` | Valida la firma HMAC del webhook y despacha |
| Lambda `programador` | Lee la tarea, calcula la línea temporal, arranca la ejecución |
| Step Functions | Máquina de estados con esperas absolutas y ramas por tipo de tarea |
| Lambda `notificador` | Envía push por ntfy y lanza la llamada por Connect |
| Lambda `verificador` | Comprueba si la tarea fue atendida antes de cada reintento |
| Lambda `voz` | Fulfillment de Lex, actúa sobre Notion según la intención |
| Amazon Connect | Telefonía saliente y contact flow |
| Amazon Lex V2 | Reconocimiento de intenciones en español |
| Amazon Bedrock | Generación del plan de tres pasos |
| DynamoDB | Estado, idempotencia, control de reintentos |
| Secrets Manager | Credenciales |
| CloudWatch | Logs estructurados y alarmas |

Infraestructura definida con AWS CDK v2 en Python. Región `eu-central-1`.

## Lógica de escalada

`H` es la hora indicada en la tarea.

| Tipo | H-5 min | H | H+5 min | H+15 min |
|---|---|---|---|---|
| Normal | push | llamada | — | — |
| Importante | push | llamada | — | llamada |
| Urgente | push | llamada | llamada | llamada |

Los reintentos se ejecutan solo si la llamada anterior no fue atendida. Al descolgar cualquier llamada, la cadena termina.

## Conversación

El contact flow reproduce el título de la tarea mediante Polly y pasa el control a Lex, que clasifica la respuesta en tres intenciones.

| Intención | Efecto |
|---|---|
| `AyudaIntent` | Bedrock genera tres pasos concretos para la tarea y los lee en voz alta |
| `HechaIntent` | Marca la tarea como Hecho en Notion |
| `AplazarIntent` | Solicita una hora nueva, actualiza Notion y reprograma la ejecución |

El agente no propone aplazar. Solo lo hace si el usuario lo solicita explícitamente.

## Requisitos

- Cuenta de AWS con acceso a Connect, Lex y Bedrock en `eu-central-1`
- Node.js 22 o superior
- Python 3.9 o superior
- AWS CDK v2
- Workspace de Notion
- App ntfy

## Despliegue

Clonar e instalar dependencias.

```bash
git clone <repo>
cd adhd-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Crear el secreto con las credenciales.

```bash
aws secretsmanager create-secret \
  --name adhd-agent/config \
  --region eu-central-1 \
  --secret-string '{
    "NOTION_TOKEN":"",
    "NOTION_DS_ID":"",
    "NOTION_VERIFICATION_TOKEN":"",
    "NTFY_TOPIC":"",
    "SHORTCUT_KEY":"",
    "CONNECT_INSTANCE_ID":"",
    "CONNECT_FLOW_ID":"",
    "CONNECT_FROM":"",
    "CONNECT_TO":""
  }'
```

Desplegar.

```bash
cdk bootstrap aws://<cuenta>/eu-central-1
cdk deploy
```

La salida incluye la URL del webhook, necesaria para configurar la suscripción en Notion.

## Configuración manual

Estos pasos no están cubiertos por el CDK.

1. Base de datos en Notion con las propiedades `Tarea` (title), `Cuando` (date con hora), `Tipo` (select: Normal, Importante, Urgente) y `Estado` (select: Pendiente, Hecho)
2. Integración de Notion conectada a esa base de datos
3. Suscripción de webhook a los eventos `page.created` y `page.properties_updated`
4. Instancia de Amazon Connect con telefonía saliente habilitada
5. Número de teléfono reservado
6. Contact flow con bloques Set voice, Get customer input (Lex) y Disconnect
7. Bot de Lex V2 en `es-ES` con las tres intenciones y una ranura `NuevaHora` de tipo `AMAZON.Time`
8. Asociación de la Lambda `adhd-agent-voz` a la instancia de Connect

## Parámetros

Los tiempos de la escalada están en `lambdas/programador/handler.py`.

```python
MIN_ANTES_PUSH = 5
REINTENTO_IMPORTANTE = 15
REINTENTO_URGENTE_1 = 5
REINTENTO_URGENTE_2 = 15
```

## Notas de implementación

**Notion API.** Las consultas usan `/v1/data_sources/{id}/query` con la cabecera `Notion-Version: 2026-03-11`. El identificador del data source difiere del que aparece en la URL de la base de datos.

**Idempotencia.** El programador reclama cada tarea con una escritura condicional en DynamoDB. Los eventos duplicados de Notion no generan ejecuciones adicionales. Las llamadas usan además el `ClientToken` de Connect.

**Esperas.** Step Functions usa `TimestampPath` con marcas absolutas en UTC. Una marca en el pasado se atraviesa de inmediato, lo que permite procesar tareas descubiertas con retraso.

**Bedrock.** El identificador del modelo lleva prefijo `eu.` por inferencia entre regiones. La función tiene una respuesta de reserva si la invocación falla.

**Dependencias.** Las Lambdas usan `urllib` de la biblioteca estándar en lugar de `requests`, evitando layers y empaquetado con Docker.

## Coste

Dentro del nivel gratuito de AWS salvo Secrets Manager, alrededor de 0,40 USD al mes, y el número de teléfono, gratuito los primeros doce meses.

## Licencia

MIT
