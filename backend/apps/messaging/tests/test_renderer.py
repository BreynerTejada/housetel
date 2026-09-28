"""The template renderer is our own (never Django/Jinja templates): `{{dotted.name}}` placeholders filled from
a flat dict of strings, a tiny markup (**bold**, [label](url)) and three outputs: plain text, WhatsApp text
and email HTML. Values are always data: they can neither run code nor inject markup."""

from apps.messaging.renderer import (
    missing_variables,
    placeholders,
    render_html,
    render_markup,
    render_plain,
    render_whatsapp,
    unknown_variables,
)

VARS = {
    "guest.first_name": "Ana",
    "reservation.code": "HT-7K2M9Q",
    "checkin_url": "https://app.test/g/tok/checkin",
    "payment_url": "https://app.test/pay/1",
}


class TestPlaceholders:
    def test_known_variables_are_replaced_with_or_without_spaces(self):
        text = render_plain("Hola {{guest.first_name}}, tu reserva {{ reservation.code }}.", VARS)
        assert text == "Hola Ana, tu reserva HT-7K2M9Q."

    def test_a_missing_variable_renders_empty_and_is_reported(self):
        template = "Hola {{guest.nickname}}! Código {{reservation.code}}"
        assert render_plain(template, VARS) == "Hola ! Código HT-7K2M9Q"
        assert missing_variables(template, VARS) == ["guest.nickname"]

    def test_an_empty_value_counts_as_missing(self):
        assert missing_variables("{{guest.first_name}}", {"guest.first_name": ""}) == ["guest.first_name"]

    def test_placeholders_are_listed_once_in_order(self):
        assert placeholders("{{b}} {{a}} {{ b }}") == ["b", "a"]

    def test_unknown_variables_are_the_ones_outside_the_catalog(self):
        catalog = {"guest.first_name", "reservation.code"}
        assert unknown_variables("{{guest.first_name}} {{guest.apodo}} {{x}} {{ guest.apodo }}", catalog) == [
            "guest.apodo",
            "x",
        ]

    def test_nothing_but_a_dotted_name_is_a_placeholder(self):
        # No expressions, indexing or dunder lookups: they are not variables of the catalog → empty.
        text = render_plain("{{ 1+1 }} {{guest.__class__}} {{__import__}}", VARS)
        assert text == "{{ 1+1 }}  "


class TestWhatsApp:
    def test_bold_uses_whatsapp_asterisks(self):
        assert render_whatsapp("**Importante:** llega a las 3", VARS) == "*Importante:* llega a las 3"

    def test_a_link_becomes_label_and_url(self):
        assert render_whatsapp("[Paga aquí]({{payment_url}})", VARS) == "Paga aquí: https://app.test/pay/1"

    def test_a_bare_url_link_is_not_repeated(self):
        assert render_whatsapp("[{{payment_url}}]({{payment_url}})", VARS) == "https://app.test/pay/1"


class TestMarkup:
    """What the inbox composer gets when a template is inserted: values in, markup kept (it is rendered for
    the     channel when the reply is sent)."""

    def test_values_are_filled_and_markup_is_kept(self):
        text = render_markup("**Hola** {{guest.first_name}}\n\n[Pagar]({{payment_url}})", VARS)
        assert text == "**Hola** Ana\n\n[Pagar](https://app.test/pay/1)"

    def test_unknown_values_render_empty(self):
        assert render_markup("Hola {{guest.nickname}}.", VARS) == "Hola ."


class TestPlainText:
    def test_bold_markers_are_dropped(self):
        assert render_plain("**Hola** {{guest.first_name}}", VARS) == "Hola Ana"

    def test_links_keep_their_url(self):
        assert render_plain("[Check-in]({{checkin_url}})", VARS) == "Check-in: https://app.test/g/tok/checkin"


class TestEmailHtml:
    def test_paragraphs_and_line_breaks(self):
        assert render_html("Hola {{guest.first_name}}\nBienvenida\n\nChao", VARS) == (
            "<p>Hola Ana<br>Bienvenida</p>\n<p>Chao</p>"
        )

    def test_values_are_escaped(self):
        html = render_html(
            "Hola {{guest.first_name}}", {"guest.first_name": '<img src=x onerror="alert(1)">'}
        )
        assert "<img" not in html
        assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in html

    def test_html_typed_in_the_template_is_shown_as_text(self):
        assert render_html("<b>Hola</b>", VARS) == "<p>&lt;b&gt;Hola&lt;/b&gt;</p>"

    def test_a_value_cannot_inject_markup(self):
        html = render_html(
            "Hola {{guest.first_name}}", {"guest.first_name": "[gana](https://evil.test) **x**"}
        )
        assert "<a" not in html and "<strong>" not in html
        assert "[gana](https://evil.test) **x**" in html

    def test_bold_and_inline_links(self):
        html = render_html("**Ojo:** mira [tu reserva]({{checkin_url}}) hoy", VARS)
        assert html == (
            '<p><strong>Ojo:</strong> mira <a href="https://app.test/g/tok/checkin" '
            'style="color:#B4583B;text-decoration:underline">tu reserva</a> hoy</p>'
        )

    def test_a_link_alone_in_its_paragraph_is_a_button(self):
        html = render_html("Listo.\n\n[Hacer check-in]({{checkin_url}})", VARS, accent="#4E6C88")
        assert '<a href="https://app.test/g/tok/checkin"' in html
        assert "background:#4E6C88" in html and ">Hacer check-in</a>" in html

    def test_only_web_and_mail_links_become_anchors(self):
        html = render_html("[Abrir]({{payment_url}})", {"payment_url": "javascript:alert(1)"})
        assert "<a" not in html and "javascript:alert(1)" in html

    def test_an_invalid_accent_falls_back_to_the_brand_color(self):
        html = render_html("[Abrir]({{payment_url}})", VARS, accent="red;background:url(x)")
        assert "url(x)" not in html and "background:#B4583B" in html
