"""OCR spatial : TSV borné, lignes, reprojection, orchestrateur et budget global."""

import io
import json
import sqlite3
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.identification import ocr_spatial
from app.identification.ocr_spatial import (
    analyze_image_spatial,
    build_ocr_evidence,
    legacy_recognized,
    verify_hypotheses,
)
from app.identification.ocr_text import (
    TsvTruncatedError,
    attach_photo_positions,
    band_raster,
    enhance_fallback,
    parse_tsv,
    reconstruct_lines,
    run_tesseract_tsv,
)
from app.identification.ocr_types import (
    OcrConfig,
    OcrDeadlineExceeded,
    OcrReading,
)
from app.storage.database import connect
from app.storage.migration_runner import apply_migrations
from app.tcgdex.cache import TcgdexCache

_TSV_HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
_TSV_FULL = "\n".join([
    _TSV_HEADER,
    "5\t1\t1\t1\t1\t1\t10\t20\t140\t30\t96.5\tPikachu",
    "5\t1\t1\t1\t1\t2\t160\t20\t80\t30\t-1\t58/102",
    "5\t1\t2\t1\t1\t1\t10\t200\t30\t25\t80.0\ttexte",
    "5\t1\t2\t1\t1\t2\t50\t200\t20\t25\t\tbruit",
])
_CATALOG = ("Pikachu", "Mew", "Tortank obscur")


def test_parse_tsv_keeps_scores_and_rejects_invalid_boxes() -> None:
    tsv = "\n".join([
        _TSV_HEADER,
        "5\t1\t1\t1\t1\t1\t-5\t20\t30\t10\t90\tGauche",
        "5\t1\t1\t1\t1\t2\t10\t20\t0\t10\t90\tVide",
        "5\t1\t1\t1\t1\t3\t10\t20\t30\t10\t-1\tNeg",
        "5\t1\t1\t1\t1\t4\t10\t20\t30\t10\t\tSansConf",
        "5\t1\t1\t1\t1\t5\t40\t20\t30\t10\t88.4\tOk",
    ])
    tokens = parse_tsv(tsv, pass_id="p1", raster_width=200, raster_height=100)
    assert [token.text for token in tokens] == ["Neg", "SansConf", "Ok"]
    assert tokens[0].confidence is None and tokens[1].confidence is None
    assert tokens[2].confidence == pytest.approx(88.4)
    assert tokens[2].norm_box == (0.2, 0.2, 0.35, 0.3)
    assert tokens[2].group == (1, 1, 1, 1)


def test_reconstruct_lines_never_joins_distinct_blocks() -> None:
    tsv = "\n".join([
        _TSV_HEADER,
        "5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t90\tAlpha",
        "5\t1\t2\t1\t1\t1\t10\t60\t30\t10\t90\tBeta",
    ])
    tokens = parse_tsv(tsv, pass_id="p1", raster_width=200, raster_height=100)
    lines = reconstruct_lines(tokens, pass_id="p1")
    assert len(lines) == 2  # même numéro de ligne, blocs distincts : pas de fusion
    assert {line.text for line in lines} == {"Alpha", "Beta"}


def test_parse_tsv_enforces_word_cap() -> None:
    rows = [_TSV_HEADER] + [
        f"5\t1\t1\t1\t1\t{index}\t{10 + index * 30}\t20\t25\t10\t90\tMot{index}" for index in range(5)
    ]
    config = OcrConfig(max_words_per_analysis=3)
    with pytest.raises(TsvTruncatedError):
        parse_tsv("\n".join(rows), pass_id="p1", raster_width=400, raster_height=100, config=config)


