import re
from typing import Dict, List, Optional

from core import storage


def cluster_sample_into_campaign(
    conn,
    sample_id: int,
    target_brand: Optional[str] = None,
    dom_hash: Optional[str] = None,
    kit_name: Optional[str] = None
) -> Dict:
    # 1. Поиск совпадения по связке (бренд + структурный DOM-хэш)
    matched = storage.find_matching_campaign(conn, target_brand=target_brand, dom_hash=dom_hash)

    if matched:
        campaign_id = matched["id"]
        storage.update_campaign_stats(conn, campaign_id)
        storage.link_sample_campaign(conn, sample_id, campaign_id)

        # Сохраняем компактный reason code принадлежности к кампании
        storage.add_signature(
            conn,
            sample_id,
            "reason_code",
            f"CAMPAIGN_MEMBER_{matched['name']}",
            {"campaign_id": campaign_id, "sample_count": matched.get("sample_count", 1) + 1}
        )

        return {
            "is_new": False,
            "campaign_id": campaign_id,
            "name": matched["name"],
            "target_brand": matched.get("target_brand"),
            "sample_count": matched.get("sample_count", 1) + 1,
        }

    # 2. Если аналогов нет — создаем новую кампанию
    brand_slug = re.sub(r"[^\w]", "", (target_brand or "GENERIC").upper()) or "GENERIC"
    hash_slug = dom_hash[:8].upper() if dom_hash else "UNSTRUCTURED"
    campaign_name = f"CAMP_{brand_slug}_{hash_slug}"

    # Проверяем уникальность имени, если совпало с редким коллизией
    existing = conn.execute("SELECT id FROM campaigns WHERE name=?", (campaign_name,)).fetchone()
    if existing:
        campaign_name = f"{campaign_name}_{sample_id}"

    new_id = storage.create_campaign(
        conn,
        name=campaign_name,
        target_brand=target_brand,
        dom_hash=dom_hash,
        kit_name=kit_name
    )
    storage.link_sample_campaign(conn, sample_id, new_id)

    storage.add_signature(
        conn,
        sample_id,
        "reason_code",
        f"CAMPAIGN_INIT_{campaign_name}",
        {"campaign_id": new_id, "is_first_sample": True}
    )

    return {
        "is_new": True,
        "campaign_id": new_id,
        "name": campaign_name,
        "target_brand": target_brand,
        "sample_count": 1,
    }
