"""
keyword_validator — Pure rules engine + DataForSEO metric enrichment. No LLM.

Validation logic (confidence-aware):
  navigational intent → archived (universal, all data sources)

  data_source in ('dataforseo', 'keywords_everywhere') — strict rules:
    archive if volume < 100, kd > 8

  data_source = 'estimated' — relaxed rules (±30% tolerance):
    archive if volume < 50, kd > 9

  data_source = 'pending' — no reliable metrics:
    status = 'pending_metrics' (waits for true-up, never archived on volume/kd)

DataForSEO enrichment runs first; on failure the existing DB data_source
is preserved per keyword (estimated stays estimated, pending stays pending).
"""
import logging
import re
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import KeywordValidationOutput
from integrations.base import IntegrationError
from integrations.dataforseo import DataForSEOIntegration

logger = logging.getLogger(__name__)


@register
class KeywordValidatorAgent(BaseAgent):
    name = "keyword_validator"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        keyword_ids: list[str] = ctx.params.get("keyword_ids", [])
        if not keyword_ids:
            return AgentResult(
                status="success",
                data={"total": 0, "validated": 0, "archived": 0, "pending_metrics": 0},
                tokens_used=0,
                cost_usd=0.0,
            )

        # 1. Fetch all raw keywords — includes data_source for classify step
        rows = await _fetch_raw_keywords(keyword_ids, ctx.db)
        if not rows:
            return AgentResult(
                status="success",
                data={"total": 0, "validated": 0, "archived": 0, "pending_metrics": 0},
                tokens_used=0,
                cost_usd=0.0,
            )

        # 2. Enrich with DataForSEO
        metrics_map: dict[str, dict[str, Any]] = {}
        dfs_succeeded = False
        try:
            dfs = DataForSEOIntegration()
            kw_texts = [r["keyword"] for r in rows]
            metrics_map = await dfs.get_keyword_metrics(kw_texts, ctx.org_id, ctx.db)
            dfs_succeeded = True
        except IntegrationError as exc:
            logger.warning(
                "keyword_validator: DataForSEO unavailable, "
                "preserving existing per-row data_source: %s", exc
            )

        # 3. Merge metrics into in-memory rows; update data_source per keyword
        for row in rows:
            m = metrics_map.get(row["keyword"], {})
            if dfs_succeeded and m:
                if m.get("volume") is not None:
                    row["volume"] = m["volume"]
                if m.get("kd") is not None:
                    row["kd"] = m["kd"]
                if m.get("cpc") is not None:
                    row["cpc"] = m["cpc"]
                row["data_source"] = "dataforseo"

        # 4. Persist updated metrics (per-row data_source)
        await _update_keyword_metrics(rows, ctx.db)

        # 5. Confidence-aware classification
        to_archive: list[dict[str, Any]] = []
        to_validate: list[dict[str, Any]] = []
        to_pending: list[dict[str, Any]] = []

        for r in rows:
            outcome = _classify_keyword(r)
            if outcome == "archive":
                to_archive.append(r)
            elif outcome == "validate":
                to_validate.append(r)
            else:
                to_pending.append(r)

        if to_archive:
            await _bulk_update_status(
                [str(r["id"]) for r in to_archive],
                status="archived",
                reason="auto-archived: navigational intent or metrics below threshold",
                db=ctx.db,
            )

        if to_validate:
            ds_label = "dataforseo" if dfs_succeeded else "estimated/pending"
            await _bulk_update_status(
                [str(r["id"]) for r in to_validate],
                status="validated",
                reason=f"rules: threshold passed ({ds_label})",
                db=ctx.db,
            )

        if to_pending:
            await _bulk_update_status(
                [str(r["id"]) for r in to_pending],
                status="pending_metrics",
                reason="no reliable metrics — awaiting true-up from real API",
                db=ctx.db,
            )

        # 6. Count outcomes from DB
        counts = await _count_outcomes(keyword_ids, ctx.db)

        result_data_source = "dataforseo" if dfs_succeeded and metrics_map else "pending"

        return AgentResult(
            status="success",
            data={
                "total": len(rows),
                "validated": counts["validated"],
                "archived": counts["archived"],
                "pending_metrics": counts["pending_metrics"],
                "data_source": result_data_source,
            },
            tokens_used=0,
            cost_usd=0.0,
        )


