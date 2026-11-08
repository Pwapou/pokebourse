"""Géométrie OCR (T06.1) : orientation EXIF, cadrage manuel, homographie, localisation auto.

Le cadrage manuel et les transformations ne dépendent que de Pillow ; la
localisation automatique de quadrilatères (OpenCV headless + NumPy) est un
backend expérimental importé paresseusement. Toutes les coordonnées sont des
pixels de la photo orientée EXIF ; les matrices 3 × 3 relient carte et photo.
"""

from __future__ import annotations

import hashlib
import io
import math

from PIL import Image, ImageOps, UnidentifiedImageError

from app.identification.ocr_types import (
    GEOMETRY_VERSION,
    PREPARED_REF_METHOD,
    AutoLocateUnavailable,
    CardRegion,
    CropSelection,
    GeometryError,
    Matrix,
    OcrConfig,
    Point,
    PreparedImage,
    RectifiedCard,
    is_finite_point,
)

_ACCEPTED_FORMATS = {"PNG", "JPEG", "WEBP"}
_EXIF_ROTATION_CCW = {1: 0, 2: 0, 3: 180, 4: 0, 5: 0, 6: 90, 7: 0, 8: 270}
_ROTATIONS = (0, 90, 180, 270)
_BOUNDS_TOLERANCE_PX = 0.5
_MIN_QUAD_AREA_PX = 4.0


def prepare_image(content: bytes, config: OcrConfig | None = None) -> PreparedImage:
    """Décode une image bornée, applique l'orientation EXIF une seule fois et empreinte les pixels.

    L'empreinte porte la méthode et les dimensions ; elle ne prouve pas la conservation
    des octets d'origine (T04 conserve séparément les octets exacts archivés).
    """
    config = config or OcrConfig()
    if not content or len(content) > config.max_image_bytes:
        raise ValueError("Image vide ou supérieure à 8 Mo.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in _ACCEPTED_FORMATS:
                raise ValueError("Formats acceptés : JPEG, PNG et WebP.")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > config.max_input_pixels:
                raise ValueError("Image trop grande : maximum 12 millions de pixels.")
            exif_tag = int(image.getexif().get(0x0112, 1))
            image.seek(0)
            image.load()
            clean = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("Image illisible ou format non pris en charge.") from error
    output = io.BytesIO()
    clean.save(output, format="PNG")
    pixels = output.getvalue()
    digest = hashlib.sha256(pixels).hexdigest()
    return PreparedImage(
        image_ref=f"{PREPARED_REF_METHOD}:{digest}:{clean.width}x{clean.height}",
        width=clean.width,
        height=clean.height,
        exif_rotation_degrees=_EXIF_ROTATION_CCW.get(exif_tag, 0),
        pixels=pixels,
    )


def _identity() -> Matrix:
    return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def mat_mul(left: Matrix, right: Matrix) -> Matrix:
    """Compose deux matrices 3 × 3 (left ∘ right, right appliquée en premier)."""
    return tuple(
        tuple(sum(left[row][k] * right[k][col] for k in range(3)) for col in range(3))
        for row in range(3)
    )  # type: ignore[return-value]


def mat_apply(matrix: Matrix, x: float, y: float) -> Point:
    """Applique une homographie ; un dénominateur nul est une erreur de repère."""
    u = matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]
    v = matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]
    w = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]
    if not math.isfinite(u) or not math.isfinite(v) or abs(w) < 1e-12:
        raise GeometryError("Transformation géométrique dégénérée (dénominateur nul).")
    return (u / w, v / w)


def mat_invert(matrix: Matrix) -> Matrix:
    """Inverse une matrice 3 × 3 ; une matrice singulière est rejetée."""
    ((a, b, c), (d, e, f), (g, h, i)) = matrix
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if not math.isfinite(det) or abs(det) < 1e-12:
        raise GeometryError("Matrice singulière : transformation non inversible.")
    cofactors = (
        ((e * i - f * h), (c * h - b * i), (b * f - c * e)),
        ((f * g - d * i), (a * i - c * g), (c * d - a * f)),
        ((d * h - e * g), (b * g - a * h), (a * e - b * d)),
    )
    # cofactors[r][c] == C_{c,r} : cette matrice est déjà l'adjugate.
    return tuple(
        tuple(cofactors[row][col] / det for col in range(3))
        for row in range(3)
    )  # type: ignore[return-value]


def _translation(dx: float, dy: float) -> Matrix:
    return ((1.0, 0.0, dx), (0.0, 1.0, dy), (0.0, 0.0, 1.0))


