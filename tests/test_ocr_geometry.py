"""Géométrie OCR : EXIF, cadrage manuel, homographie, plafonds et repli automatique."""

import io
import math

import pytest
from PIL import Image

from app.identification.ocr_geometry import (
    GeometryError,
    mat_apply,
    mat_invert,
    mat_mul,
    order_quad,
    polygon_iou,
    prepare_image,
    project_box,
    quad_destination_size,
    rectify_region,
    auto_detect_regions,
    full_image_region,
    manual_region,
    validate_selection,
)
from app.identification.ocr_types import CropSelection, OcrConfig, PreparedImage


def _png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _prepared(width: int = 400, height: int = 300) -> PreparedImage:
    return prepare_image(_png(Image.new("RGB", (width, height), "white")))


def test_prepare_image_applies_exif_orientation_once() -> None:
    expected_by_tag = {1: None, 3: Image.Transpose.ROTATE_180, 6: Image.Transpose.ROTATE_270, 8: Image.Transpose.ROTATE_90}
    for tag, transpose in expected_by_tag.items():
        source = Image.new("RGB", (120, 80), (200, 30, 40))
        output = io.BytesIO()
        exif = Image.Exif()
        exif[0x0112] = tag
        source.save(output, format="JPEG", exif=exif)
        prepared = prepare_image(output.getvalue())
        expected = source if transpose is None else source.transpose(transpose)
        assert (prepared.width, prepared.height) == (expected.width, expected.height)
        assert prepared.width * prepared.height == 120 * 80
        with Image.open(io.BytesIO(prepared.pixels)) as decoded:
            observed = decoded.convert("RGB").getpixel((5, 5))
            wanted = expected.convert("RGB").getpixel((5, 5))
        # Le JPEG est lossy : comparaison par canal avec tolérance d'encodage.
        assert all(abs(a - b) <= 2 for a, b in zip(observed, wanted))
        assert f":{expected.width}x{expected.height}" in prepared.image_ref


