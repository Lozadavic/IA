import logging
import os
from typing import Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from app.rag import RetrievedChunk, retriever
from app.utils import InMemoryConversationStore, sanitize_text

logger = logging.getLogger(__name__)

load_dotenv()

SYSTEM_PROMPT = """
Eres un asistente de atención al cliente por WhatsApp.
Tono: amable, claro, profesional y conciso.
Si falta información, haz una pregunta corta de aclaración.
Nunca inventes horarios, precios, stock o políticas.
Si no hay datos disponibles, indícalo con claridad y ofrece una alternativa.
Siempre sugiere un siguiente paso (visita, reserva, hablar con un agente humano, etc.).
Idioma por defecto: español.
""".strip()

INTENT_KEYWORDS: Dict[str, List[str]] = {
    "hours": ["horario", "horarios", "abren", "cierran", "hora"],
    "location": ["ubicación", "direccion", "dirección", "donde", "ubicados"],
    "availability": ["disponible", "stock", "existencia", "hay", "availability"],
    "price": ["precio", "cuesta", "vale", "coste", "costo"],
    "shipping": ["envío", "envios", "shipping", "entrega"],
    "payments": ["pago", "pagos", "tarjeta", "transferencia"],
    "returns": ["devolución", "cambio", "garantía"],
    "human": ["humano", "agente", "asesor", "persona", "soporte"],
    "reservation": ["reserva", "reservar", "cita"],
}

conversation_store = InMemoryConversationStore()


class SupportAgent:
    def __init__(self) -> None:
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client: Optional[OpenAI] = None
        self.handoff_requests: set[str] = set()
        if self.openai_key:
            self.client = OpenAI(api_key=self.openai_key)

    def detect_intent(self, message: str) -> str:
        lower = message.lower()
        for intent, keywords in INTENT_KEYWORDS.items():
            if any(keyword in lower for keyword in keywords):
                return intent
        return "general"

    def build_context(self, retrieved: List[RetrievedChunk]) -> str:
        if not retrieved:
            return "No hay datos relevantes en la base de conocimiento."
        items = [f"- {chunk.text}" for chunk in retrieved]
        return "\n".join(items)

    def generate_response(self, user_id: str, message: str) -> str:
        sanitized = sanitize_text(message)
        intent = self.detect_intent(sanitized)
        conversation_store.append(user_id, f"Usuario: {sanitized}")

        retrieved = retriever.retrieve(sanitized, top_k=4)
        context = self.build_context(retrieved)
        history = "\n".join(conversation_store.get(user_id))

        if intent == "availability":
            response = (
                "Para confirmar disponibilidad necesito un par de detalles: "
                "¿qué producto o servicio específico buscas y en qué ubicación o modalidad (retiro/envío)?"
            )
            conversation_store.append(user_id, f"Asistente: {response}")
            return response

        if intent == "human":
            self.handoff_requests.add(user_id)
            response = (
                "Puedo ayudarte a contactar a un agente humano. "
                "Por favor comparte tu nombre y el motivo de tu consulta, y te atenderemos pronto."
            )
            conversation_store.append(user_id, f"Asistente: {response}")
            return response

        if not self.client:
            response = self.compose_template_response(intent, context)
            conversation_store.append(user_id, f"Asistente: {response}")
            return response

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Historial:\n{history}\n\n"
                            f"Contexto relevante:\n{context}\n\n"
                            f"Consulta del usuario: {sanitized}"
                        ),
                    },
                ],
                temperature=0.2,
            )
            response = completion.choices[0].message.content.strip()
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM error: %s", exc)
            response = self.compose_template_response(intent, context)

        conversation_store.append(user_id, f"Asistente: {response}")
        return response

    def compose_template_response(self, intent: str, context: str) -> str:
        base = "Hola, gracias por tu mensaje. "
        if intent == "hours":
            return (
                f"{base}Esto es lo que tengo sobre horarios:\n{context}\n"
                "¿Quieres que confirme un horario específico o prefieres hablar con un agente?"
            )
        if intent == "location":
            return (
                f"{base}Información de ubicación disponible:\n{context}\n"
                "¿Deseas indicaciones o quieres agendar una visita?"
            )
        if intent == "price":
            return (
                f"{base}Sobre precios encontré lo siguiente:\n{context}\n"
                "¿Qué producto o servicio te interesa para darte un valor exacto?"
            )
        if intent == "shipping":
            return (
                f"{base}Política de envíos:\n{context}\n"
                "¿A qué ciudad o código postal sería el envío?"
            )
        if intent == "returns":
            return (
                f"{base}Política de devoluciones:\n{context}\n"
                "¿Quieres que revise tu caso con un agente?"
            )
        if intent == "payments":
            return (
                f"{base}Métodos de pago disponibles:\n{context}\n"
                "¿Deseas asistencia con un pago específico?"
            )
        if intent == "reservation":
            return (
                f"{base}Sobre reservas:\n{context}\n"
                "¿Qué fecha y horario te funcionan?"
            )
        return (
            f"{base}Esto es lo más relevante que encontré:\n{context}\n"
            "¿En qué más puedo ayudarte o quieres hablar con un agente humano?"
        )


support_agent = SupportAgent()
