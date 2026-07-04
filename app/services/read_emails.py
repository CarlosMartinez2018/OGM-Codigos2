"""
read_emails.py -- Lectura de correos de Outlook y almacenamiento en PostgreSQL.

Uso rapido:
  python read_emails.py
  python read_emails.py --date 2026-06-23
  python read_emails.py --all-dates
  python read_emails.py --month 6 --year 2026
  python read_emails.py --all-dates --auto-export
"""

import asyncio
import argparse
import calendar
import logging
import sys
from datetime import datetime, timezone, date, time, timedelta
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, func

from app.core.config import settings
from app.services.connector import outlook
from app.schemas import EmailData
from app.db.database import async_session, init_db, engine
from app.db.models import ProductionEmail

# En consolas Windows heredadas (cp1252) los asuntos con emoji rompen la
# impresion de rich. Forzar UTF-8 en stdout/stderr si es posible.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

console = Console()
logger = logging.getLogger(__name__)
LOCAL_TZ = timezone(timedelta(hours=-5), "America/Bogota")


# ---------------------------------------------------------------------------
# Helpers de rango de fechas
# ---------------------------------------------------------------------------

def _month_range(month: int, year: int) -> tuple[datetime, datetime]:
    """Devuelve (inicio, fin) en UTC para el mes/ano indicados."""
    last_day = calendar.monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    end   = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return start, end


def _day_range(day: date) -> tuple[datetime, datetime]:
    """Devuelve (inicio, fin) UTC para un dia local de Colombia."""
    start_local = datetime.combine(day, time.min, tzinfo=LOCAL_TZ)
    end_local = datetime.combine(day, time.max.replace(microsecond=0), tzinfo=LOCAL_TZ)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Lectura desde Outlook (Microsoft Graph API)
# ---------------------------------------------------------------------------

async def read_outlook_emails(
    filter_today: bool = True,
    single_day: Optional[date] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    folder: str = "Inbox",
    count: Optional[int] = 500,
) -> list[EmailData]:
    """Lee y parsea correos desde un buzon de Outlook via Microsoft Graph API."""
    if not outlook.is_configured:
        raise ValueError(
            "Outlook no configurado. Agrega AZURE_TENANT_ID, AZURE_CLIENT_ID, "
            "AZURE_CLIENT_SECRET y OUTLOOK_MAILBOX en tu .env."
        )

    since: Optional[datetime] = None
    until: Optional[datetime] = None

    if single_day:
        since, until = _day_range(single_day)
        label = f"dia {single_day.isoformat()}"
    elif month and year:
        since, until = _month_range(month, year)
        label = f"{calendar.month_name[month]} {year}"
    elif filter_today:
        today_local = datetime.now(LOCAL_TZ).date()
        since, until = _day_range(today_local)
        label = f"hoy ({today_local})"
    else:
        label = "todas las fechas"

    logger.info(f"Consultando Outlook -- periodo: {label}")

    emails = await outlook.fetch_recent_emails(
        folder=folder,
        count=count,
        since_datetime=since,
        until_datetime=until,
    )

    logger.info(f"Correos recibidos de Outlook: {len(emails)}")
    return emails


# ---------------------------------------------------------------------------
# Guardar en PostgreSQL (UPSERT por message_id)
# ---------------------------------------------------------------------------

