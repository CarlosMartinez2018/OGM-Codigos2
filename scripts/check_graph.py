"""
check_graph.py — Validador standalone de credenciales Microsoft Graph.

Verifica, sin tocar la BD, que las credenciales del .env pueden:
  1. Obtener token (client_credentials via MSAL).
  2. Leer el buzon configurado (Mail.Read).
  3. Leer el sitio SharePoint configurado (Sites.Read.All), si aplica.

Uso:
    python -m scripts.check_graph
    python -m scripts.check_graph --count 5   # ademas lista los N mas recientes

Exit codes: 0 = todo OK, 1 = alguna verificacion fallo.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

from app.core.config import settings
from app.services.connector import GRAPH_API_BASE, OutlookConnector

sys.stdout.reconfigure(encoding="utf-8")


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


async def main(count: int) -> int:
    failures = 0
    conn = OutlookConnector()

    print("1. Configuracion (.env)")
    if conn.is_configured:
        _ok(f"credenciales presentes — buzon: {conn.mailbox}")
    else:
        _fail("faltan AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / OUTLOOK_MAILBOX")
        return 1

    print("2. Token (client_credentials)")
    try:
        token = await conn._get_token()
        _ok("token obtenido")
    except Exception as exc:
        _fail(f"no se pudo obtener token: {exc}")
        return 1

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Nota: NO usamos /users/{mailbox} (perfil) — eso exige User.Read.All,
        # que la app no necesita. Se prueba directo el endpoint de correos,
        # que es lo que la ingesta usa realmente (Mail.Read).
        print("3. Buzon (Mail.Read)")
        r = await client.get(
            f"{GRAPH_API_BASE}/users/{conn.mailbox}/mailFolders/Inbox/messages"
            f"?$top={max(count, 1)}&$orderby=receivedDateTime desc"
            f"&$select=subject,from,receivedDateTime",
            headers=headers,
        )
        if r.status_code == 200:
            msgs = r.json().get("value", [])
            _ok(f"buzon legible — {len(msgs)} correo(s) recuperado(s)")
            if count > 0:
                for m in msgs:
                    frm = m.get("from", {}).get("emailAddress", {}).get("address", "?")
                    print(f"       - {m.get('receivedDateTime', '')[:16]}  {frm[:35]:35}  {m.get('subject', '')[:50]}")
        else:
            _fail(f"HTTP {r.status_code}: {r.text[:150]}")
            failures += 1

        print("4. SharePoint (Sites.Read.All)")
        if settings.sharepoint_hostname and settings.sharepoint_site_path:
            r = await client.get(
                f"{GRAPH_API_BASE}/sites/{settings.sharepoint_hostname}:{settings.sharepoint_site_path}",
                headers=headers,
            )
            if r.status_code == 200:
                _ok(f"sitio accesible: {r.json().get('displayName', '')}")
            else:
                _fail(f"HTTP {r.status_code}: {r.text[:150]}")
                failures += 1
        else:
            print("       (sin configurar — omitido)")

    print("\n" + ("TODO OK" if failures == 0 else f"{failures} verificacion(es) fallaron"))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=0,
                        help="listar los N correos mas recientes del Inbox")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.count)))
