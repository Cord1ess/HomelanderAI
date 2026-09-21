"""Tests for the EyePACS Diabetic Retinopathy screening arm."""

from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter

from app import catalogue
from app.arms import ARMS, arm_for_intake, eyepacs_dr
from app.scoring import score


def create_synthetic_fundus(has_lesions: bool = False, size=(256, 256)) -> bytes:
    """Generate a synthetic fundus-like image with a red/orange retina on black background."""
    img = Image.new("RGB", size, color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Circular retina (warm orange-red typical of fundus photography)
    draw.ellipse([20, 20, size[0] - 20, size[1] - 20], fill=(185, 75, 25))

    # Optic disc (yellowish-white circle)
    draw.ellipse([180, 110, 215, 145], fill=(240, 215, 140))
    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    draw = ImageDraw.Draw(img)

    if has_lesions:
        # Microaneurysms / blot hemorrhages (dark spots)
        for x, y in [(75, 80), (85, 120), (105, 95), (120, 140), (130, 90), (145, 115)]:
            draw.ellipse([x, y, x + 6, y + 6], fill=(45, 12, 10))

        # Hard exudates (bright yellowish lipid deposits)
        for x, y in [(90, 70), (110, 160), (140, 150), (100, 130)]:
            draw.ellipse([x, y, x + 8, y + 8], fill=(255, 240, 160))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Metadata and Registration ────────────────────────────────────────────────


def test_spec_is_valid():
    assert eyepacs_dr.NAME == "eyepacs_dr"
    assert "resnet50" in eyepacs_dr.VERSION
    assert len(eyepacs_dr.ICDR_CLASSES) == 5
    assert eyepacs_dr.ICDR_CLASSES[0] == "No DR (Normal)"
    assert eyepacs_dr.ICDR_CLASSES[4] == "Proliferative DR"
    assert "EyePACS" in eyepacs_dr.VALIDATION


def test_arm_is_available():
    assert eyepacs_dr.available() is True


def test_arm_registered_in_arms():
    assert eyepacs_dr.NAME in ARMS
    registered = ARMS[eyepacs_dr.NAME]
    assert registered.intake_id == "eyepacs"
    assert registered.arm_type == "vision"


def test_arm_for_intake_resolves():
    arm = arm_for_intake("eyepacs")
    assert arm is not None
    assert arm.name == eyepacs_dr.NAME


def test_catalogue_reflects_eyepacs_availability():
    entries = catalogue.as_dicts()
    eyepacs_entry = next((e for e in entries if e["id"] == "eyepacs"), None)
    assert eyepacs_entry is not None
    assert eyepacs_entry["available"] is True
    assert eyepacs_entry["arm_name"] == eyepacs_dr.NAME
    assert "EyePACS" in eyepacs_entry["validation"]


# ── Robustness & Graceful Degradation ─────────────────────────────────────────


def test_empty_payload_returns_unusable():
    result = eyepacs_dr.run(b"")
    assert not result.usable
    assert result.score is None
    assert "Empty image" in (result.error or "")


def test_corrupted_payload_returns_unusable():
    result = eyepacs_dr.run(b"not_an_image_data")
    assert not result.usable
    assert result.score is None
    assert result.error is not None


# ── Clinical Evaluation & Explainability ─────────────────────────────────────


def test_clean_fundus_evaluation():
    fundus_bytes = create_synthetic_fundus(has_lesions=False)
    result = eyepacs_dr.run(fundus_bytes)

    assert result.usable is True
    assert result.score is not None
    assert 0.0 <= result.score <= 100.0
    assert result.raw_score is not None
    assert 0.0 <= result.raw_score <= 4.0

    # Clean retina should have low risk
    assert result.score < 40.0
    assert result.details["referable_dr"] is False

    # Check Grad-CAM artifacts
    assert "gradcam_overlay" in result.artifacts
    assert "heatmap" in result.artifacts
    assert len(result.artifacts["gradcam_overlay"]) > 100
    assert len(result.artifacts["heatmap"]) > 100


def test_lesion_fundus_escalates_score():
    clean_bytes = create_synthetic_fundus(has_lesions=False)
    lesion_bytes = create_synthetic_fundus(has_lesions=True)

    clean_res = eyepacs_dr.run(clean_bytes)
    lesion_res = eyepacs_dr.run(lesion_bytes)

    assert clean_res.usable and lesion_res.usable
    # Lesions must yield higher severity and score
    assert lesion_res.score > clean_res.score
    assert lesion_res.raw_score > clean_res.raw_score
    assert lesion_res.details["lesion_density"] > clean_res.details["lesion_density"]


# ── Underwriting Scoring Rules Integration ───────────────────────────────────


def test_diabetes_history_underwriting_adjustments():
    # Base vision score: 25.0 (Low risk)
    base_vision = 25.0

    # 1. Clean history
    res1 = score(base_vision, declared_history={})
    assert res1.crs == 25.0
    assert res1.tier == "low"

    # 2. Long-standing diabetes (>10 years) + hypertension
    res2 = score(
        base_vision,
        declared_history={
            "diabetes_duration": "Over 10 years",
            "hypertension": True,
        },
    )
    # +15.0 for duration >10 yrs, +10.0 for hypertension = +25.0 total
    assert res2.crs == 50.0
    assert res2.tier == "moderate"
    keys = [a.key for a in res2.adjustments]
    assert "diabetes_duration_over_10_years" in keys
    assert "diabetes_with_hypertension" in keys