def test_prepare_image_bounds_and_formats() -> None:
    with pytest.raises(ValueError, match="8 Mo"):
        prepare_image(b"x" * (8 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="12 millions"):
        prepare_image(_png(Image.new("RGB", (4000, 4000), "white")))
    with pytest.raises(ValueError, match="illisible"):
        prepare_image(b"pas une image")


def test_prepare_image_reference_is_stable_and_content_addressed() -> None:
    image = _png(Image.new("RGB", (50, 40), "white"))
    assert prepare_image(image).image_ref == prepare_image(image).image_ref
    assert prepare_image(image).image_ref != prepare_image(_png(Image.new("RGB", (50, 40), "black"))).image_ref


def test_validate_selection_rectangle_rules() -> None:
    with pytest.raises(GeometryError):
        validate_selection(CropSelection(rect=(0, 0, 10, 10), rotation=45), 100, 100)
    with pytest.raises(GeometryError):
        validate_selection(CropSelection(rect=(0, 0, 10, 10), quad=((0, 0), (1, 0), (1, 1), (0, 1))), 100, 100)
    with pytest.raises(GeometryError, match="vide"):
        validate_selection(CropSelection(rect=(5, 5, 5, 20)), 100, 100)
    with pytest.raises(GeometryError, match="hors"):
        validate_selection(CropSelection(rect=(0, 0, 120, 20)), 100, 100)
    with pytest.raises(GeometryError):
        validate_selection(CropSelection(rect=(math.nan, 0, 10, 10)), 100, 100)
    with pytest.raises(GeometryError):
        validate_selection(CropSelection(rect=(0, 0, math.inf, 10)), 100, 100)
    validated = validate_selection(CropSelection(rect=(-0.2, 0, 60, 20)), 100, 100)
    assert validated.rect == (0.0, 0.0, 60.0, 20.0)


def test_validate_selection_quad_rules() -> None:
    square = ((10.0, 10.0), (90.0, 10.0), (90.0, 90.0), (10.0, 90.0))
    assert validate_selection(CropSelection(quad=square), 100, 100).quad == order_quad(square)
    with pytest.raises(GeometryError, match="non distincts"):
        validate_selection(CropSelection(quad=((10, 10), (10, 10), (90, 90), (10, 90))), 100, 100)
    with pytest.raises(GeometryError, match="non convexe|croisés|colinéaire|dégénéré"):
        validate_selection(CropSelection(quad=((10, 10), (50, 10), (90, 10), (30, 10))), 100, 100)
    with pytest.raises(GeometryError, match="hors"):
        validate_selection(CropSelection(quad=((10, 10), (90, 10), (90, 90), (120, 90))), 100, 100)
    with pytest.raises(GeometryError, match="non finies"):
        validate_selection(CropSelection(quad=((10, 10), (math.inf, 10), (90, 90), (10, 90))), 100, 100)
    # Un ordre croisé en entrée est normalisé cycliquement (convention stable) :
    # le même carré est accepté quel que soit le point de départ.
    crossed_order = validate_selection(
        CropSelection(quad=((10, 10), (90, 90), (90, 10), (10, 90))), 100, 100)
    assert set(crossed_order.quad) == {(10.0, 10.0), (90.0, 10.0), (90.0, 90.0), (10.0, 90.0)}


def test_order_quad_reorders_arbitrary_start() -> None:
    square = ((90.0, 90.0), (10.0, 10.0), (10.0, 90.0), (90.0, 10.0))
    ordered = order_quad(square)
    assert ordered[0] == (10.0, 10.0)  # convention stable : départ haut gauche
    assert set(ordered) == set(square)


def test_rectify_axis_aligned_crop_and_rotation_project_back() -> None:
    prepared = _prepared()
    selection = CropSelection(rect=(50.0, 40.0, 250.0, 240.0), rotation=90)
    # L'orchestrateur applique selection.rotation ; l'API basse reçoit la rotation explicite.
    card = rectify_region(prepared, manual_region(prepared, selection), OcrConfig(),
                          rotation=selection.rotation)
    assert (card.width, card.height) == (200, 200)
    # Rotation 90° CCW : (0,0) carte -> ancienne coordonnée (199, 0) -> photo (249, 40).
    projected = mat_apply(card.card_to_photo, 0.0, 0.0)
    assert abs(projected[0] - 249) <= 0.51 and abs(projected[1] - 40) <= 0.51
    back = mat_apply(card.photo_to_card, *projected)
    assert abs(back[0]) <= 0.51 and abs(back[1]) <= 0.51


def test_rectify_perspective_quad_reprojects_corners_within_tolerance() -> None:
    prepared = _prepared(600, 400)
    region = manual_region(prepared, CropSelection(quad=((60.0, 40.0), (340.0, 30.0), (350.0, 260.0), (50.0, 270.0))))
    card = rectify_region(prepared, region, OcrConfig())
    # photo → carte : chaque coin de la photo rejoint son coin de destination.
    for corner, expected in zip(region.quad, ((0.0, 0.0), (card.width - 1.0, 0.0), (card.width - 1.0, card.height - 1.0), (0.0, card.height - 1.0))):
        projected = mat_apply(card.photo_to_card, *corner)
        assert math.dist(projected, expected) <= 0.51
    # carte → photo : la destination revient au coin d'origine (matrice inverse).
    for corner, destination in zip(region.quad, ((0.0, 0.0), (card.width - 1.0, 0.0), (card.width - 1.0, card.height - 1.0), (0.0, card.height - 1.0))):
        assert math.dist(mat_apply(card.card_to_photo, *destination), corner) <= 0.51
    # Un point central revient par la matrice inverse.
    center = (card.width / 2.0, card.height / 2.0)
    photo = mat_apply(card.card_to_photo, *center)
    assert math.dist(mat_apply(card.photo_to_card, *photo), center) <= 0.51


def test_rectify_respects_raster_caps() -> None:
    prepared = _prepared(3000, 3000)
    region = full_image_region(prepared)
    card = rectify_region(prepared, region, OcrConfig())
    assert max(card.width, card.height) <= 2000
    assert card.width * card.height <= 12_000_000


def test_quad_destination_size_uses_opposite_sides_and_caps() -> None:
    config = OcrConfig()
    quad = ((0.0, 0.0), (100.0, 0.0), (100.0, 200.0), (0.0, 200.0))
    assert quad_destination_size(quad, config) == (100, 200)
    huge = ((0.0, 0.0), (5000.0, 0.0), (5000.0, 5000.0), (0.0, 5000.0))
    width, height = quad_destination_size(huge, config)
    assert max(width, height) <= 2000
    with pytest.raises(GeometryError):
        quad_destination_size(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)), config)


def test_project_box_identity_and_translation() -> None:
    identity = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    quad, norm_box, bounding = project_box((10, 20, 30, 40), identity, 100, 100)
    assert quad == ((10.0, 20.0), (40.0, 20.0), (40.0, 60.0), (10.0, 60.0))
    assert norm_box == (0.1, 0.2, 0.4, 0.6)
    assert bounding == (10, 20, 40, 60)
    translate = ((1.0, 0.0, 5.0), (0.0, 1.0, 7.0), (0.0, 0.0, 1.0))
    _quad, _norm, translated = project_box((10, 20, 30, 40), translate, 100, 100)
    assert translated == (15, 27, 45, 67)


def test_polygon_iou_values() -> None:
    square = ((0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0))
    assert polygon_iou(square, square) == pytest.approx(1.0)
    assert polygon_iou(square, ((10.0, 10.0), (14.0, 10.0), (14.0, 14.0), (10.0, 14.0))) == 0.0
    assert polygon_iou(square, ((2.0, 0.0), (6.0, 0.0), (6.0, 4.0), (2.0, 4.0))) == pytest.approx(1 / 3)


def test_mat_invert_rejects_singular() -> None:
    with pytest.raises(GeometryError):
        mat_invert(((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)))


def test_auto_detect_blank_image_falls_back_with_diagnostic() -> None:
    prepared = _prepared()
    regions, diagnostics = auto_detect_regions(prepared, OcrConfig())
    assert regions == ()
    assert diagnostics  # indisponible OU aucun quadrilatère : un repli est proposé
    assert any("cadrage manuel" in item or "photo entière" in item for item in diagnostics)


def test_full_image_region_never_claims_a_card() -> None:
    prepared = _prepared()
    region = full_image_region(prepared)
    assert region.method == "full_image"
    assert region.kind == "unknown"
    assert "full_frame_no_localization" in region.motifs