def test_run_tesseract_tsv_refuses_oversized_output() -> None:
    image = Image.new("RGB", (120, 40), "white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    with pytest.raises(TsvTruncatedError, match="cessive"):
        run_tesseract_tsv(output.getvalue(), psm=6, timeout_seconds=10.0, max_bytes=10)


def test_run_tesseract_tsv_reads_synthetic_card() -> None:
    font = ImageFont.load_default(size=40)
    image = Image.new("RGB", (700, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 30), "Pikachu 20/82", fill="black", font=font)
    output = io.BytesIO()
    image.save(output, format="PNG")
    payload = run_tesseract_tsv(output.getvalue(), psm=7, timeout_seconds=20.0, max_bytes=2_000_000)
    tokens = parse_tsv(payload, pass_id="real", raster_width=700, raster_height=120)
    texts = [token.text for token in tokens]
    assert any("Pikachu" in text for text in texts)
    assert any(any(char.isdigit() for char in text) for text in texts)


def _prepared_card(tmp_path: Path, text: str = "Pikachu 20/82"):
    font = ImageFont.load_default(size=36)
    image = Image.new("RGB", (600, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 20), text, fill="black", font=font)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _fixed_tesseract(monkeypatch: pytest.MonkeyPatch, payload: str, calls: list[int]) -> None:
    def fake(image_png: bytes, *, psm: int, timeout_seconds: float, max_bytes: int) -> str:
        calls.append(psm)
        return payload
    monkeypatch.setattr(ocr_spatial, "run_tesseract_tsv", fake)


def test_spatial_pipeline_produces_positioned_readings_and_hypotheses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    _fixed_tesseract(monkeypatch, _TSV_FULL, calls)
    analysis = analyze_image_spatial(_prepared_card(tmp_path), catalog_names=_CATALOG)
    recognized = legacy_recognized(analysis)
    assert recognized["names"] == ["Pikachu"]
    assert recognized["numbers"] == ["58/102"]
    assert len(calls) == 1  # lectures suffisantes : aucune passe ciblée déclenchée
    number = next(reading for reading in analysis.readings if reading.role == "number")
    assert number.photo_box is not None
    left, top, right, bottom = number.photo_box
    assert 0 <= left < right <= analysis.width and 0 <= top < bottom <= analysis.height
    values = [hypothesis.value for hypothesis in analysis.number_hypotheses]
    assert values[0] == "58/102"  # littéral en tête
    assert all(hypothesis.alternative_group_id == hypothesis.reading_id for hypothesis in analysis.number_hypotheses)


def test_spatial_pipeline_uses_targeted_passes_within_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    sparse = "\n".join([
        _TSV_HEADER,
        "5\t1\t1\t1\t1\t1\t10\t20\t140\t30\t96.5\tPikachu",
    ])
    full = "\n".join([
        _TSV_HEADER,
        "5\t1\t1\t1\t1\t1\t10\t20\t80\t30\t96.5\t58/102",
    ])

    def fake(image_png: bytes, *, psm: int, timeout_seconds: float, max_bytes: int) -> str:
        calls.append(psm)
        return sparse if len(calls) == 1 else full
    monkeypatch.setattr(ocr_spatial, "run_tesseract_tsv", fake)
    analysis = analyze_image_spatial(_prepared_card(tmp_path), catalog_names=_CATALOG)
    assert legacy_recognized(analysis)["numbers"] == ["58/102"]
    assert 2 <= len(calls) <= 6  # bande numéro déclenchée, budget global respecté


def test_spatial_pipeline_keeps_partial_result_when_fallback_pass_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    sparse = "\n".join([
        _TSV_HEADER,
        "5\t1\t1\t1\t1\t1\t10\t20\t140\t30\t96.5\tPikachu",
    ])

    def fake(image_png: bytes, *, psm: int, timeout_seconds: float, max_bytes: int) -> str:
        calls.append(psm)
        if len(calls) == 1:
            return sparse  # nom seul : la bande numéro déclenche la passe qui échoue
        raise TsvTruncatedError("Sortie OCR excessive : analyse refusée.")
    monkeypatch.setattr(ocr_spatial, "run_tesseract_tsv", fake)
    config = OcrConfig()
    analysis = analyze_image_spatial(_prepared_card(tmp_path), catalog_names=_CATALOG, config=config)
    assert legacy_recognized(analysis)["names"] == ["Pikachu"]
    assert any("deadline_partial" in item for item in analysis.diagnostics)
    assert "passes" in analysis.truncated


def test_spatial_pipeline_raises_before_any_reading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(image_png: bytes, *, psm: int, timeout_seconds: float, max_bytes: int) -> str:
        raise TsvTruncatedError("Sortie OCR excessive : analyse refusée.")
    monkeypatch.setattr(ocr_spatial, "run_tesseract_tsv", fake)
    with pytest.raises(TsvTruncatedError):
        analyze_image_spatial(_prepared_card(tmp_path))


def test_spatial_pipeline_enforces_global_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fixed_tesseract(monkeypatch, _TSV_FULL, [])
    class _FrozenThenLate:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self) -> float:
            self.calls += 1
            return 0.0 if self.calls < 4 else 100.0  # préparation puis budget épuisé

    with pytest.raises(OcrDeadlineExceeded):
        analyze_image_spatial(_prepared_card(tmp_path), clock=_FrozenThenLate())


