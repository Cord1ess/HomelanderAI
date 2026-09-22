"""Fill the demo company with realistic applications for a showcase.

    python scripts/seed_demo.py            # adds ~30 clients if none are seeded yet
    python scripts/seed_demo.py --reset    # removes the seeded clients first

Run after `alembic upgrade head` and `db/seed.sql`. It seeds the built-in
company ("Demo Insurance Co.", the one `underwriter` / `medical` / `admin`
sign in to), creating its rows if they do not exist yet.

Every row is one the product could have written itself: scores come from the
real fusion and history rules (`app.scoring`), premiums from the company's
own pricing policy, and audit entries through the same hash-chained writer
the API uses, so the trail verifies. What is invented is the people, their
answers and their readings; no images are stored, so a seeded application's
review screen says so.

Seeded clients have emails ending in `@demo.example` and share one portal
password, printed at the end, so any of them can be shown signing in.
"""

from __future__ import annotations

import asyncio
import random
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import delete, select, text  # noqa: E402

from app import persistence, plans, scoring, turnaround  # noqa: E402
from app.arms import ARMS  # noqa: E402
from app.core.security import generate_portal_id, hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Applicant,
    Application,
    ApplicationStatus,
    CompositeScore,
    ModelRun,
    ModelRunStatus,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    RequestedDocument,
    RiskTier,
    SubScore,
    Tenant,
    UnderwriterDecision,
    UnderwriterDecisionType,
    User,
)
from app.routers.auth import ADMIN_TENANT_ID, BUILT_IN_ACCOUNTS, _ensure_built_in_rows  # noqa: E402

SEED_DOMAIN = "demo.example"
PORTAL_PASSWORD = "client123"
RNG = random.Random(20260922)

FIRST = ["Rahim", "Fatema", "Karim", "Nusrat", "Abdul", "Sadia", "Tanvir", "Rokeya", "Imran", "Shirin",
         "Mahmud", "Nasrin", "Jahid", "Farzana", "Arif", "Sultana", "Habib", "Rashida", "Faisal", "Taslima",
         "Mizan", "Rumana", "Sohel", "Parvin", "Kamal", "Salma", "Anwar", "Laila", "Rafiq", "Mousumi"]
LAST = ["Uddin", "Begum", "Hossain", "Jahan", "Malek", "Islam", "Ahmed", "Khatun", "Chowdhury", "Akter",
        "Rahman", "Sultana", "Karim", "Haque", "Sarkar", "Mia", "Ali", "Sikder", "Bhuiyan", "Nahar"]
COVERS = [("life", [500_000, 1_000_000, 1_500_000, 2_500_000, 5_000_000], ["10", "15", "20"]),
          ("health", [250_000, 500_000, 1_000_000], ["1", "5", "10"]),
          ("critical_illness", [1_000_000, 1_500_000, 3_000_000], ["10", "20"])]
CHEST_FINDINGS = ["Infiltration", "Consolidation", "Effusion", "Nodule", "Fibrosis", "Atelectasis"]

# ── one client's story: which readers ran and what they found ─────────────────


def readings_for(profile: str) -> dict[str, float]:
    """Per-reader scores that make sense together for a risk profile."""
    r = RNG
    if profile == "low":
        out = {"tb_xray": r.uniform(1, 18)}
        if r.random() < 0.55:
            out["dr_fundus"] = r.uniform(0.5, 12)
        if r.random() < 0.45:
            out["ecg_12lead"] = r.uniform(0, 10)
        if r.random() < 0.35:
            out["mortality"] = r.uniform(5, 25)
        return out
    if profile == "moderate":
        lead = r.choice(["tb_xray", "dr_fundus", "ecg_12lead", "mortality"])
        out = {"tb_xray": r.uniform(3, 20)}
        out[lead] = r.uniform(45, 72)
        if lead != "dr_fundus" and r.random() < 0.5:
            out["dr_fundus"] = r.uniform(1, 15)
        if lead != "mortality" and r.random() < 0.4:
            out["mortality"] = r.uniform(15, 40)
        return out
    out = {"tb_xray": r.uniform(6, 30)}
    lead = r.choice(["tb_xray", "dr_fundus", "ecg_12lead", "mortality"])
    out[lead] = r.uniform(85, 100)
    second = r.choice([k for k in ["dr_fundus", "ecg_12lead", "mortality"] if k != lead])
    out[second] = r.uniform(35, 75)
    return out


