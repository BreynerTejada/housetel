"""Code tables of the Colombian legal reports (defaults; each hotel can override them in its settings).

Sources and assumptions are documented in docs/integration-notes/C7-compliance.md ("SIRE" and "TRA"):

- `SIRE_COUNTRY_CODES`: ISO 3166 alpha-2 → the 3-digit country code of the DIAN table ("Códigos de países",
  e.g. Colombia 169, Estados Unidos 249, España 245), the numeric table the Colombian state uses in its flat
  files. Override per hotel with `ComplianceSettings.sire_country_codes` if Migración Colombia's drop-down
  shows
  a different value.
- `SIRE_DOCUMENT_TYPES`: `Guest.document_type` → SIRE document code (3 pasaporte, 5 cédula de extranjería are
  the documented ones; the rest are defaults to verify). Override with
  `ComplianceSettings.sire_document_codes`.
- `DIVIPOLA_CITIES`: city name (lower case, without accents) → DANE DIVIPOLA municipality code, used for the
  SIRE city of the hotel and for Factus `municipality_code` when the hotel did not set it.
- `TRA_*`: values sent to the MinCIT TRA service.
"""

import unicodedata

SIRE_DOCUMENT_TYPES = {
    "PA": "3",  # Pasaporte
    "CE": "5",  # Cédula de extranjería
    "DNI": "10",  # Documento de identidad extranjero
    "PEP": "47",  # Permiso especial de permanencia
    "PPT": "48",  # Permiso por protección temporal
    "OTHER": "10",
}

# ISO alpha-2 → DIAN 3-digit country code (tabla "Códigos de países" de la DIAN).
SIRE_COUNTRY_CODES = {
    "AF": "013", "AL": "017", "DE": "023", "AM": "026", "AW": "027", "BA": "029", "BF": "031", "AD": "037",
    "AO": "040", "AI": "041", "AG": "043", "SA": "053", "DZ": "059", "AR": "063", "AU": "069", "AT": "072",
    "AZ": "074", "BS": "077", "BH": "080", "BD": "081", "BB": "083", "BE": "087", "BZ": "088", "BM": "090",
    "BY": "091", "MM": "093", "BO": "097", "BW": "101", "BR": "105", "BN": "108", "BG": "111", "BI": "115",
    "BT": "119", "CV": "127", "KY": "137", "KH": "141", "CM": "145", "CA": "149", "VA": "159", "CC": "165",
    "CO": "169", "KM": "173", "CG": "177", "CK": "183", "KP": "187", "KR": "190", "CI": "193", "CR": "196",
    "HR": "198", "CU": "199", "TD": "203", "CL": "211", "CN": "215", "TW": "218", "CY": "221", "BJ": "229",
    "DK": "232", "DM": "235", "EC": "239", "EG": "240", "SV": "242", "ER": "243", "AE": "244", "ES": "245",
    "SK": "246", "SI": "247", "US": "249", "EE": "251", "ET": "253", "FO": "259", "PH": "267", "FI": "271",
    "FR": "275", "GA": "281", "GM": "285", "GE": "287", "GH": "289", "GI": "293", "GD": "297", "GR": "301",
    "GL": "305", "GP": "309", "GU": "313", "GT": "317", "GF": "325", "GN": "329", "GQ": "331", "GW": "334",
    "GY": "337", "HT": "341", "HN": "345", "HK": "351", "HU": "355", "IN": "361", "ID": "365", "IQ": "369",
    "IR": "372", "IE": "375", "IS": "379", "IL": "383", "IT": "386", "JM": "391", "JP": "399", "JO": "403",
    "KZ": "406", "KE": "410", "KI": "411", "KG": "412", "KW": "413", "LA": "420", "LS": "426", "LV": "429",
    "LB": "431", "LR": "434", "LY": "438", "LI": "440", "LT": "443", "LU": "445", "MO": "447", "MK": "448",
    "MG": "450", "MY": "455", "MW": "458", "MV": "461", "ML": "464", "MT": "467", "MP": "469", "MH": "472",
    "MA": "474", "MQ": "477", "MU": "485", "MR": "488", "MX": "493", "FM": "494", "MD": "496", "MN": "497",
    "MC": "498", "MS": "501", "MZ": "505", "NA": "507", "NR": "508", "CX": "511", "NP": "517", "NI": "521",
    "NE": "525", "NG": "528", "NU": "531", "NF": "535", "NO": "538", "NC": "542", "PG": "545", "NZ": "548",
    "VU": "551", "OM": "556", "NL": "573", "PK": "576", "PW": "578", "PA": "580", "PY": "586", "PE": "589",
    "PN": "593", "PF": "599", "PL": "603", "PT": "607", "PR": "611", "QA": "618", "GB": "628", "CF": "640",
    "CZ": "644", "DO": "647", "RE": "660", "ZW": "665", "RO": "670", "RW": "675", "RU": "676", "SB": "677",
    "EH": "685", "WS": "687", "AS": "690", "KN": "695", "SM": "697", "PM": "700", "VC": "705", "SH": "710",
    "LC": "715", "ST": "720", "SN": "728", "SC": "731", "SL": "735", "SG": "741", "SY": "744", "SO": "748",
    "LK": "750", "ZA": "756", "SD": "759", "SE": "764", "CH": "767", "SR": "770", "SZ": "773", "TJ": "774",
    "TH": "776", "TZ": "780", "DJ": "783", "IO": "787", "TL": "788", "TG": "800", "TK": "805", "TO": "810",
    "TT": "815", "TN": "820", "TC": "823", "TM": "825", "TR": "827", "TV": "828", "UA": "830", "UG": "833",
    "UY": "845", "UZ": "847", "VE": "850", "VN": "855", "VG": "863", "VI": "866", "FJ": "870", "WF": "875",
    "YE": "880", "RS": "885", "CD": "888", "ZM": "890", "PS": "897",
}  # fmt: skip

