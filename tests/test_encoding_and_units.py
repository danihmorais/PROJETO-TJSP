import httpx

from app.legislation import Device, _decode_html_response
from app.render import parse_legal_units


def test_decode_old_planalto_latin1_without_replacement_character():
    html = (
        '<html><head><meta http-equiv="Content-Type" '
        'content="text/html; charset=iso-8859-1"></head><body>'
        '<p>Art. 5º Ficam sujeitos à lei brasileira.</p>'
        '<p>§ 1º Aplica-se a disposição.</p>'
        '<p>Inciso I - conteúdo com Constituição e administração pública.</p>'
        '</body></html>'
    ).encode("iso-8859-1")

    response = httpx.Response(
        200,
        headers={"content-type": "text/html"},
        content=html,
        request=httpx.Request("GET", "https://www.planalto.gov.br/")
    )

    decoded = _decode_html_response(response)
    assert "Ficam sujeitos à lei brasileira" in decoded
    assert "§ 1º" in decoded
    assert "Constituição" in decoded
    assert "�" not in decoded


def test_decode_valid_utf8_even_when_no_charset_is_declared():
    html = '<p>Art. 1º A Constituição é a lei fundamental.</p>'.encode("utf-8")
    response = httpx.Response(
        200,
        headers={"content-type": "text/html"},
        content=html,
        request=httpx.Request("GET", "https://www.planalto.gov.br/")
    )

    assert _decode_html_response(response) == '<p>Art. 1º A Constituição é a lei fundamental.</p>'


def test_parse_legal_units_preserves_reference_and_identifies_real_units():
    device = Device(
        "5",
        "Art. 5º Ficam sujeitos à lei brasileira, embora cometidos no estrangeiro:\n"
        "I - os crimes:\n"
        "a) contra a vida ou a liberdade do Presidente da República;\n"
        "b) contra o patrimônio público.\n"
        "II - outros crimes:\n"
        "a) previstos em lei.\n"
        "§ 1º Nos casos do n. I, aplica-se a regra."
    )

    units = parse_legal_units(device)

    assert [(kind, label) for kind, label, _ in units] == [
        ("caput", None),
        ("inciso", "I"),
        ("alinea", "a)"),
        ("alinea", "b)"),
        ("inciso", "II"),
        ("alinea", "a)"),
        ("paragraph", "§ 1º"),
    ]
    assert "n. I" in units[-1][2]
    assert all("n. I" not in label for _kind, label, _body in units if label)


def test_parse_inline_units_only_after_normative_separator():
    device = Device(
        "10",
        "Art. 10 O ato será praticado nos seguintes casos: I - primeiro; II - segundo; "
        "a) observação do segundo inciso; b) outra observação. Conforme o n. III, aplica-se a regra."
    )

    units = parse_legal_units(device)

    assert [(kind, label) for kind, label, _ in units] == [
        ("caput", None),
        ("inciso", "I"),
        ("inciso", "II"),
        ("alinea", "a)"),
        ("alinea", "b)"),
    ]
    assert "Conforme o n. III" in units[-1][2]
