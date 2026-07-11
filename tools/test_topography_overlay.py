from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "template" / "viewer"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    html = (VIEWER / "index.html").read_text(encoding="utf-8")
    app = (VIEWER / "app.js").read_text(encoding="utf-8")
    overlay = (VIEWER / "topography-overlay.js").read_text(encoding="utf-8")
    medical = (VIEWER / "ecg-topography-medical-data.js").read_text(encoding="utf-8")

    for filename in ("ecg-topography-medical-data.js", "topography-overlay.js", "topography-overlay.css"):
        require((VIEWER / filename).exists(), f"Falta {filename}.")
    require('id="ecgLeadOverlay"' in html and 'id="ecgStage"' in html, "Falta el overlay externo al canvas.")
    require('ecg-topography-medical-data.js' in html and 'topography-overlay.js' in html, "Falta cargar la capa educativa.")
    require("ECG_TOPOGRAPHY_EDUCATION" in medical, "Faltan los datos médicos estructurados.")
    require("state.signal" not in overlay, "El overlay no puede modificar ni leer las señales.")
    require("getContext" not in overlay, "El overlay no debe dibujar dentro del canvas.")
    require("II_LONG" in overlay, "DII largo debe enmarcarse junto con DII corto.")
    require("additionalUnavailable" in overlay and "No disponibles en este registro de 12 derivaciones" in overlay,
            "Las derivaciones adicionales deben mostrarse sin fabricar trazados.")
    require("syncGeometry" in overlay and "getCurrentLeadLayout" in app, "Falta sincronización geométrica.")
    require("renderFrames" in app and "drawCalibration" in app, "Los marcos deben actualizarse después de cada dibujo.")
    print("Prueba de capa topográfica: OK")


if __name__ == "__main__":
    main()
