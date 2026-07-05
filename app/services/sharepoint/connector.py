"""
Conector Microsoft Graph para bibliotecas de documentos de SharePoint.

Reusa el patron de app/services/connector.py (Outlook):
- Autentica via MSAL (client_credentials, app-only) con los mismos
  AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET del .env.
- Resuelve un sitio, lista sus drives y recorre un drive recursivamente
  entregando cada item con su ruta completa.

Permiso Graph (Application) requerido: Sites.Read.All (admin consent).
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import AsyncIterator, Optional

import httpx
import msal

from app.core.config import settings

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"


@dataclass
class SPItem:
    id: str
    drive_id: str
    drive_name: str
    name: str
    path: str
    parent_path: Optional[str]
    is_folder: bool
    size: Optional[int]
    mime_type: Optional[str]
    file_extension: Optional[str]
    web_url: Optional[str]
    sp_created_at: Optional[datetime]
    sp_modified_at: Optional[datetime]


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _ext_of(name: str) -> Optional[str]:
    if "." not in name:
        return None
    ext = name.rsplit(".", 1)[1].lower()
    return ext if 1 <= len(ext) <= 10 else None


class SharePointConnector:
    def __init__(self) -> None:
        self.tenant_id = settings.azure_tenant_id
        self.client_id = settings.azure_client_id
        self.client_secret = settings.azure_client_secret
        self.hostname = settings.sharepoint_hostname
        self.site_path = settings.sharepoint_site_path
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    @property
    def is_configured(self) -> bool:
        return all([self.tenant_id, self.client_id, self.client_secret,
                    self.hostname, self.site_path])

    async def _get_token(self) -> str:
        if (self._access_token and self._token_expiry
                and datetime.now(timezone.utc) < self._token_expiry):
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
            err = result.get("error_description", result.get("error", "Unknown"))
            raise ConnectionError(f"Failed to acquire token: {err}")

        self._access_token = result["access_token"]
        self._token_expiry = datetime.now(timezone.utc) + timedelta(minutes=55)
        return self._access_token

    async def _headers(self) -> dict:
        token = await self._get_token()
        return {"Authorization": f"Bearer {token}"}

    async def _get_json(self, client: httpx.AsyncClient, url: str) -> dict:
        r = await client.get(url, headers=await self._headers(), timeout=30.0)
        if r.status_code != 200:
            raise ConnectionError(
                f"Graph API {r.status_code} on {url}: {r.text[:200]}"
            )
        return r.json()

    async def download_item(self, drive_id: str, item_id: str) -> tuple[bytes, str]:
        """Descarga el contenido de un driveItem. Devuelve (bytes, content_type).

        Graph responde 302 a una URL de descarga; httpx sigue el redirect.
        """
        url = f"{GRAPH_API_BASE}/drives/{drive_id}/items/{item_id}/content"
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            r = await client.get(url, headers=await self._headers())
            if r.status_code != 200:
                raise ConnectionError(
                    f"Graph API {r.status_code} al descargar {item_id}: {r.text[:200]}"
                )
            ctype = r.headers.get("content-type", "application/octet-stream")
            return r.content, ctype

    async def resolve_site_id(self, client: httpx.AsyncClient) -> str:
        url = f"{GRAPH_API_BASE}/sites/{self.hostname}:{self.site_path}"
        data = await self._get_json(client, url)
        return data["id"]

    async def list_drives(self, client: httpx.AsyncClient) -> list[dict]:
        site_id = await self.resolve_site_id(client)
        url = f"{GRAPH_API_BASE}/sites/{site_id}/drives"
        data = await self._get_json(client, url)
        return data.get("value", [])

    async def walk_drive(
        self,
        client: httpx.AsyncClient,
        drive_id: str,
        drive_name: str,
    ) -> AsyncIterator[SPItem]:
        """Recorrido en anchura de un drive; entrega cada item (carpeta + archivo).

        Pagina via @odata.nextLink. Recursa en carpetas encolando sus ids.
        """
        queue: list[tuple[str, str]] = [("root", "")]  # (item_ref, parent_path)
        while queue:
            item_ref, parent_path = queue.pop(0)
            if item_ref == "root":
                url = (f"{GRAPH_API_BASE}/drives/{drive_id}/root/children"
                       f"?$top=200")
            else:
                url = (f"{GRAPH_API_BASE}/drives/{drive_id}/items/{item_ref}"
                       f"/children?$top=200")

            while url:
                data = await self._get_json(client, url)
                for raw in data.get("value", []):
                    name = raw.get("name", "")
                    is_folder = "folder" in raw
                    path = f"{parent_path}/{name}" if parent_path else f"/{name}"
                    file_info = raw.get("file") or {}
                    item = SPItem(
                        id=raw["id"],
                        drive_id=drive_id,
                        drive_name=drive_name,
                        name=name,
                        path=path,
                        parent_path=parent_path or "/",
                        is_folder=is_folder,
                        size=raw.get("size"),
                        mime_type=file_info.get("mimeType"),
                        file_extension=None if is_folder else _ext_of(name),
                        web_url=raw.get("webUrl"),
                        sp_created_at=_parse_dt(raw.get("createdDateTime")),
                        sp_modified_at=_parse_dt(raw.get("lastModifiedDateTime")),
                    )
                    yield item
                    if is_folder:
                        queue.append((raw["id"], path))
                url = data.get("@odata.nextLink")

    async def test_connection(self) -> dict:
        """Sonda rapida para /health."""
        if not self.is_configured:
            return {"status": "not_configured"}
        try:
            async with httpx.AsyncClient() as client:
                site_id = await self.resolve_site_id(client)
            return {"status": "connected", "site_id": site_id,
                    "site_path": f"{self.hostname}{self.site_path}"}
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "message": str(e)[:300]}


sharepoint = SharePointConnector()
