from app.ui.common import plain


def test_plain_shows_typed_text_as_typed():
    assert "![" not in plain("![](https://example.com/x.png)") and "](" not in plain("[a](https://example.com)")
    assert plain("Tucán pico iris") == "Tucán pico iris"
    assert plain(":red[hola]") == "\\:red\\[hola\\]"
