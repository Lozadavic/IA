# WhatsApp Customer Support Assistant (RAG)

Asistente de atención al cliente por WhatsApp usando la API oficial de WhatsApp Business Cloud, FastAPI y un flujo RAG (Retrieval-Augmented Generation). Incluye modo sin LLM cuando no hay clave de embeddings o de OpenAI.

## Requisitos
- Python 3.10+
- Cuenta de WhatsApp Business Cloud API
- Token y Phone Number ID de Meta

## Estructura
```
app/
  main.py        # FastAPI entrypoint
  whatsapp.py    # Webhook de WhatsApp + envío de mensajes
  rag.py         # Indexado y recuperación de conocimiento
  agent.py       # Lógica de decisión y generación de respuestas
  utils.py       # Utilidades (rate limit, logging, sanitización)
knowledge/
  faq.md         # Base de conocimiento de ejemplo
.env.example
requirements.txt
README.md
```

## Configuración
1. Copia el archivo `.env.example` a `.env` y completa los valores:
   ```bash
   cp .env.example .env
   ```
2. Crea y activa el entorno virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Instala dependencias:
   ```bash
   pip install -r requirements.txt
   ```
4. Ejecuta la app:
   ```bash
   uvicorn app.main:app --reload
   ```

## Exponer con ngrok
```bash
ngrok http 8000
```
Copia la URL HTTPS que te entrega ngrok. Usarás esa URL en la configuración del webhook.

## Configurar el webhook en Meta
1. En Meta for Developers, ve a **WhatsApp > Configuration**.
2. En **Webhook**, agrega la URL de ngrok y el endpoint:
   ```
   https://<tu-subdominio>.ngrok.io/webhook
   ```
3. Define el **Verify Token** con el mismo valor de `VERIFY_TOKEN`.
4. Suscribe los eventos de mensajes.

## Probar con WhatsApp
1. Envía un mensaje al número de WhatsApp configurado.
2. Ejemplo de preguntas:
   - "¿Cuál es su horario de atención?"
   - "¿Dónde están ubicados?"
   - "¿Hacen envíos a domicilio?"
   - "Quiero hablar con un asesor"

## Ejemplos de respuestas esperadas
- Horarios:
  > Hola, gracias por tu mensaje. Esto es lo que tengo sobre horarios: ... ¿Quieres que confirme un horario específico o prefieres hablar con un agente?
- Disponibilidad:
  > Para confirmar disponibilidad necesito un par de detalles: ¿qué producto o servicio específico buscas y en qué ubicación o modalidad (retiro/envío)?
- Humano:
  > Puedo ayudarte a contactar a un agente humano. Por favor comparte tu nombre y el motivo de tu consulta, y te atenderemos pronto.

## Notas de RAG
- Los documentos se cargan desde la carpeta `/knowledge`.
- Si existe `OPENAI_API_KEY`, se crea un índice vectorial con Chroma.
- Si no hay clave, se usa búsqueda por palabras clave.
- Si no hay LLM disponible, se genera respuesta con plantillas y texto recuperado.

## Payload de ejemplo (para pruebas locales)
```json
{
  "entry": [
    {
      "changes": [
        {
          "value": {
            "messages": [
              {
                "from": "5215550000000",
                "type": "text",
                "text": {"body": "¿Cuáles son sus horarios?"}
              }
            ]
          }
        }
      ]
    }
  ]
}
```

## Despliegue
- Asegúrate de configurar variables de entorno en tu proveedor (Render, Fly.io, AWS, etc.).
- Usa HTTPS en producción para recibir webhooks.

## Seguridad y buenas prácticas
- El bot no inventa información: responde solo con la base de conocimiento.
- Limita el número de solicitudes por usuario.
- Los logs son estructurados y no incluyen datos sensibles.