# ── Business logic ────────────────────────────────────────────────────────────

def _classify_keyword(row: dict[str, Any]) -> str:
    """Return 'archive', 'pending_metrics', or 'validate' for this keyword row."""
    intent = str(row.get("intent") or "").lower().strip()
    ds = str(row.get("data_source") or "pending")
    volume = row.get("volume")
    kd = row.get("kd")

    # Universal: navigational → archive regardless of source
    if intent == "navigational":
        return "archive"

    # No reliable metrics → await true-up
    if ds not in ("dataforseo", "keywords_everywhere", "estimated"):
        return "pending_metrics"

    # Estimated (±30% tolerance): lenient thresholds
    if ds == "estimated":
        if volume is not None and volume < 50:
            return "archive"
        if kd is not None and kd > 9:
            return "archive"
        return "validate"

    # Tier 1/2 real data: strict thresholds
    if volume is not None and volume < 100:
        return "archive"
    if kd is not None and kd > 8:
        return "archive"
    return "validate"


def _should_hard_archive(row: dict[str, Any]) -> bool:
    """Legacy rules-only check. Kept for direct unit-test imports."""
    volume = row.get("volume")
    kd = row.get("kd")
    intent = str(row.get("intent") or "").lower().strip()

    if volume is not None and volume < 50:
        return True
    if kd is not None and kd > 9:
        return True
    if intent == "navigational":
        return True
    return False


# ── DB helpers ────────────────────────────────────────────────────────────────

def _in_clause(ids: list[str]) -> tuple[str, dict[str, str]]:
    placeholders = ", ".join(f":id_{i}" for i in range(len(ids)))
    params = {f"id_{i}": str(id_) for i, id_ in enumerate(ids)}
    return placeholders, params


async def _fetch_raw_keywords(
    keyword_ids: list[str], db: AsyncSession
) -> list[dict[str, Any]]:
    if not keyword_ids:
        return []
    placeholders, params = _in_clause(keyword_ids)
    result = await db.execute(
        text(
            f"SELECT id, keyword, volume, kd, cpc, intent, status, data_source "
            f"FROM keywords "
            f"WHERE id IN ({placeholders}) AND status = 'raw'"
        ),
        params,
    )
    return [dict(row) for row in result.mappings().all()]


async def _update_keyword_metrics(
    rows: list[dict[str, Any]],
    db: AsyncSession,
) -> None:
    """Persist per-row metrics. data_source already merged into each row."""
    for row in rows:
        await db.execute(
            text(
                "UPDATE keywords SET "
                "volume = :volume, kd = :kd, cpc = :cpc, "
                "data_source = :data_source, updated_at = now() "
                "WHERE id = :id"
            ),
            {
                "id": str(row["id"]),
                "volume": row.get("volume"),
                "kd": row.get("kd"),
                "cpc": row.get("cpc"),
                "data_source": row.get("data_source", "pending"),
            },
        )
    await db.flush()


async def _bulk_update_status(
    keyword_ids: list[str],
    status: str,
    reason: str,
    db: AsyncSession,
) -> None:
    if not keyword_ids:
        return
    placeholders, params = _in_clause(keyword_ids)
    await db.execute(
        text(
            f"UPDATE keywords SET status = :status, reason = :reason, "
            f"updated_at = now() "
            f"WHERE id IN ({placeholders})"
        ),
        {"status": status, "reason": reason, **params},
    )
    await db.flush()


