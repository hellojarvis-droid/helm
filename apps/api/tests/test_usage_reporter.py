"""usage_reporter — aggregate message.agent cost into Stripe metered usage."""

from __future__ import annotations

import pytest
from helm.db.models import AgentSession, Business, User
from helm.services import event_log, stripe_client, usage_reporter

from tests.conftest import requires_db


@requires_db
@pytest.mark.asyncio
async def test_report_usage_posts_cents_to_stripe_and_advances_watermark(
    session, monkeypatch
) -> None:
    user = User(
        supabase_id="sub-usage-1",
        email="usage1@example.com",
        tier="operator",
        stripe_customer_id="cus_u1",
        stripe_subscription_id="sub_u1",
        stripe_metered_item_id="si_metered_u1",
    )
    session.add(user)
    await session.flush()
    biz = Business(user_id=user.id, name="A", vertical="dtc_physical", status="active")
    session.add(biz)
    await session.flush()
    ag = AgentSession(user_id=user.id, business_id=biz.id, status="active")
    session.add(ag)
    await session.commit()

    # Two LLM turns: 7¢ + 11¢ = 18¢
    for c in (7, 11):
        await event_log.write(
            session,
            session_id=ag.id,
            business_id=biz.id,
            event_type="message.agent",
            agent_name="ceo_agent",
            payload={"text": "hi"},
            cost_cents=c,
        )

    # Stub the Stripe SDK call.
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        usage_reporter,
        "_configured_stripe",
        lambda: type(
            "S",
            (),
            {
                "SubscriptionItem": type(
                    "I",
                    (),
                    {
                        "create_usage_record": staticmethod(
                            lambda iid, **kwargs: calls.append({"iid": iid, **kwargs})
                        )
                    },
                )()
            },
        )(),
    )
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    from helm import config

    config.get_settings.cache_clear()

    cents = await usage_reporter.report_usage_for_user(session, str(user.id))
    assert cents == 18
    assert len(calls) == 1
    assert calls[0]["iid"] == "si_metered_u1"
    assert calls[0]["quantity"] == 18
    assert calls[0]["timestamp"] == "now"
    assert calls[0]["action"] == "increment"

    # Watermark advanced — re-running with no new events posts nothing.
    cents2 = await usage_reporter.report_usage_for_user(session, str(user.id))
    assert cents2 == 0
    assert len(calls) == 1

    # New event after the watermark gets reported in isolation.
    await event_log.write(
        session,
        session_id=ag.id,
        business_id=biz.id,
        event_type="message.agent",
        agent_name="ceo_agent",
        payload={"text": "more"},
        cost_cents=4,
    )
    cents3 = await usage_reporter.report_usage_for_user(session, str(user.id))
    assert cents3 == 4
    assert len(calls) == 2
    assert calls[1]["quantity"] == 4

    config.get_settings.cache_clear()


@requires_db
@pytest.mark.asyncio
async def test_report_usage_noop_without_metered_item(session) -> None:
    user = User(
        supabase_id="sub-usage-2",
        email="usage2@example.com",
        tier="founder",
        stripe_customer_id="cus_u2",
    )
    # No stripe_metered_item_id — common for founder tier without metered overage.
    session.add(user)
    await session.commit()

    cents = await usage_reporter.report_usage_for_user(session, str(user.id))
    assert cents == 0


def test_extract_metered_item_id_picks_metered_item() -> None:
    from helm.services.stripe_billing import extract_metered_item_id

    sub = {
        "items": {
            "data": [
                {
                    "id": "si_flat",
                    "price": {"id": "price_flat", "recurring": {"usage_type": "licensed"}},
                },
                {
                    "id": "si_metered",
                    "price": {"id": "price_metered", "recurring": {"usage_type": "metered"}},
                },
            ]
        }
    }
    assert extract_metered_item_id(sub) == "si_metered"

    # Flat-only sub returns None.
    flat_only = {
        "items": {
            "data": [
                {"id": "si_flat", "price": {"recurring": {"usage_type": "licensed"}}},
            ]
        }
    }
    assert extract_metered_item_id(flat_only) is None


# Touch reference so unused-import lint is happy when adding more tests later.
_ = stripe_client
