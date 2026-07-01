"""
Microsoft Graph API connector for Outlook email integration.
Supports reading emails from Exchange Online / Microsoft 365 mailboxes.

Setup instructions:
1. Go to https://portal.azure.com > App registrations > New registration
2. Set redirect URI: http://localhost (for testing)
3. API Permissions > Add:
   - Microsoft Graph > Application permissions:
     - Mail.Read (to read emails)
     - Mail.ReadBasic (minimal read)
   - Grant admin consent
4. Certificates & secrets > New client secret
5. Copy Tenant ID, Client ID, Client Secret to .env
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import msal

from config import settings
from schemas import EmailData

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"


class OutlookConnector:
    """
    Cliente para Microsoft Graph API — lectura de buzón de Outlook.

    Autenticación: client_credentials (sin usuario interactivo).
    Requiere permisos: Mail.Read (Application) con consentimiento de administrador.
    """

    def __init__(self) -> None:
        self.tenant_id     = settings.azure_tenant_id
        self.client_id     = settings.azure_client_id
        self.client_secret = settings.azure_client_secret
        self.mailbox       = settings.outlook_mailbox
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    @property
    def is_configured(self) -> bool:
        """True si todas las credenciales están presentes en .env."""
        return all([self.tenant_id, self.client_id, self.client_secret, self.mailbox])

    async def _get_token(self) -> str:
        """
        Obtiene (o reutiliza) un access token via MSAL.
        El token se cachea y se renueva 5 minutos antes de expirar.
        """
        # Reutilizar token vigente
        if (
            self._access_token
            and self._token_expiry
            and datetime.now(timezone.utc) < self._token_expiry
        ):
            return self._access_token

        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret,
        )

        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )

        if "access_token" not in result:
            error = result.get("error_description", result.get("error", "Unknown error"))
            raise ConnectionError(f"Failed to acquire token: {error}")

        self._access_token = result["access_token"]
        # Los tokens de Azure AD duran ~1 hora; renovamos 5 min antes
        self._token_expiry = datetime.now(timezone.utc) + timedelta(minutes=55)
        logger.debug("Token de Azure AD renovado correctamente.")
        return self._access_token

    async def fetch_recent_emails(
        self,
        folder: str = "Inbox",
        count: Optional[int] = 500,
        since_datetime: Optional[datetime] = None,
        until_datetime: Optional[datetime] = None,
    ) -> list[EmailData]:
        """
        Obtiene correos del buzón de Outlook via Microsoft Graph API.

        Implementa paginación automática hasta alcanzar `count` mensajes.

        Args:
            folder:          Nombre de carpeta del buzón (p.ej. "Inbox").
            count:           Número máximo de mensajes a recuperar.
            since_datetime:  Solo correos recibidos desde esta fecha (UTC).
            until_datetime:  Solo correos recibidos hasta esta fecha (UTC).

        Returns:
            Lista de EmailData ordenados por fecha descendente.

        Raises:
            ValueError:       Si las credenciales no están configuradas.
            ConnectionError:  Si la API devuelve un error HTTP.
        """
        if not self.is_configured:
            raise ValueError(
                "Outlook not configured. Set AZURE_TENANT_ID, AZURE_CLIENT_ID, "
                "AZURE_CLIENT_SECRET, and OUTLOOK_MAILBOX in .env"
            )

        token = await self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "Prefer": 'outlook.body-content-type="text"',
        }

        # Campos a recuperar de Graph API
        select_fields = (
            "id,subject,from,toRecipients,ccRecipients,"
            "receivedDateTime,body,hasAttachments,internetMessageId,conversationId"
        )

        # Filtros OData de fecha
        filters: list[str] = []
        if since_datetime:
            filters.append(
                f"receivedDateTime ge {since_datetime.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )
        if until_datetime:
            filters.append(
                f"receivedDateTime le {until_datetime.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )

        # URL inicial con parámetros de query
        page_size = min(count, 999) if count else 999
        url = (
            f"{GRAPH_API_BASE}/users/{self.mailbox}/mailFolders/{folder}"
            f"/messages?$top={page_size}&$orderby=receivedDateTime desc"
            f"&$expand=attachments($select=name,isInline)&$select={select_fields}"
        )
        if filters:
            url += "&$filter=" + " and ".join(filters)

        emails: list[EmailData] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            while url and (count is None or len(emails) < count):
                response = await client.get(url, headers=headers)

                if response.status_code != 200:
                    logger.error(
                        f"Graph API error {response.status_code}: {response.text[:300]}"
                    )
                    raise ConnectionError(
                        f"Graph API error: {response.status_code} — {response.text[:200]}"
                    )

                data = response.json()

                for msg in data.get("value", []):
                    emails.append(_parse_graph_message(msg))
                    if count is not None and len(emails) >= count:
                        break

                # Seguir paginación si hay más resultados
                url = data.get("@odata.nextLink")

        logger.info(f"Outlook — recuperados {len(emails)} correos de '{self.mailbox}/{folder}'")
        return emails

    async def test_connection(self) -> dict:
        """Verifica la conexión a Graph API y devuelve información del buzón."""
        if not self.is_configured:
            return {
                "status":  "not_configured",
                "message": "Set Azure credentials in .env file",
            }
        try:
            token = await self._get_token()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{GRAPH_API_BASE}/users/{self.mailbox}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if response.status_code == 200:
                    user = response.json()
                    return {
                        "status":       "connected",
                        "mailbox":      self.mailbox,
                        "display_name": user.get("displayName", ""),
                    }
                return {
                    "status":  "error",
                    "code":    response.status_code,
                    "message": response.text[:200],
                }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Helper de parseo de mensajes de Graph API
# ---------------------------------------------------------------------------

def _domains(addrs: list[str]) -> list[str]:
    """Extrae dominios únicos de una lista de direcciones de correo."""
    seen: list[str] = []
    for a in addrs:
        if "@" in a:
            d = a.split("@")[1].lower()
            if d not in seen:
                seen.append(d)
    return seen


def _parse_graph_message(msg: dict) -> EmailData:
    """Convierte un mensaje JSON de Graph API en EmailData."""
    # Remitente
    from_field   = msg.get("from", {}).get("emailAddress", {})
    sender_email = from_field.get("address", "")
    sender_name  = from_field.get("name", "")
    sender       = f"{sender_name} <{sender_email}>" if sender_name else sender_email

    # Destinatarios To / Cc
    to_addrs = [
        r["emailAddress"]["address"]
        for r in msg.get("toRecipients", [])
        if r.get("emailAddress", {}).get("address")
    ]
    cc_addrs = [
        r["emailAddress"]["address"]
        for r in msg.get("ccRecipients", [])
        if r.get("emailAddress", {}).get("address")
    ]

    # Cuerpo
    body_content = msg.get("body", {}).get("content", "")
    body_type    = msg.get("body", {}).get("contentType", "text")
    body_text    = body_content if body_type == "text" else ""
    body_html    = body_content if body_type == "html" else ""
    if not body_text and body_html:
        body_text = body_html  # fallback

    # Fecha recibido
    received: Optional[datetime] = None
    raw_dt = msg.get("receivedDateTime", "")
    if raw_dt:
        try:
            received = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            received = datetime.now(timezone.utc)

    # Adjuntos
    attachment_names = [
        att.get("name") for att in msg.get("attachments", [])
        if att.get("name") and not att.get("isInline", False)
    ]

    return EmailData(
        message_id=msg.get("internetMessageId") or msg.get("id", ""),
        conversation_id=msg.get("conversationId", ""),
        subject=msg.get("subject") or "(sin asunto)",
        sender=sender,
        sender_domain=sender_email.split("@")[1].lower() if "@" in sender_email else "",
        to_recipients=to_addrs,
        to_domains=_domains(to_addrs),
        cc_recipients=cc_addrs,
        cc_domains=_domains(cc_addrs),
        received_date=received,
        body_text=body_text,
        body_html=body_html,
        has_attachments=msg.get("hasAttachments", False) or len(attachment_names) > 0,
        attachment_names=attachment_names,
    )


# Singleton
outlook = OutlookConnector()
