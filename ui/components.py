import base64
import streamlit.components.v1 as components

def copy_button_html(text: str, label: str, key: str) -> None:
    """Render a one-click clipboard copy button for a block of text."""
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    components.html(
        f"""
        <div style="display:flex; justify-content:flex-start; margin:0.35rem 0 0.85rem 0;">
            <button
                onclick="navigator.clipboard.writeText(atob('{encoded}').replace(/\\n/g, '\\n')).then(() => {{
                    const el = document.getElementById('status-{key}');
                    if (el) {{ el.innerText = 'Copied'; setTimeout(() => {{ el.innerText = ''; }}, 1600); }}
                }})"
                style="
                    background: #3c63ff;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 0.55rem 0.95rem;
                    cursor: pointer;
                    font-family: sans-serif;
                    font-size: 0.9rem;
                    box-shadow: 0 4px 10px rgba(0,0,0,0.15);
                ">
                {label}
            </button>
            <span id="status-{key}" style="align-self:center; margin-left:0.75rem; color:#4bb37d; font-size:0.85rem; font-family: sans-serif; font-weight: bold;"></span>
        </div>
        """,
        height=60,
    )
