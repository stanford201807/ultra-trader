from pathlib import Path


def test_dashboard_serves_static_assets() -> None:
    app_py = Path("dashboard/app.py").read_text(encoding="utf-8")
    assert 'app.mount("/static"' in app_py


def test_dashboard_font_scale_controls_exist() -> None:
    template = Path("dashboard/static/templates/app-dom.part1.html").read_text(
        encoding="utf-8"
    )
    assert "font-scale-controls" in template
    assert "increaseFont" in template
    assert "decreaseFont" in template
    assert ':style="{ \'--uifs\': uiFontScale }"' not in template

    css = Path("dashboard/static/styles.css").read_text(encoding="utf-8")
    assert "--uifs" in css

    font_scale = Path("dashboard/static/app/modules/fontScale.js").read_text(
        encoding="utf-8"
    )
    assert "applyScaleToApp" in font_scale
    assert 'app.style.setProperty("--uifs"' in font_scale
    assert "const MAX_SCALE = 2.0;" in font_scale
    assert "const MIN_SCALE = 0.85;" in font_scale