async def save_to_db(emails: list[EmailData]) -> tuple[int, int]:
    """
    Guarda correos en la tabla production_emails con UPSERT.
    Retorna (insertados, actualizados).
    """
    if not emails:
        return 0, 0

    inserted = 0
    updated = 0

    async with async_session() as session:
        for em in emails:
            stmt = pg_insert(ProductionEmail).values(
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
            result = await session.execute(stmt)
            # xmax = 0 means INSERT, xmax > 0 means UPDATE in PostgreSQL
            # But with SQLAlchemy we just count by checking if rowcount > 0
            if result.rowcount:
                inserted += 1  # We count all as processed

        await session.commit()

        total = await session.scalar(
            select(func.count()).select_from(ProductionEmail)
        )

    return len(emails), total


def export_emails_to_xlsx(emails: list[EmailData], output_dir: str = "exports") -> Path:
    """Exporta los correos leidos a un archivo Excel."""
    from openpyxl import Workbook

    export_dir = Path(output_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = f"outlook_emails_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    output_path = export_dir / filename

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Outlook Emails"
    sheet.append([
        "message_id",
        "conversation_id",
        "sender",
        "sender_domain",
        "to_recipients",
        "cc_recipients",
        "subject",
        "received_date",
        "body_preview",
        "has_attachments",
        "attachment_names",
    ])

    for em in emails:
        sheet.append([
            em.message_id,
            em.conversation_id,
            em.sender,
            em.sender_domain,
            "; ".join(em.to_recipients),
            "; ".join(em.cc_recipients),
            em.subject,
            em.received_date.isoformat() if em.received_date else "",
            em.body_preview or "",
            "Si" if em.has_attachments else "No",
            "; ".join(em.attachment_names),
        ])

    workbook.save(output_path)
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _main(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    selected_day: Optional[date] = None
    if args.date:
        try:
            selected_day = date.fromisoformat(args.date)
        except ValueError:
            console.print("[red]--date debe tener formato YYYY-MM-DD[/red]"); sys.exit(1)

    if args.month and not args.year:
        console.print("[red]--month requiere tambien --year[/red]"); sys.exit(1)
    if args.year and not args.month:
        console.print("[red]--year requiere tambien --month[/red]"); sys.exit(1)
    if args.month and not (1 <= args.month <= 12):
        console.print("[red]--month debe ser un numero entre 1 y 12[/red]"); sys.exit(1)
    if args.limit < 0:
        console.print("[red]--limit debe ser 0 o mayor[/red]"); sys.exit(1)

    month_mode = args.month is not None or args.year is not None
    selected_modes = sum([bool(args.all_dates), bool(selected_day), month_mode])
    if selected_modes > 1:
        console.print("[red]Usa solo una opcion de periodo: --all-dates, --date o --month/--year[/red]")
        sys.exit(1)

    # Asegurar tablas existen
    await init_db()

    console.print("\n[bold blue]read_emails.py - Lectura de correos (Outlook)[/bold blue]")

    emails: list[EmailData] = []
    filter_today = not args.all_dates and not args.month and not selected_day
    count = None if args.limit == 0 else args.limit

    try:
        emails = await read_outlook_emails(
            filter_today=filter_today,
            single_day=selected_day,
            month=args.month,
            year=args.year,
            count=count,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]"); sys.exit(1)

    _print_emails(emails)

    if emails:
        processed, total_db = await save_to_db(emails)
        console.print(
            f"\n[bold green]PostgreSQL:[/bold green] {processed} correos procesados. "
            f"Total en production_emails: {total_db}"
        )
        if args.auto_export:
            output_path = export_emails_to_xlsx(emails)
            console.print(f"[bold green]Excel:[/bold green] Exportado en {output_path}")
    else:
        console.print("[yellow]No hay correos para guardar.[/yellow]")

    await engine.dispose()


def _print_emails(emails: list[EmailData]) -> None:
    """Imprime un resumen de los correos leidos en consola."""
    if not emails:
        console.print("[yellow]No se encontraron correos.[/yellow]")
        return

    table = Table(
        title=f"Correos leidos ({len(emails)} total)",
        show_header=True,
        header_style="bold white on dark_blue",
        border_style="blue",
    )
    table.add_column("#",           width=4,  justify="right")
    table.add_column("Asunto",      max_width=45)
    table.add_column("Email Rem.",  max_width=32)
    table.add_column("Dominio",     max_width=22)
    table.add_column("Recibido",    width=12, justify="center")
    table.add_column("Adjuntos",    width=9,  justify="center")

    for i, em in enumerate(emails, start=1):
        table.add_row(
            str(i),
            (em.subject or "(Sin asunto)")[:45],
            em.sender_email[:32],
            em.sender_domain[:22],
            em.received_date.strftime("%Y-%m-%d") if em.received_date else "-",
            "[green]Si[/green]" if em.has_attachments else "-",
        )

    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Lee correos desde Outlook y los guarda en PostgreSQL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--all-dates", action="store_true", default=False,
        help="Sin filtro de fecha (trae todos los correos disponibles).",
    )
    parser.add_argument(
        "--date", default=None, metavar="YYYY-MM-DD",
        help="Lee solo un dia especifico. Ej: --date 2026-06-23.",
    )
    parser.add_argument(
        "--month", type=int, default=None, metavar="1-12",
        help="Mes a leer (1-12). Requiere --year.",
    )
    parser.add_argument(
        "--year", type=int, default=None, metavar="YYYY",
        help="Ano a leer (ej. 2026). Requiere --month.",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Maximo de correos a leer. 0 = sin limite. Default: 0.",
    )
    parser.add_argument(
        "--auto-export", action="store_true", default=False,
        help="Exporta a Excel los correos leidos despues de guardarlos.",
    )

    asyncio.run(_main(parser.parse_args()))
