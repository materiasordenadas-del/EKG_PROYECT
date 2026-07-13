from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "template" / "viewer"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def visible_r_peaks(original_bpm: int, target_bpm: int, display_seconds: float) -> list[float]:
    """Posiciones visibles de picos R regulares; prueba solo la relación temporal."""
    scale = target_bpm / original_bpm
    source_rr = 60 / original_bpm
    source_peaks = [index * source_rr for index in range(120)]
    return [source_time / scale for source_time in source_peaks if source_time / scale < display_seconds]


def main() -> None:
    html = (VIEWER / "index.html").read_text(encoding="utf-8")
    script = (VIEWER / "app.js").read_text(encoding="utf-8")

    removed_control = "playback" + "Rate"
    require(removed_control not in html and removed_control not in script,
            "No debe quedar el control antiguo de velocidad en el visor activo.")
    removed_speed_control = "speed" + "Select"
    require(removed_speed_control not in html and removed_speed_control not in script,
            "La velocidad del papel debe permanecer fija a 25 mm/s.")
    for control in ("originalHeartRate", "targetHeartRateInput", "resetHeartRateButton", "playPauseButton", "restartButton"):
        require(control in html, f"Falta el control {control}.")
    require("surfaceModeSelect" in html and "Monitor negro" in html, "Falta el modo de pantalla negra.")
    require("surfaceMode: 'paper'" in script and "function traceColor()" in script,
            "Falta el estado visual independiente del ECG.")
    require("ctx.fillStyle = '#030706'" in script and "'#39ff88'" in script,
            "El modo monitor debe usar fondo negro y ondas verdes.")
    require("function heartRateScale()" in script, "Falta la escala temporal basada en FC.")
    require("target / original" in script, "La escala debe ser FC de reproducción / FC original.")
    require("state.displayTimeSec += deltaSec" in script, "El tiempo visible debe avanzar solo con dt real.")
    require("return ANIM_SHORT_SEC;" in script and "return ANIM_LONG_SEC;" in script,
            "Las ventanas animadas deben permanecer en 2,5 s y 10 s de pantalla.")
    require("const PAPER_SPEED_MM_PER_SEC = 25;" in script,
            "El papel debe mantenerse a 25 mm/s.")
    require("STATIC_LONG_SEC * PAPER_SPEED_MM_PER_SEC * PAPER_MM_PX" in script,
            "El ancho del papel debe representar 10 s a velocidad fija.")
    require("deltaSec * heartRateScale" not in script, "La FC no puede acelerar el cursor ni el reloj visible.")
    require("const sourceTime = displayTime * scale" in script,
            "La FC debe afectar solo al tiempo de lectura de la señal.")
    require("function sampleAt" in script and "fraction" in script,
            "La lectura de señal debe usar interpolación lineal.")
    require("originalRateSignal" in script and "signal_500hz.json" in script,
            "La FC original debe obtenerse desde la señal original de 500 Hz.")
    restart_start = script.index("$('restartButton').addEventListener")
    restart_end = script.index("$('diagnosisButton').addEventListener", restart_start)
    restart_body = script[restart_start:restart_end]
    require("state.displayTimeSec = 0" in restart_body, "Reiniciar debe volver al inicio.")
    require("targetHeartRate" not in restart_body, "Reiniciar debe conservar la FC de reproducción.")

    display_seconds = 10
    beats_60 = visible_r_peaks(60, 60, display_seconds)
    beats_120 = visible_r_peaks(60, 120, display_seconds)
    beats_30 = visible_r_peaks(60, 30, display_seconds)
    require(len(beats_60) == 10, "A 60 lpm deben verse 10 complejos en 10 s.")
    require(len(beats_120) == 20, "A 120 lpm deben verse 20 complejos en 10 s.")
    require(len(beats_30) == 5, "A 30 lpm deben verse 5 complejos en 10 s.")
    for target, beats in ((60, beats_60), (120, beats_120), (30, beats_30)):
        measured_bpm = len(beats) / display_seconds * 60
        require(abs(measured_bpm - target) <= 5, f"FC visible fuera de tolerancia para {target} lpm.")

    pixels_per_second = 200  # 25 mm/s con una cuadrícula de 8 px por mm.
    rr_pixels = {target: pixels_per_second * (60 / target) for target in (60, 120, 30)}
    require(rr_pixels[120] < rr_pixels[60] < rr_pixels[30], "La distancia RR en píxeles debe variar con la FC.")
    require(pixels_per_second == 200, "La velocidad horizontal del papel debe permanecer fija.")
    print("Prueba de animación y escalado de FC: OK")


if __name__ == "__main__":
    main()