def history_for(profile: str, age: int) -> dict:
    r = RNG
    symptoms = {"cough_over_2_weeks": False, "weight_loss": False, "night_sweats": False,
                "haemoptysis": False, "fever": False}
    history = {"diabetes": False, "hiv": False, "household_tb_contact": False,
               "antibiotics_no_improvement": False, "smoker": r.random() < 0.3,
               "prior_tb": False, "prior_tb_treatment_completed": False}
    if profile != "low" and r.random() < 0.5:
        history["diabetes"] = True
    if profile == "elevated" and r.random() < 0.5:
        symptoms["cough_over_2_weeks"] = True
        symptoms["night_sweats"] = r.random() < 0.5
    cardio = {"hypertension": age > 45 and r.random() < 0.4, "high_cholesterol": r.random() < 0.2,
              "family_heart_disease": r.random() < 0.2}
    return {"cxr_lung": {"symptoms": symptoms, "history": history, "cardio": cardio}}


def chest_details(score: float) -> dict:
    """What the chest reader's findings would look like for this score."""
    r = RNG
    probabilities = {f: round(min(0.99, max(0.01, r.gauss(score / 140, 0.08))), 3) for f in CHEST_FINDINGS}
    contributions = {f: round((p - 0.2) * (score / 40), 3) for f, p in probabilities.items()}
    return {
        "scorer": "logistic_regression_over_18_findings",
        "backbone": "densenet121-res224-all",
        "validation": "Internal cross-validation on one hospital's films; not externally validated.",
        "cv_auc": 0.877,
        "findings": probabilities,
        "contributions": contributions,
    }


