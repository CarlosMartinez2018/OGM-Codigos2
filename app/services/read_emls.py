"""
read_emls.py -- Lectura de correos desde archivos .eml locales y almacenamiento en PostgreSQL.

Uso:
    python read_emls.py
    python read_emls.py --folder ./otra_carpeta
"""

import asyncio
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import re
import html as _html
import sys

from rich.console import Console
from rich.table import Table
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, func

import mailparser
from app.schemas import EmailData
from app.db.database import async_session, init_db, engine
from app.db.models import TrainingEmail

console = Console()
logger = logging.getLogger(__name__)


def clean_html(html_str: str) -> str:
    """Extrae texto plano de un bloque HTML (fallback si no hay texto plano)."""
    if not html_str:
        return ""
    s = re.sub(r"<style[^>]*>.*?</style>", "", html_str, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<script[^>]*>.*?</script>", "", s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_date(raw_date) -> Optional[datetime]:
    if raw_date is None:
        return None
    if isinstance(raw_date, datetime):
        return raw_date.astimezone(timezone.utc) if raw_date.tzinfo else raw_date.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(raw_date))
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def parse_eml_file(file_path: Path) -> EmailData:
    mail = mailparser.parse_from_file(str(file_path))

    sender = mail.from_[0][1] if mail.from_ else ""
    sender_name = mail.from_[0][0] if mail.from_ else ""
    sender_full = f"{sender_name} <{sender}>" if sender_name else sender

    to_emails = [r[1] for r in mail.to_ if r[1]] if mail.to_ else []
    cc_emails = [r[1] for r in mail.cc_ if r[1]] if mail.cc_ else []

    body_text = mail.text_plain[0] if mail.text_plain else ""
    body_html = mail.text_html[0] if mail.text_html else ""

    if not body_text and body_html:
        body_text = clean_html(body_html)

    attachment_names = [
        att.get("filename", "(sin nombre)")
        for att in mail.attachments
        if att.get("filename") and not att.get("filename", "").lower().startswith("image")
    ]

    return EmailData(
        message_id=mail.message_id or "",
        subject=mail.subject or "(sin asunto)",
        sender=sender_full,
        to_recipients=to_emails,
        cc_recipients=cc_emails,
        received_date=_parse_date(mail.date),
        body_text=body_text.strip(),
        body_html=body_html,
        has_attachments=len(attachment_names) > 0,
        attachment_names=attachment_names,
    )


# ---------------------------------------------------------------------------
# Guardar en PostgreSQL (UPSERT por message_id)
# ---------------------------------------------------------------------------

async def save_to_db(emails: list[EmailData]) -> tuple[int, int]:
    """
    Guarda correos en la tabla training_emails con UPSERT.
    Retorna (procesados, total_en_tabla).
    """
    if not emails:
        return 0, 0

    async with async_session() as session:
        for em in emails:
            stmt = pg_insert(TrainingEmail).values(
                message_id=em.message_id,
                conversation_id=em.conversation_id,
                sender=em.sender,
                sender_domain=em.sender_domain,
                to_recipients=em.to_recipients,
                cc_recipients=em.cc_recipients,
                subject=em.subject,
                received_date=em.received_date,
                body_text=em.body_text,
                body_preview=em.body_preview,
                has_attachments=em.has_attachments,
                attachment_names=em.attachment_names,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["message_id"],
                set_={
                    "conversation_id": stmt.excluded.conversation_id,
                    "sender": stmt.excluded.sender,
                    "sender_domain": stmt.excluded.sender_domain,
                    "to_recipients": stmt.excluded.to_recipients,
                    "cc_recipients": stmt.excluded.cc_recipients,
                    "subject": stmt.excluded.subject,
                    "received_date": stmt.excluded.received_date,
                    "body_text": stmt.excluded.body_text,
                    "body_preview": stmt.excluded.body_preview,
                    "has_attachments": stmt.excluded.has_attachments,
                    "attachment_names": stmt.excluded.attachment_names,
                },
            )
            await session.execute(stmt)

        await session.commit()

        total = await session.scalar(
            select(func.count()).select_from(TrainingEmail)
        )

    return len(emails), total


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_emails(emails: list[EmailData]) -> None:
    if not emails:
        console.print("[yellow]No se encontraron correos en la carpeta.[/yellow]")
        return

    table = Table(
        title=f"Archivos EML procesados ({len(emails)} total)",
        show_header=True, header_style="bold white on dark_green", border_style="green",
    )
    table.add_column("#", width=4, justify="right")
    table.add_column("Asunto", max_width=45)
    table.add_column("Email Rem.", max_width=32)
    table.add_column("Recibido", width=12, justify="center")

    for i, em in enumerate(emails, start=1):
        table.add_row(
            str(i),
            (em.subject or "(Sin asunto)")[:45],
            em.sender_email[:32],
            em.received_date.strftime("%Y-%m-%d") if em.received_date else "-",
        )
    console.print(table)


async def _main(args):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    folder_path = Path(args.folder)

    if not folder_path.exists() or not folder_path.is_dir():
        console.print(f"[red]La carpeta '{folder_path}' no existe.[/red]")
        sys.exit(1)

    # Asegurar tablas existen
    await init_db()

    console.print(f"\n[bold green]read_emls.py - Escaneando archivos locales en {folder_path}[/bold green]")

    eml_files = list(folder_path.glob("*.eml"))
    if not eml_files:
        console.print(f"[yellow]No se encontraron archivos .eml en {folder_path}[/yellow]")
        sys.exit(0)

    emails = []
    for f in eml_files:
        try:
            emails.append(parse_eml_file(f))
        except Exception as e:
            logger.error(f"Error parseando {f.name}: {e}")

    _print_emails(emails)

    if emails:
        processed, total_db = await save_to_db(emails)
        console.print(
            f"\n[bold green]PostgreSQL:[/bold green] {processed} correos procesados. "
            f"Total en training_emails: {total_db}"
        )

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Lee correos desde archivos .eml locales y los guarda en PostgreSQL."
    )
    parser.add_argument(
        "--folder", default="./sample_emails",
        help="Carpeta con archivos .eml. Default: ./sample_emails",
    )

    asyncio.run(_main(parser.parse_args()))