def _rotation_new_to_old(degrees: int, src_width: int, src_height: int) -> tuple[int, int, Matrix]:
    """Matrice nouveau→ancien pour les rotations Pillow (90° = sens contraire des aiguilles)."""
    if degrees == 0:
        return src_width, src_height, _identity()
    if degrees == 90:
        return src_height, src_width, ((0.0, -1.0, src_width - 1.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    if degrees == 180:
        return src_width, src_height, ((-1.0, 0.0, src_width - 1.0), (0.0, -1.0, src_height - 1.0), (0.0, 0.0, 1.0))
    if degrees == 270:
        return src_height, src_width, ((0.0, 1.0, 0.0), (-1.0, 0.0, src_height - 1.0), (0.0, 0.0, 1.0))
    raise GeometryError("Rotation invalide : 0, 90, 180 ou 270 uniquement.")


def _rotate_png(pixels: bytes, degrees: int) -> tuple[bytes, int, int, Matrix]:
    """Tourne une image PNG et retourne la matrice associée nouveau→ancien."""
    with Image.open(io.BytesIO(pixels)) as image:
        source = image.convert("RGB")
    new_width, new_height, mapping = _rotation_new_to_old(degrees, source.width, source.height)
    rotated = source if degrees == 0 else source.transpose({
        90: Image.Transpose.ROTATE_90,
        180: Image.Transpose.ROTATE_180,
        270: Image.Transpose.ROTATE_270,
    }[degrees])
    output = io.BytesIO()
    rotated.save(output, format="PNG")
    return output.getvalue(), new_width, new_height, mapping


def order_quad(points: tuple[Point, Point, Point, Point]) -> tuple[Point, Point, Point, Point]:
    """Ordonne cycliquement autour du centroïde ; convention stable : départ « haut gauche ».

    Le point de départ définit une convention de lecture (haut gauche, haut droit,
    bas droit, bas gauche) ; il ne prouve pas le haut sémantique de la carte.
    """
    if not all(is_finite_point(point) for point in points):
        raise GeometryError("Quadrilatère invalide : coordonnées non finies.")
    for index, left in enumerate(points):
        for right in points[index + 1:]:
            if math.dist(left, right) < 1.0:
                raise GeometryError("Quadrilatère dégénéré : sommets non distincts.")
    center_x = sum(point[0] for point in points) / 4.0
    center_y = sum(point[1] for point in points) / 4.0
    ordered = tuple(sorted(points, key=lambda point: math.atan2(point[1] - center_y, point[0] - center_x)))
    start = min(range(4), key=lambda index: (ordered[index][0] + ordered[index][1], index))
    rotated = ordered[start:] + ordered[:start]
    if not _is_convex(rotated):
        raise GeometryError("Quadrilatère non convexe ou sommets croisés.")
    return rotated  # type: ignore[return-value]


def _cross(origin: Point, left: Point, right: Point) -> float:
    return (left[0] - origin[0]) * (right[1] - origin[1]) - (left[1] - origin[1]) * (right[0] - origin[0])


def _is_convex(quad: tuple[Point, Point, Point, Point]) -> bool:
    signs = []
    for index in range(4):
        value = _cross(quad[index], quad[(index + 1) % 4], quad[(index + 2) % 4])
        if abs(value) < 1e-9:
            return False  # colinéaire : dégénéré
        signs.append(value > 0)
    return all(signs) or not any(signs)


def polygon_area(polygon: tuple[Point, ...]) -> float:
    """Aire algébrique (shoelace) ; valeur absolue pour une aire géométrique."""
    total = 0.0
    for index, point in enumerate(polygon):
        following = polygon[(index + 1) % len(polygon)]
        total += point[0] * following[1] - following[0] * point[1]
    return total / 2.0


def _clip_edge(subject: list[Point], edge_start: Point, edge_end: Point, clip_ccw: bool) -> list[Point]:
    """Étape Sutherland–Hodgman : coupe un polygone par un bord orienté (clip convexe)."""
    def inside(point: Point) -> bool:
        cross = _cross(edge_start, edge_end, point)
        return cross >= 0 if clip_ccw else cross <= 0

    result: list[Point] = []
    for index, current in enumerate(subject):
        previous = subject[index - 1]
        current_inside = inside(current)
        if current_inside != inside(previous):
            # Intersection segment × bord (paramétrique).
            dx_s, dy_s = current[0] - previous[0], current[1] - previous[1]
            dx_e, dy_e = edge_end[0] - edge_start[0], edge_end[1] - edge_start[1]
            denom = dx_s * dy_e - dy_s * dx_e
            if abs(denom) > 1e-12:
                t = ((edge_start[0] - previous[0]) * dy_e - (edge_start[1] - previous[1]) * dx_e) / denom
                result.append((previous[0] + t * dx_s, previous[1] + t * dy_s))
        if current_inside:
            result.append(current)
    return result


def polygon_intersection_area(subject: tuple[Point, ...], clip: tuple[Point, ...]) -> float:
    """Aire d'intersection de deux polygones convexes (découpage Sutherland–Hodgman)."""
    output = list(subject)
    clip_ccw = polygon_area(clip) > 0
    for index in range(len(clip)):
        if not output:
            return 0.0
        output = _clip_edge(output, clip[index], clip[(index + 1) % len(clip)], clip_ccw)
    return abs(polygon_area(tuple(output))) if len(output) >= 3 else 0.0


def polygon_iou(left: tuple[Point, ...], right: tuple[Point, ...]) -> float:
    """IoU polygonale : déduplique les quadrilatères quasi identiques (seuil initial 0,9)."""
    area_left = abs(polygon_area(left))
    area_right = abs(polygon_area(right))
    if area_left <= 0 or area_right <= 0:
        return 0.0
    intersection = polygon_intersection_area(left, right)
    return intersection / (area_left + area_right - intersection)


def validate_selection(selection: CropSelection, width: int, height: int) -> CropSelection:
    """Valide le recadrage contre les dimensions réellement décodées (HTTP 400 sinon)."""
    if selection.rotation not in _ROTATIONS:
        raise GeometryError("Rotation invalide : 0, 90, 180 ou 270 uniquement.")
    if (selection.rect is None) == (selection.quad is None):
        raise GeometryError("Fournir exactement un rectangle ou un quadrilatère de cadrage.")
    if selection.rect is not None:
        x0, y0, x1, y1 = selection.rect
        values = selection.rect
        if not all(math.isfinite(value) for value in values):
            raise GeometryError("Cadrage invalide : coordonnées non finies.")
        if x1 - x0 < 1 or y1 - y0 < 1:
            raise GeometryError("Cadrage invalide : rectangle vide.")
        if x0 < -_BOUNDS_TOLERANCE_PX or y0 < -_BOUNDS_TOLERANCE_PX or x1 > width + _BOUNDS_TOLERANCE_PX or y1 > height + _BOUNDS_TOLERANCE_PX:
            raise GeometryError("Cadrage hors de la photo.")
        clamped = (max(0.0, x0), max(0.0, y0), min(float(width), x1), min(float(height), y1))
        if clamped[2] - clamped[0] < 1 or clamped[3] - clamped[1] < 1:
            raise GeometryError("Cadrage invalide : rectangle vide après bornage.")
        return CropSelection(rect=clamped, rotation=selection.rotation, contract_version=selection.contract_version)
    quad = order_quad(selection.quad)  # type: ignore[arg-type]
    for point in quad:
        if (point[0] < -_BOUNDS_TOLERANCE_PX or point[1] < -_BOUNDS_TOLERANCE_PX
                or point[0] > width + _BOUNDS_TOLERANCE_PX or point[1] > height + _BOUNDS_TOLERANCE_PX):
            raise GeometryError("Quadrilatère hors de la photo.")
    clamped_quad = tuple(
        (min(max(point[0], 0.0), float(width)), min(max(point[1], 0.0), float(height)))
        for point in quad
    )
    if abs(polygon_area(clamped_quad)) < _MIN_QUAD_AREA_PX:
        raise GeometryError("Quadrilatère dégénéré : aire nulle.")
    return CropSelection(quad=clamped_quad, rotation=selection.rotation, contract_version=selection.contract_version)


def full_image_region(prepared: PreparedImage) -> CardRegion:
    """Repère « photo entière » : ne prouve pas qu'un seul objet y figure."""
    quad = ((0.0, 0.0), (float(prepared.width), 0.0),
            (float(prepared.width), float(prepared.height)), (0.0, float(prepared.height)))
    return CardRegion(
        region_id="region-full", object_id="obj-full", kind="unknown", quad=quad,
        method="full_image", motifs=("full_frame_no_localization",),
    )


def manual_region(prepared: PreparedImage, selection: CropSelection, region_id: str = "region-manual-0") -> CardRegion:
    """Produit la région de cadrage manuel dans le repère de la photo orientée."""
    validated = validate_selection(selection, prepared.width, prepared.height)
    if validated.rect is not None:
        x0, y0, x1, y1 = validated.rect
        quad = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    else:
        quad = validated.quad  # type: ignore[assignment]
    return CardRegion(
        region_id=region_id, object_id="obj-manual-0", kind="card", quad=quad,
        method="manual", motifs=("manual_selection",),
    )


def _is_axis_aligned(quad: tuple[Point, Point, Point, Point]) -> tuple[float, float, float, float] | None:
    """Retourne le rectangle du quadrilatère axis-aligné, sinon None."""
    xs = sorted({round(point[0], 6) for point in quad})
    ys = sorted({round(point[1], 6) for point in quad})
    if len(xs) == 2 and len(ys) == 2:
        return xs[0], ys[0], xs[1], ys[1]
    return None


def quad_destination_size(quad: tuple[Point, Point, Point, Point], config: OcrConfig | None = None) -> tuple[int, int]:
    """Dimensions de destination : maximum des côtés opposés, plafonds raster respectés.

    Ne force jamais le ratio standard : une perspective n'est pas corrigée par un
    étirement arbitraire.
    """
    config = config or OcrConfig()
    width = max(math.dist(quad[0], quad[1]), math.dist(quad[3], quad[2]))
    height = max(math.dist(quad[1], quad[2]), math.dist(quad[0], quad[3]))
    if width < 2 or height < 2:
        raise GeometryError("Région trop petite pour être redressée.")
    scale = min(1.0,
                config.max_card_long_side / max(width, height),
                math.sqrt(config.max_derived_pixels / (width * height)))
    return max(1, round(width * scale)), max(1, round(height * scale))


def _homography_photo_to_card(quad: tuple[Point, Point, Point, Point], width: int, height: int) -> Matrix:
    """Résout l'homographie photo→carte par 4 correspondances (élimination gaussienne)."""
    destinations = ((0.0, 0.0), (width - 1.0, 0.0), (width - 1.0, height - 1.0), (0.0, height - 1.0))
    rows: list[list[float]] = []
    for (x, y), (u, v) in zip(quad, destinations, strict=True):
        rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y, u])
        rows.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y, v])
    # Élimination de Gauss avec pivot partiel sur les 8 inconnues h11..h32.
    for column in range(8):
        pivot = max(range(column, 8), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) < 1e-12:
            raise GeometryError("Homographie impossible : correspondences singulières.")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        for row in range(column + 1, 8):
            factor = rows[row][column] / rows[column][column]
            for col in range(column, 9):
                rows[row][col] -= factor * rows[column][col]
    solution = [0.0] * 8
    for row in range(7, -1, -1):
        solution[row] = (rows[row][8] - sum(rows[row][col] * solution[col] for col in range(row + 1, 8))) / rows[row][row]
    matrix: Matrix = (
        (solution[0], solution[1], solution[2]),
        (solution[3], solution[4], solution[5]),
        (solution[6], solution[7], 1.0),
    )
    # Vérifie la reprojection des quatre coins avant d'accepter la matrice.
    for (x, y), (u, v) in zip(quad, destinations, strict=True):
        projected = mat_apply(matrix, x, y)
        if math.dist(projected, (u, v)) > 0.51:
            raise GeometryError("Homographie incohérente : reprojection invalide.")
    return matrix