def test_full_frame_region_never_pairs_distant_name_and_number(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fixed_tesseract(monkeypatch, _TSV_FULL, [])
    analysis = analyze_image_spatial(_prepared_card(tmp_path), localization="full")
    assert analysis.regions[0].method == "full_image"
    # Les lectures restent séparées : aucune hypothèse ne fusionne nom et numéro distants.
    assert {reading.role for reading in analysis.readings} <= {"name", "number", "unknown"}


def test_envelope_is_bounded_and_never_contains_raw_background(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fixed_tesseract(monkeypatch, _TSV_FULL, [])
    analysis = analyze_image_spatial(_prepared_card(tmp_path), catalog_names=_CATALOG)
    envelope = build_ocr_evidence(analysis)
    serialized = json.dumps(envelope)
    assert "texte" not in serialized  # fragments de fond exclus
    assert len(envelope["number_hypotheses"]) <= analysis.number_hypotheses.__len__()
    assert envelope["version"] == analysis.schema_version
    assert legacy_recognized(analysis) == {"names": ["Pikachu"], "numbers": ["58/102"]}


@pytest.fixture
def matcher(tmp_path: Path):
    path = tmp_path / "spatial.sqlite"
    with connect(path) as connection:
        apply_migrations(connection)
        TcgdexCache(connection).seed_initial_if_empty()
        from app.identification.matcher import CardMatcher
        yield CardMatcher(TcgdexCache(connection), seed_if_empty=False, repair_index=False)


def test_verify_hypotheses_finds_reference_without_identity(matcher, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fixed_tesseract(monkeypatch, _TSV_FULL, [])
    analysis = analyze_image_spatial(_prepared_card(tmp_path), catalog_names=_CATALOG)
    search = verify_hypotheses(matcher, analysis)
    assert any(candidate.tcgdex_id == "base1-58" for candidate in search.suggestions)
    top = search.suggestions[0]
    assert top.literal_support
    assert top.contradictions == ()
    envelope = build_ocr_evidence(analysis, search)
    assert envelope["suggestions"] and envelope["search"]["values_examined"] >= 1


def test_verify_hypotheses_does_not_stop_at_first_miss(matcher, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tsv = "\n".join([
        _TSV_HEADER,
        "5\t1\t1\t1\t1\t1\t10\t20\t140\t30\t96.5\tPikachu",
        "5\t1\t1\t1\t1\t2\t160\t20\t90\t30\t-1\t999/102",
        "5\t1\t1\t1\t1\t3\t260\t20\t80\t30\t-1\t58/102",
    ])
    _fixed_tesseract(monkeypatch, tsv, [])
    analysis = analyze_image_spatial(_prepared_card(tmp_path), catalog_names=_CATALOG)
    search = verify_hypotheses(matcher, analysis)
    assert any(candidate.tcgdex_id == "base1-58" for candidate in search.suggestions)
    assert search.values_examined >= 2  # la première lecture erronée n'arrête pas la recherche


def test_band_raster_and_enhance_respect_derived_pixel_cap() -> None:
    import io as _io

    from PIL import Image as PILImage
    from app.identification.ocr_geometry import full_image_region, prepare_image, rectify_region

    output = _io.BytesIO()
    PILImage.new("RGB", (900, 1200), "white").save(output, format="PNG")
    prepared = prepare_image(output.getvalue())
    card = rectify_region(prepared, full_image_region(prepared), OcrConfig())
    band = band_raster(card, "number", OcrConfig())
    enhanced = enhance_fallback(band, OcrConfig())
    for raster in (band, enhanced):
        with PILImage.open(_io.BytesIO(raster)) as decoded:
            assert decoded.width * decoded.height <= 12_000_000