# City (lower case, no accents) → DANE DIVIPOLA code (capitals + frequent tourist municipalities).
DIVIPOLA_CITIES = {
    "bogota": "11001", "medellin": "05001", "cali": "76001", "barranquilla": "08001", "cartagena": "13001",
    "cartagena de indias": "13001", "cucuta": "54001", "bucaramanga": "68001", "pereira": "66001",
    "santa marta": "47001", "ibague": "73001", "manizales": "17001", "villavicencio": "50001",
    "pasto": "52001",
    "monteria": "23001", "neiva": "41001", "armenia": "63001", "popayan": "19001", "valledupar": "20001",
    "sincelejo": "70001", "tunja": "15001", "riohacha": "44001", "quibdo": "27001", "florencia": "18001",
    "yopal": "85001", "san andres": "88001", "leticia": "91001", "mocoa": "86001", "arauca": "81001",
    "inirida": "94001", "san jose del guaviare": "95001", "mitu": "97001", "puerto carreno": "99001",
    "envigado": "05266", "rionegro": "05615", "guatape": "05321", "santa fe de antioquia": "05042",
    "jardin": "05364", "salento": "63690", "filandia": "63272", "villa de leyva": "15407", "paipa": "15516",
    "barichara": "68079", "san gil": "68679", "mompox": "13468", "santa cruz de mompox": "13468",
    "providencia": "88564", "girardot": "25307", "melgar": "73449", "zipaquira": "25899", "chia": "25175",
    "palmira": "76520", "buenaventura": "76109", "santiago de tolu": "70820", "nuqui": "27495",
}  # fmt: skip

# Motivo de viaje (values of the guest portal, apps.guestportal) → TRA wording (MinCIT tourism statistics).
TRA_TRAVEL_REASONS = {
    "leisure": "Vacaciones, recreo y ocio",
    "business": "Negocios y motivos profesionales",
    "family": "Visitas a familiares y amigos",
    "education": "Educación y formación",
    "health": "Salud y atención médica",
    "religion": "Religión y peregrinaciones",
    "shopping": "Compras",
    "transit": "Tránsito",
    "other": "Otros motivos",
}

# Property.property_type → TRA "tipo de acomodación".
TRA_ACCOMMODATION_TYPES = {
    "hotel": "Hotel",
    "boutique": "Hotel",
    "hostel": "Hostal",
    "aparthotel": "Apartahotel",
    "glamping": "Glamping",
}

# Guest.document_type → TRA "tipo_identificacion".
TRA_DOCUMENT_TYPES = {
    "CC": "CC",
    "CE": "CE",
    "TI": "TI",
    "PA": "PA",
    "PEP": "PEP",
    "PPT": "PPT",
    "DNI": "DE",
    "NIT": "NIT",
    "OTHER": "DE",
}


def normalize_name(value: str) -> str:
    """Lower case, trimmed, without accents: the key of `DIVIPOLA_CITIES`."""
    text = unicodedata.normalize("NFKD", value or "")
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).lower().split())


def divipola_code(city: str) -> str:
    return DIVIPOLA_CITIES.get(normalize_name(city), "")


# ISO alpha-2 → Spanish country name (TRA "ciudad de residencia" when the guest has no city on file).
COUNTRY_NAMES_ES = {
    "AR": "Argentina", "AT": "Austria", "AU": "Australia", "BE": "Bélgica", "BO": "Bolivia", "BR": "Brasil",
    "CA": "Canadá", "CH": "Suiza", "CL": "Chile", "CN": "China", "CO": "Colombia", "CR": "Costa Rica",
    "CU": "Cuba",
    "DE": "Alemania", "DK": "Dinamarca", "DO": "República Dominicana", "EC": "Ecuador", "ES": "España",
    "FI": "Finlandia", "FR": "Francia", "GB": "Reino Unido", "GT": "Guatemala", "HN": "Honduras",
    "IE": "Irlanda",
    "IL": "Israel", "IN": "India", "IT": "Italia", "JP": "Japón", "KR": "Corea del Sur", "MX": "México",
    "NI": "Nicaragua", "NL": "Países Bajos", "NO": "Noruega", "NZ": "Nueva Zelanda", "PA": "Panamá",
    "PE": "Perú",
    "PL": "Polonia", "PR": "Puerto Rico", "PT": "Portugal", "PY": "Paraguay", "RU": "Rusia", "SE": "Suecia",
    "SV": "El Salvador", "TR": "Turquía", "US": "Estados Unidos", "UY": "Uruguay", "VE": "Venezuela",
    "ZA": "Sudáfrica",
}  # fmt: skip