def rectify_region(prepared: PreparedImage, region: CardRegion, config: OcrConfig | None = None,
                   rotation: int = 0) -> RectifiedCard:
    """Produit la vue rectangulaire de la région et les matrices aller-retour photo.

    Le redressement projectif utilise Pillow (QUAD) ; OpenCV n'est requis que pour
    la localisation automatique. Une rotation supplémentaire explicite compose une
    nouvelle matrice avec l'homographie.
    """
    config = config or OcrConfig()
    if rotation not in _ROTATIONS:
        raise GeometryError("Rotation invalide : 0, 90, 180 ou 270 uniquement.")
    with Image.open(io.BytesIO(prepared.pixels)) as source_image:
        source = source_image.convert("RGB")
    quad = order_quad(region.quad)
    rect = _is_axis_aligned(quad)
    if rect is not None:
        x0, y0, x1, y1 = rect
        crop_box = (round(x0), round(y0), round(x1), round(y1))
        card_image = source.crop(crop_box)
        card_to_photo = _translation(crop_box[0], crop_box[1])
        photo_to_card = _translation(-crop_box[0], -crop_box[1])
        # Plafonds raster également sur le chemin rapide : réduction proportionnelle.
        destination_width, destination_height = quad_destination_size(quad, config)
        if (destination_width, destination_height) != (card_image.width, card_image.height):
            scale_x = card_image.width / destination_width
            scale_y = card_image.height / destination_height
            card_image = card_image.resize((destination_width, destination_height), Image.Resampling.LANCZOS)
            scale_to_original = ((scale_x, 0.0, 0.0), (0.0, scale_y, 0.0), (0.0, 0.0, 1.0))
            card_to_photo = mat_mul(card_to_photo, scale_to_original)
            photo_to_card = mat_mul(
                ((1 / scale_x, 0.0, 0.0), (0.0, 1 / scale_y, 0.0), (0.0, 0.0, 1.0)),
                photo_to_card,
            )
    else:
        width, height = quad_destination_size(quad, config)
        pillow_quad = (quad[0][0], quad[0][1], quad[3][0], quad[3][1],
                       quad[2][0], quad[2][1], quad[1][0], quad[1][1])  # UL, LL, LR, UR
        card_image = source.transform((width, height), Image.Transform.QUAD, pillow_quad, Image.Resampling.BICUBIC)
        photo_to_card = _homography_photo_to_card(quad, width, height)
        card_to_photo = mat_invert(photo_to_card)
    output = io.BytesIO()
    card_image.save(output, format="PNG")
    pixels = output.getvalue()
    if rotation:
        pixels, new_width, new_height, mapping = _rotate_png(pixels, rotation)
        card_to_photo = mat_mul(card_to_photo, mapping)
        photo_to_card = mat_mul(mat_invert(mapping), photo_to_card)
    else:
        new_width, new_height = card_image.width, card_image.height
    return RectifiedCard(
        region=region, width=new_width, height=new_height,
        card_to_photo=card_to_photo, photo_to_card=photo_to_card,
        extra_rotation=rotation, pixels=pixels,
    )