async def _apply_validation_results(
    results: list[dict[str, Any]], db: AsyncSession
) -> None:
    """Kept for backwards-compat with tests that import it; not called by execute()."""
    for raw in results:
        try:
            output = KeywordValidationOutput(**raw)
        except ValidationError as exc:
            logger.warning("keyword_validator: invalid result skipped: %s", exc)
            continue
        await db.execute(
            text(
                "UPDATE keywords SET "
                "status = :status, reason = :reason, updated_at = now() "
                "WHERE id = :id"
            ),
            {
                "id": output.keyword_id,
                "status": output.updated_status,
                "reason": output.reason,
            },
        )
    await db.flush()


async def _count_outcomes(keyword_ids: list[str], db: AsyncSession) -> dict[str, int]:
    placeholders, params = _in_clause(keyword_ids)
    result = await db.execute(
        text(
            f"SELECT status, COUNT(*) as cnt FROM keywords "
            f"WHERE id IN ({placeholders}) "
            f"GROUP BY status"
        ),
        params,
    )
    counts: dict[str, int] = {"validated": 0, "archived": 0, "pending_metrics": 0}
    for row in result.fetchall():
        status = str(row[0])
        if status in counts:
            counts[status] = int(row[1])
    return counts


# ── Legacy LLM parsing helpers — kept so test imports don't break ─────────────

_REFUSAL_PHRASES = [
    "i cannot", "i can't", "as an ai", "i don't have access",
    "i am unable", "i'm unable", "not able to provide",
]

_CODE_INDICATORS = [
    "function ", "const ", "var ", "let ", "=>",
    "console.log", "return {", "def ",
]


def _parse_validation_json(
    response: str, batch: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Legacy LLM response parser — no longer called by execute()."""
    if not response or not response.strip():
        logger.warning("keyword_validator: empty LLM response")
        return []

    if any(p in response.lower() for p in _REFUSAL_PHRASES):
        logger.warning("keyword_validator: model refused to answer")
        return []

    head = response[:200]
    if any(indicator in head for indicator in _CODE_INDICATORS):
        logger.warning(
            "keyword_validator: model returned code instead of JSON — skipping. Head: %s",
            head,
        )
        return []

    text_to_id = {r["keyword"].lower(): str(r["id"]) for r in batch}
    text_to_kw = {r["keyword"].lower(): r["keyword"] for r in batch}

    cleaned = re.sub(r"```(?:json)?", "", response, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)

    data: Any = None

    if cleaned.startswith("["):
        try:
            import json
            data = json.loads(cleaned)
        except Exception:
            pass

    if data is None:
        import re as _re
        array_match = _re.search(r"\[.*?\]", cleaned, _re.DOTALL)
        if array_match:
            try:
                import json
                data = json.loads(array_match.group())
            except Exception:
                pass

    if data is None:
        logger.warning(
            "keyword_validator: could not parse JSON. Raw response start: %s",
            response[:300],
        )
        return []

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    results: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue

        keyword_id = (
            item.get("keyword_id") or item.get("id") or item.get("uuid")
        )
        if not keyword_id:
            kw_lower = str(item.get("keyword") or "").lower().strip()
            keyword_id = text_to_id.get(kw_lower)
            if not keyword_id:
                logger.warning(
                    "keyword_validator: could not match item to batch keyword: %s",
                    item,
                )
                continue

        keyword_text = str(item.get("keyword") or "").strip()
        if not keyword_text:
            id_lower = str(keyword_id).lower()
            keyword_text = text_to_kw.get(id_lower, "")
        if not keyword_text:
            continue

        if "worth_targeting" in item:
            worth_targeting = item["worth_targeting"]
        elif "recommended" in item:
            worth_targeting = item["recommended"]
        elif "include" in item:
            worth_targeting = item["include"]
        elif "keep" in item:
            worth_targeting = item["keep"]
        else:
            worth_targeting = False

        reason = str(
            item.get("reason")
            or item.get("rationale")
            or item.get("explanation")
            or item.get("why")
            or ""
        ).strip()

        results.append(
            {
                "keyword_id": str(keyword_id),
                "keyword": keyword_text,
                "worth_targeting": worth_targeting,
                "reason": reason,
            }
        )

    return results


def _batches(items: list[Any], n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]
