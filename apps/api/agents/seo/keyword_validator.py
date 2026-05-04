import json
import logging
import re
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.llm_router import LLMUnavailableError
from core.contracts import KeywordValidationOutput
from core.prompt_registry import PromptRegistry
from integrations.base import IntegrationError
from integrations.dataforseo import DataForSEOIntegration

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50


@register
class KeywordValidatorAgent(BaseAgent):
    name = "keyword_validator"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        keyword_ids: list[str] = ctx.params.get("keyword_ids", [])
        if not keyword_ids:
            return AgentResult(
                status="success",
                data={"total": 0, "validated": 0, "archived": 0, "data_source": "llm_estimate"},
            )

        # 1. Fetch all raw keywords in one query — no N+1
        rows = await _fetch_raw_keywords(keyword_ids, ctx.db)
        if not rows:
            return AgentResult(
                status="success",
                data={"total": 0, "validated": 0, "archived": 0, "data_source": "llm_estimate"},
            )

        # 2. Enrich with DataForSEO; fall back to existing DB values on any error
        data_source = "llm_estimate"
        metrics_map: dict[str, dict[str, Any]] = {}
        try:
            dfs = DataForSEOIntegration()
            kw_texts = [r["keyword"] for r in rows]
            metrics_map = await dfs.get_keyword_metrics(kw_texts, ctx.org_id, ctx.db)
            data_source = "dataforseo"
        except IntegrationError as exc:
            logger.warning(
                "keyword_validator: DataForSEO unavailable, falling back to existing DB values: %s", exc
            )

        # 3. Merge DataForSEO metrics into in-memory rows (used for hard rules)
        for row in rows:
            m = metrics_map.get(row["keyword"], {})
            if m:
                if m.get("volume") is not None:
                    row["volume"] = m["volume"]
                if m.get("kd") is not None:
                    row["kd"] = m["kd"]
                if m.get("cpc") is not None:
                    row["cpc"] = m["cpc"]

        # 4. Persist updated metrics to DB BEFORE calling the LLM
        await _update_keyword_metrics(rows, metrics_map, data_source, ctx.db)

        # 5. Hard rules applied in Python — do not leave to LLM
        hard_archived: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        for row in rows:
            if _should_hard_archive(row):
                hard_archived.append(row)
            else:
                candidates.append(row)

        if hard_archived:
            await _bulk_update_status(
                [str(r["id"]) for r in hard_archived],
                status="archived",
                reason="auto-archived: volume<50, kd>9, or navigational intent",
                db=ctx.db,
            )

        # 6. LLM validation in batches of BATCH_SIZE
        prompt_template = await PromptRegistry().get("keyword_validator", ctx.db)
        llm_results: list[dict[str, Any]] = []

        for batch in _batches(candidates, _BATCH_SIZE):
            batch_json = json.dumps(
                [
                    {
                        "keyword_id": str(r["id"]),
                        "keyword": r["keyword"],
                        "volume": r.get("volume"),
                        "kd": r.get("kd"),
                        "cpc": r.get("cpc"),
                        "intent": r.get("intent"),
                    }
                    for r in batch
                ],
                ensure_ascii=False,
            )
            prompt = prompt_template.replace("KEYWORD_BATCH_JSON", batch_json)
            parsed: list[dict[str, Any]] = []
            try:
                response = await self.call_llm(ctx, prompt)
                logger.info("[keyword_validator] raw LLM response:\n%s\n", response[:500])
                parsed = _parse_validation_json(response, batch)
            except LLMUnavailableError as exc:
                logger.warning(
                    "keyword_validator: LLM unavailable for batch of %d — applying hard rules. Error: %s",
                    len(batch), exc,
                )

            if not parsed:
                # LLM returned garbage — apply hard rules to every keyword in this batch
                # so they never stay stuck as raw.
                logger.warning(
                    "keyword_validator: LLM parse failed for batch of %d — applying hard rules only",
                    len(batch),
                )
                for row in batch:
                    if _should_hard_archive(row):
                        status = "archived"
                        reason = "hard-rule fallback: failed LLM parse, volume/kd/intent out of range"
                    else:
                        status = "validated"
                        reason = "hard-rule fallback: LLM parse failed, metrics within acceptable range"
                    parsed.append({
                        "keyword_id": str(row["id"]),
                        "keyword": row["keyword"],
                        "worth_targeting": status == "validated",
                        "reason": reason,
                    })

            llm_results.extend(parsed)

        # 7. Validate each result through the contract, then persist
        await _apply_validation_results(llm_results, ctx.db)

        # 8. Count from DB — never trust parsed list counts
        counts = await _count_outcomes(keyword_ids, ctx.db)

        return AgentResult(
            status="success",
            data={
                "total": len(rows),
                "validated": counts["validated"],
                "archived": counts["archived"],
                "data_source": data_source,
            },
            tokens_used=ctx.llm.last_tokens_used,
            cost_usd=ctx.llm.last_cost_usd,
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

def _in_clause(ids: list[str]) -> tuple[str, dict[str, str]]:
    """Build an IN clause and matching params dict for a list of IDs."""
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
            f"SELECT id, keyword, volume, kd, cpc, intent, status "
            f"FROM keywords "
            f"WHERE id IN ({placeholders}) AND status = 'raw'"
        ),
        params,
    )
    return [dict(row) for row in result.mappings().all()]


