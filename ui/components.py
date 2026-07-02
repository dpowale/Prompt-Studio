import base64
import streamlit.components.v1 as components

from ui.theme import THEME_PRESETS

def copy_button_html(text: str, label: str, key: str, theme_mode: str = "Light") -> None:
    """Render a one-click clipboard copy button for a block of text."""
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    theme = THEME_PRESETS.get(theme_mode, THEME_PRESETS["Light"])
    components.html(
        f"""
        <div style="display:flex; justify-content:flex-start; margin:0.35rem 0 0.85rem 0;">
            <button
                onclick="navigator.clipboard.writeText(atob('{encoded}').replace(/\\n/g, '\\n')).then(() => {{
                    const el = document.getElementById('status-{key}');
                    if (el) {{ el.innerText = 'Copied'; setTimeout(() => {{ el.innerText = ''; }}, 1600); }}
                }})"
                style="
                    background: linear-gradient(135deg, {theme['accent']}, {theme['accent_2']});
                    color: #ffffff;
                    border: none;
                    border-radius: 999px;
                    padding: 0.62rem 1rem;
                    cursor: pointer;
                    font-family: 'Segoe UI', 'Aptos', 'Helvetica Neue', sans-serif;
                    font-size: 0.9rem;
                    font-weight: 600;
                    box-shadow: 0 12px 22px rgba(37, 99, 235, 0.24);
                ">
                {label}
            </button>
            <span id="status-{key}" style="align-self:center; margin-left:0.75rem; color:{theme['success']}; font-size:0.85rem; font-family: 'Segoe UI', 'Aptos', 'Helvetica Neue', sans-serif; font-weight: 700;"></span>
        </div>
        """,
        height=60,
    )