async def seed(reset: bool) -> int:
    await _ensure_built_in_rows()
    async with AsyncSessionLocal() as db:
        tenant = await db.get(Tenant, ADMIN_TENANT_ID)
        assert tenant is not None
        users = {u.email: u for u in (await db.execute(select(User).where(User.tenant_id == tenant.id))).scalars()}
        underwriter = users[next(a.username for a in BUILT_IN_ACCOUNTS if a.role.value == "underwriter")]
        medical = users[next(a.username for a in BUILT_IN_ACCOUNTS if a.role.value == "medical_professional")]

        existing = (
            await db.execute(select(Applicant).where(Applicant.email.like(f"%@{SEED_DOMAIN}")))
        ).scalars().all()
        if existing and not reset:
            print(f"{len(existing)} seeded clients already exist; run with --reset to replace them.")
            return 1
        if existing:
            # Their applications cascade; the audit trigger has to be lowered for the teardown.
            await db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_delete"))
            await db.execute(delete(Applicant).where(Applicant.id.in_([a.id for a in existing])))
            await db.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_delete"))
            await db.commit()
            print(f"removed {len(existing)} previously seeded clients")

        arm_rows = {name: await persistence.register_arm(db, arm) for name, arm in ARMS.items()}
        thresholds = scoring.Thresholds(
            low_max=float(tenant.tier_low_max), moderate_max=float(tenant.tier_moderate_max)
        )
        policy = plans.Policy.from_tenant(tenant)
        password_hash = hash_password(PORTAL_PASSWORD)

        now = datetime.now(UTC)
        names = RNG.sample([(f, l) for f in FIRST for l in LAST], 30)
        counts: dict[str, int] = {}
        for i, (first, last) in enumerate(names):
            profile = RNG.choices(["low", "moderate", "elevated"], weights=[55, 30, 15])[0]
            age = RNG.randint(22, 68)
            dob = (now - timedelta(days=age * 365 + RNG.randint(0, 364))).date()
            submitted = now - timedelta(days=RNG.uniform(0.2, 55), hours=RNG.uniform(0, 8))
            cover_type, amounts, terms = RNG.choice(COVERS)
            amount = Decimal(RNG.choice(amounts))
            declared = history_for(profile, age)

            applicant = Applicant(
                tenant_id=tenant.id,
                name=f"{first} {last}",
                phone=f"017{RNG.randint(10000000, 99999999)}",
                email=f"{first.lower()}.{last.lower()}{i}@{SEED_DOMAIN}",
                date_of_birth=dob,
                sex=RNG.choice(["male", "female"]),
                portal_id=generate_portal_id(),
                password_hash=password_hash,
                created_at=submitted,
            )
            db.add(applicant)
            await db.flush()

            readings = readings_for(profile)
            fused = scoring.fuse(list(readings.values()))
            scored = scoring.score(fused, declared, age=age, thresholds=thresholds)
            crs, tier = scored.crs, scored.tier

            days_open = (now - submitted).days
            if days_open >= 3:
                status = ApplicationStatus.DECIDED if RNG.random() < 0.9 else ApplicationStatus.AWAITING_EVIDENCE
            else:
                status = RNG.choice([ApplicationStatus.SCORED, ApplicationStatus.SCORED, ApplicationStatus.DECIDED])
            if tier == "elevated" and status == ApplicationStatus.SCORED and RNG.random() < 0.6:
                status = ApplicationStatus.ESCALATED

            application = Application(
                tenant_id=tenant.id,
                applicant_id=applicant.id,
                status=status,
                coverage_type=cover_type,
                coverage_amount=amount,
                policy_term=RNG.choice(terms),
                models_requested=[ARMS[n].intake_id for n in readings],
                declared_history=declared,
                submitted_at=submitted,
                processing_started_at=submitted + timedelta(seconds=2),
                evaluated_at=submitted + timedelta(seconds=RNG.randint(20, 90)),
                expected_by=turnaround.add_business_days(submitted.date(), tenant.turnaround_business_days),
            )
            db.add(application)
            await db.flush()

            for name, value in readings.items():
                run = ModelRun(
                    tenant_id=tenant.id,
                    application_id=application.id,
                    model_arm_id=arm_rows[name].id,
                    status=ModelRunStatus.COMPLETED,
                    started_at=submitted + timedelta(seconds=3),
                    completed_at=submitted + timedelta(seconds=RNG.randint(8, 80)),
                )
                db.add(run)
                await db.flush()
                db.add(
                    SubScore(
                        tenant_id=tenant.id,
                        model_run_id=run.id,
                        raw_score=Decimal(str(round(value / 100, 4))),
                        calibrated_score=Decimal(str(round(value, 2))),
                        details=chest_details(value) if name == "tb_xray" else {"scorer": ARMS[name].version},
                    )
                )
            db.add(
                CompositeScore(
                    tenant_id=tenant.id,
                    application_id=application.id,
                    version=1,
                    crs_value=Decimal(str(crs)),
                    tier=RiskTier(tier),
                    tier_thresholds=thresholds.as_dict(),
                    adjustments=[asdict(a) for a in scored.adjustments],
                    computed_at=application.evaluated_at,
                )
            )

            await persistence.append_audit(
                db,
                tenant_id=tenant.id,
                application_id=application.id,
                event_type="application_submitted",
                payload={"reference": applicant.external_ref, "seeded": True},
                actor_user_id=underwriter.id,
            )

            if status == ApplicationStatus.AWAITING_EVIDENCE:
                db.add(
                    RequestedDocument(
                        tenant_id=tenant.id,
                        application_id=application.id,
                        description=RNG.choice(
                            ["A chest X-ray taken within the last 6 months", "The full blood count report",
                             "The cardiologist's letter", "HbA1c result"]
                        ),
                        requested_by=underwriter.id,
                        requested_at=submitted + timedelta(days=1),
                    )
                )
            if status == ApplicationStatus.ESCALATED:
                await persistence.append_audit(
                    db, tenant_id=tenant.id, application_id=application.id,
                    event_type="escalated", payload={"note": "Please review the findings.", "by_role": "underwriter"},
                    actor_user_id=underwriter.id,
                )
                db.add(
                    Notification(
                        tenant_id=tenant.id, user_id=medical.id, application_id=application.id,
                        notification_type=NotificationType.TIER_ESCALATION, channel=NotificationChannel.IN_APP,
                        status=NotificationStatus.SENT,
                        message=f"{applicant.external_ref} has been escalated to you for a decision.",
                    )
                )
            if status == ApplicationStatus.DECIDED:
                decided_at = submitted + timedelta(days=RNG.uniform(0.3, 3.5))
                if tier == "low":
                    kind, premium, who = UnderwriterDecisionType.CONFIRMED_FAST_TRACK, None, underwriter
                else:
                    suggested = plans.monthly_premium("moderate", float(amount), policy) or 7500.0
                    factor = RNG.uniform(1.0, 1.35) if tier == "elevated" else RNG.uniform(0.95, 1.15)
                    kind = UnderwriterDecisionType.APPROVED_WITH_ADJUSTMENT
                    premium = Decimal(str(round(suggested * factor / 50) * 50))
                    who = medical if tier == "elevated" else underwriter
                    if tier == "elevated":
                        await persistence.append_audit(
                            db, tenant_id=tenant.id, application_id=application.id,
                            event_type="escalated", payload={"note": None, "by_role": "underwriter"},
                            actor_user_id=underwriter.id,
                        )
                db.add(
                    UnderwriterDecision(
                        tenant_id=tenant.id, application_id=application.id, underwriter_id=who.id,
                        decision=kind, final_premium=premium, decided_at=decided_at,
                    )
                )
                await persistence.append_audit(
                    db, tenant_id=tenant.id, application_id=application.id,
                    event_type="decision_recorded",
                    payload={"decision": kind.value, "final_premium": float(premium) if premium else None},
                    actor_user_id=who.id,
                )
            counts[f"{tier}/{status.value}"] = counts.get(f"{tier}/{status.value}", 0) + 1

        await db.commit()

    print("seeded 30 clients for Demo Insurance Co.:")
    for key in sorted(counts):
        print(f"  {key:32s} {counts[key]}")
    print(f"portal password for every seeded client: {PORTAL_PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(seed(reset="--reset" in sys.argv)))