async def _update_keyword_metrics(
    rows: list[dict[str, Any]],
    metrics_map: dict[str, dict[str, Any]],
    data_source: str,
    db: AsyncSession,
) -> None:
    for row in rows:
        m = metrics_map.get(row["keyword"], {})
        await db.execute(
            text(
                "UPDATE keywords SET "
                "volume = :volume, kd = :kd, cpc = :cpc, "
                "data_source = :data_source, updated_at = now() "
                "WHERE id = :id"
            ),
            {
                "id": str(row["id"]),
                "volume": m.get("volume") if m else row.get("volume"),
                "kd": m.get("kd") if m else row.get("kd"),
                "cpc": m.get("cpc") if m else row.get("cpc"),
                "data_source": data_source,
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
            f"UPDATE keywords SET status = :status, reason = :reason, updated_at = now() "
            f"WHERE id IN ({placeholders})"
        ),
        {"status": status, "reason": reason, **params},
    )
    await db.flush()


async def _apply_validation_results(
    results: list[dict[str, Any]], db: AsyncSession
) -> None:
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
    counts: dict[str, int] = {"validated": 0, "archived": 0}
    for row in result.fetchall():
        status = str(row[0])
        if status in counts:
            counts[status] = int(row[1])
    return counts


# ── Business logic ────────────────────────────────────────────────────────────

def _should_hard_archive(row: dict[str, Any]) -> bool:
    """Return True if hard rules require immediate archiving (no LLM needed)."""
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


# ── LLM response parsing ──────────────────────────────────────────────────────

_REFUSAL_PHRASES = [
    "i cannot", "i can't", "as an ai", "i don't have access",
    "i am unable", "i'm unable", "not able to provide",
]


_CODE_INDICATORS = ["function ", "const ", "var ", "let ", "=>", "console.log", "return {", "def "]


def _parse_validation_json(
    response: str, batch: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Extract validation results from any LLM output format.

    Handles fallback field names and matches by keyword TEXT when keyword_id
    is missing or null.
    """
    if not response or not response.strip():
        logger.warning("keyword_validator: empty LLM response")
        return []

    if any(p in response.lower() for p in _REFUSAL_PHRASES):
        logger.warning("keyword_validator: model refused to answer")
        return []

    # Detect code output — model returned a function/script instead of JSON
    head = response[:200]
    if any(indicator in head for indicator in _CODE_INDICATORS):
        logger.warning(
            "keyword_validator: model returned code instead of JSON — skipping. Head: %s", head
        )
        return []

    # Build text-based lookup for fallback matching when keyword_id is absent
    text_to_id = {r["keyword"].lower(): str(r["id"]) for r in batch}
    text_to_kw = {r["keyword"].lower(): r["keyword"] for r in batch}

    # Strip markdown fences and trailing commas
    cleaned = re.sub(r"```(?:json)?", "", response, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)

    data: Any = None

    # Fast path: response starts with [
    if cleaned.startswith("["):
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # Fallback: find a JSON array anywhere in the response
    if data is None:
        array_match = re.search(r"\[.*?\]", cleaned, re.DOTALL)
        if array_match:
            try:
                data = json.loads(array_match.group())
            except json.JSONDecodeError:
                pass

    if data is None:
        logger.warning(
            "keyword_validator: could not parse JSON. Raw response start: %s", response[:300]
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

        # Resolve keyword_id — accept fallback key names
        keyword_id = (
            item.get("keyword_id")
            or item.get("id")
            or item.get("uuid")
        )

        # Fall back to text-based matching when keyword_id is absent
        if not keyword_id:
            kw_lower = str(item.get("keyword") or "").lower().strip()
            keyword_id = text_to_id.get(kw_lower)
            if not keyword_id:
                logger.warning("keyword_validator: could not match item to batch keyword: %s", item)
                continue

        # Resolve keyword text
        keyword_text = str(item.get("keyword") or "").strip()
        if not keyword_text:
            id_lower = str(keyword_id).lower()
            keyword_text = text_to_kw.get(id_lower, "")
        if not keyword_text:
            continue

        # Resolve worth_targeting — accept fallback key names
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

        # Resolve reason — accept fallback key names
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


# ── Utilities ─────────────────────────────────────────────────────────────────

def _batches(items: list[Any], n: int):
    """Yield successive n-sized chunks of items."""
    for i in range(0, len(items), n):
        yield items[i : i + n]
