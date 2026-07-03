"""
eval_classifier.py -- Mide la precision real del clasificador contra un gold set.

Corre el clasificador (reglas + LLM si esta activo) sobre los correos etiquetados
en data/gold_set.json y reporta: acierto de lender, de waiver, de ambos, y la
PRECISION por banda de confianza (¿el bucket "alta" es de verdad correcto?).

NO muta la BD (solo lee training_emails y clasifica en memoria).

Uso (desde la raiz):
    python -m scripts.eval_classifier
"""
import asyncio
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from app.core.config import settings
from app.db.database import async_session, engine
from app.db.models import TrainingEmail
from app.services.llm_classifier import classifier

console = Console()
GOLD = Path(__file__).resolve().parent.parent / "data" / "gold_set.json"


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


async def main() -> None:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    items = gold["items"]
    verified = [i for i in items if i.get("verified")]
    console.print(f"\n[bold]eval_classifier[/bold]  ·  LLM activo: "
                  f"[{'green' if settings.use_llm_classifier else 'yellow'}]{settings.use_llm_classifier}[/]  "
                  f"·  modelo: {settings.ollama_model}")
    if not verified:
        console.print("[yellow]AVISO: ningun item tiene verified=true. Corriendo sobre el BORRADOR "
                      "de etiquetas; revisa data/gold_set.json antes de tomar decisiones.[/yellow]")

    async with async_session() as session:
        kb = await classifier._load_business_data(session)
        rows = {}
        for it in items:
            r = await session.get(TrainingEmail, it["training_email_id"])
            if r is not None:
                rows[it["training_email_id"]] = r

        results = []
        for it in items:
            r = rows.get(it["training_email_id"])
            if r is None:
                continue
            ed = classifier._production_to_email_data(r)
            res = await classifier.classify(ed, session, kb=kb)
            l_ok = _norm(res.lender) == _norm(it["expected_lender"])
            w_ok = _norm(res.waiver_type) == _norm(it["expected_waiver_type"])
            results.append({
                "id": it["training_email_id"],
                "exp_l": it["expected_lender"], "exp_w": it["expected_waiver_type"],
                "got_l": res.lender, "got_w": res.waiver_type,
                "l_ok": l_ok, "w_ok": w_ok, "both": l_ok and w_ok,
                "conf": res.confidence_score, "level": res.confidence_level,
            })

    # --- Tabla por item ---
    t = Table(title="Predicciones vs gold", show_lines=False, header_style="bold")
    for col in ("id", "lender ok", "waiver ok", "conf", "nivel", "predicho (L / W)"):
        t.add_column(col)
    for r in results:
        t.add_row(
            str(r["id"]),
            "[green]si[/]" if r["l_ok"] else f"[red]NO[/] ({r['got_l'][:14]})",
            "[green]si[/]" if r["w_ok"] else f"[red]NO[/] ({r['got_w'][:16]})",
            f"{r['conf']:.2f}", r["level"],
            f"{r['got_l'][:18]} / {r['got_w'][:20]}",
        )
    console.print(t)

    # --- Agregados ---
    n = len(results) or 1
    l_acc = sum(r["l_ok"] for r in results)
    w_acc = sum(r["w_ok"] for r in results)
    both = sum(r["both"] for r in results)
    avg = sum(r["conf"] for r in results) / n
    console.print(f"\n[bold]Aciertos[/bold]  lender {l_acc}/{n}  ·  waiver {w_acc}/{n}  ·  "
                  f"ambos {both}/{n}  ·  confianza media {avg:.2f}")

    # --- Precision por banda (lo importante para bank-grade) ---
    console.print("\n[bold]Precision por banda de confianza[/bold] (¿el bucket es de fiar?):")
    bt = Table(show_header=True, header_style="bold")
    for col in ("banda", "n", "ambos correctos", "precision"):
        bt.add_column(col)
    for band in ("high", "medium", "low"):
        grp = [r for r in results if r["level"] == band]
        if not grp:
            continue
        ok = sum(r["both"] for r in grp)
        bt.add_row(band, str(len(grp)), str(ok), f"{ok/len(grp)*100:.0f}%")
    console.print(bt)
    console.print("\n[dim]Meta bank-grade: el umbral de auto debe caer donde la precision de la banda "
                  "sea ~100%. Todo lo demas -> revision humana.[/dim]")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
