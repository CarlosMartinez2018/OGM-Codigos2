import asyncio
import argparse
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select, func

from app.db.database import async_session, init_db, engine
from app.db.models import ProductionEmail
from app.services.read_emls import parse_eml_file

async def load_emls_to_prod(folder_path: str):
    await init_db()
    path = Path(folder_path)
    emails = []
    for f in path.glob("*.eml"):
        try:
            emails.append(parse_eml_file(f))
        except Exception as e:
            print(f"Error parsing {f.name}: {e}")

    if not emails:
        print("No emails found.")
        return

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
            stmt = stmt.on_conflict_do_nothing(index_elements=["message_id"])
            await session.execute(stmt)

        await session.commit()
        total = await session.scalar(select(func.count()).select_from(ProductionEmail))
        print(f"Inserted {len(emails)} emails into production_emails. Total: {total}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(load_emls_to_prod("sample_emails"))