def project_quad(box: tuple[int, int, int, int], card_to_photo: Matrix) -> tuple[Point, Point, Point, Point]:
    """Reprojette les quatre coins d'une boîte (repère passe) vers la photo orientée."""
    left, top, width, height = box
    corners = ((left, top), (left + width, top), (left + width, top + height), (left, top + height))
    return tuple(mat_apply(card_to_photo, float(x), float(y)) for x, y in corners)


def project_box(box: tuple[int, int, int, int], card_to_photo: Matrix,
                frame_width: int, frame_height: int) -> tuple[tuple[Point, Point, Point, Point], tuple[float, float, float, float], tuple[int, int, int, int]]:
    """Reprojette une boîte de la passe vers la photo orientée.

    Retourne le quadrilatère projeté, la boîte normalisée (repère de la passe) et
    le rectangle englobant arrondi vers l'extérieur puis borné à la photo. Le
    rectangle englobant est une approximation explicitement étiquetée.
    """
    quad = project_quad(box, card_to_photo)
    left, top, width, height = box
    norm_box = (left / frame_width, top / frame_height,
                (left + width) / frame_width, (top + height) / frame_height)
    xs = [point[0] for point in quad]
    ys = [point[1] for point in quad]
    bounding = (
        max(0, int(math.floor(min(xs)))),
        max(0, int(math.floor(min(ys)))),
        min(frame_width, int(math.ceil(max(xs)))),
        min(frame_height, int(math.ceil(max(ys)))),
    )
    return quad, norm_box, bounding


def auto_detect_regions(prepared: PreparedImage, config: OcrConfig | None = None) -> tuple[tuple[CardRegion, ...], tuple[str, ...]]:
    """Localise au plus quatre quadrilatères plausibles (backend expérimental OpenCV).

    Sans OpenCV headless, retourne une région vide et un diagnostic de repli :
    le cadrage manuel ou la photo entière restent utilisables. Une localisation
    n'identifie jamais le contenu d'un contour (aucun attribut de carte ni lot
    n'est déduit de la seule géométrie).
    """
    config = config or OcrConfig()
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy  # type: ignore[import-not-found]
    except ImportError:
        return (), ("auto_unavailable: backend OpenCV headless absent ; cadrage manuel ou photo entière disponible.",)
    reduced = min(1.0, config.auto_detect_long_side / max(prepared.width, prepared.height))
    image = cv2.imdecode(numpy.frombuffer(prepared.pixels, dtype=numpy.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return (), ("auto_decode_failed: image indécodable par le backend automatique.",)
    if reduced < 1.0:
        image = cv2.resize(image, (max(1, round(prepared.width * reduced)), max(1, round(prepared.height * reduced))))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    area_floor = 0.01 * image.shape[0] * image.shape[1]
    candidates: list[tuple[float, tuple[Point, Point, Point, Point], str]] = []
    approx_budget = 200
    ranked = sorted(contours, key=cv2.contourArea, reverse=True)[:100]
    for contour in ranked:
        if approx_budget <= 0:
            break
        area = cv2.contourArea(contour)
        if area < area_floor:
            continue
        perimeter = cv2.arcLength(contour, True)
        quad: tuple[Point, Point, Point, Point] | None = None
        for epsilon_factor in (0.02, 0.04):
            approximated = cv2.approxPolyDP(contour, epsilon_factor * perimeter, True)
            approx_budget -= 1
            if len(approximated) == 4 and cv2.isContourConvex(approximated):
                points = tuple((float(item[0][0]), float(item[0][1])) for item in approximated)
                try:
                    quad = order_quad(points)  # type: ignore[arg-type]
                except GeometryError:
                    quad = None
                if quad is not None:
                    break
        if quad is None:
            continue
        sides = [math.dist(quad[index], quad[(index + 1) % 4]) for index in range(4)]
        if min(sides) < 30:
            continue  # côté trop petit dans l'image réduite
        if any(point[0] < 0 or point[1] < 0 or point[0] > image.shape[1] or point[1] > image.shape[0] for point in quad):
            continue  # sommet hors image
        score = _edge_support(edges, quad) * 2.0
        ratio = min(sides) / max(sides)
        score += 0.5 if 0.6 <= ratio <= 0.85 else 0.0  # indice souple, jamais une preuve
        candidates.append((score, quad, "portrait_ratio_hint" if 0.6 <= ratio <= 0.85 else "generic_quad"))
    candidates.sort(key=lambda item: (-item[0], item[1][0][0], item[1][0][1]))
    kept: list[tuple[float, tuple[Point, Point, Point, Point], str]] = []
    for candidate in candidates:
        if any(polygon_iou(candidate[1], existing[1]) >= 0.9 for existing in kept):
            continue  # quasi identique ; les contours imbriqués carte/boîtier sont préservés
        kept.append(candidate)
        if len(kept) >= config.max_regions:
            break
    regions: list[CardRegion] = []
    diagnostics: list[str] = []
    for index, (_score, quad, motif) in enumerate(kept):
        photo_quad = tuple((point[0] / reduced, point[1] / reduced) for point in quad)
        try:
            destination_width, _ = quad_destination_size(photo_quad, config)
        except GeometryError:
            destination_width = 0
        quality = "ok" if destination_width >= 150 else "insufficient"
        if quality == "insufficient":
            diagnostics.append(f"auto_region_small:{index}: largeur utile {destination_width}px < 150px ; qualité insuffisante.")
        regions.append(CardRegion(
            region_id=f"region-auto-{index}", object_id=f"obj-auto-{index}",
            kind="unknown", quad=photo_quad, method="auto", quality=quality,
            motifs=(motif, "auto_localization_uncertain"),
        ))
    if not regions:
        diagnostics.append("auto_no_quad: aucun quadrilatère plausible ; cadrage manuel ou photo entière disponible.")
    return tuple(regions), tuple(diagnostics)


def _edge_support(edges: object, quad: tuple[Point, Point, Point, Point]) -> float:
    """Fraction des points de périmètre recouvrant un pixel de contour (0..1)."""
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - auto_detect_regions garde déjà ce repli
        return 0.0
    edge_image = numpy.asarray(edges)
    dilated = cv2.dilate(edge_image, numpy.ones((3, 3), dtype=numpy.uint8))
    samples = 0
    hits = 0
    perimeter = sum(math.dist(quad[index], quad[(index + 1) % 4]) for index in range(4))
    steps = max(4, min(400, int(perimeter)))
    for index in range(4):
        start, end = quad[index], quad[(index + 1) % 4]
        for step in range(steps // 4):
            fraction = step / max(1, steps // 4)
            x = int(round(start[0] + (end[0] - start[0]) * fraction))
            y = int(round(start[1] + (end[1] - start[1]) * fraction))
            if 0 <= y < dilated.shape[0] and 0 <= x < dilated.shape[1]:
                samples += 1
                hits += int(dilated[y, x] > 0)
    return hits / samples if samples else 0.0


GEOMETRY_MODULE_VERSION = GEOMETRY_VERSION
