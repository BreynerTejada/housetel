import pytest

from apps.core import integrations
from apps.core.integrations import (
    BaseProvider,
    IntegrationNotAvailable,
    get_provider,
    get_secrets,
    get_setting,
    providers_for,
    register_provider,
    set_secrets,
)
from apps.core.models import Alert, IntegrationSetting
from apps.core.tests.factories import PropertyFactory

pytestmark = pytest.mark.django_db


class FakeSimulated(BaseProvider):
    label = "Simulado de prueba"


class FakeReal(BaseProvider):
    label = "Real de prueba"


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr(integrations, "_PROVIDERS", {})
    return integrations._PROVIDERS


class TestSecrets:
    def test_roundtrip_is_encrypted_at_rest(self, prop):
        setting = get_setting(prop, "payments")
        set_secrets(setting, {"private_key": "prv_test_SuperSecret123"})

        stored = (
            IntegrationSetting.objects.filter(pk=setting.pk).values_list("secrets_encrypted", flat=True).get()
        )
        assert stored and "SuperSecret123" not in stored
        assert get_secrets(IntegrationSetting.objects.get(pk=setting.pk)) == {
            "private_key": "prv_test_SuperSecret123"
        }

    def test_merges_with_existing_none_removes_and_blank_keeps(self, prop):
        setting = get_setting(prop, "payments")
        set_secrets(setting, {"a": "1", "b": "2", "c": "3"})
        set_secrets(setting, {"a": "", "b": None, "d": "4"})
        assert get_secrets(setting) == {"a": "1", "c": "3", "d": "4"}

    def test_missing_or_undecryptable_secrets_read_as_empty(self, prop):
        setting = get_setting(prop, "payments")
        assert get_secrets(setting) == {}
        setting.secrets_encrypted = "not-a-fernet-token"
        assert get_secrets(setting) == {}


class TestGetSetting:
    @pytest.mark.parametrize(
        ("kind", "mode"), [("payments", "simulated"), ("sire", "simulated"), ("email", "real")]
    )
    def test_creates_the_setting_enabled_with_the_default_mode(self, prop, kind, mode):
        setting = get_setting(prop, kind)
        assert (setting.property, setting.kind, setting.mode, setting.enabled) == (prop, kind, mode, True)

    def test_llm_defaults_to_real_only_when_a_gemini_key_exists(self, prop, organization, settings):
        settings.GEMINI_API_KEY = ""
        assert get_setting(prop, "llm").mode == "simulated"
        settings.GEMINI_API_KEY = "fake-key-for-tests"
        assert get_setting(PropertyFactory(organization=organization), "llm").mode == "real"

    def test_is_idempotent(self, prop):
        assert get_setting(prop, "payments").pk == get_setting(prop, "payments").pk
        assert IntegrationSetting.objects.filter(property=prop).count() == 1

    def test_platform_settings_have_no_property_and_are_unique(self):
        first, second = get_setting(None, "saas_billing"), get_setting(None, "saas_billing")
        assert first.pk == second.pk and first.property is None

    def test_unknown_kind_is_rejected(self, prop):
        with pytest.raises(ValueError):
            get_setting(prop, "fax")


class TestProviders:
    def test_returns_the_provider_registered_for_the_configured_mode(self, prop, registry):
        register_provider("sire", "simulated", FakeSimulated)
        register_provider("sire", "real", FakeReal)
        IntegrationSetting.objects.filter(pk=get_setting(prop, "sire").pk).update(mode="real")

        provider = get_provider(prop, "sire")

        assert isinstance(provider, FakeReal)
        assert provider.setting.kind == "sire"

    def test_provider_exposes_config_and_decrypted_secrets(self, prop, registry):
        register_provider("payments", "simulated", FakeSimulated)
        setting = get_setting(prop, "payments")
        setting.config = {"environment": "sandbox"}
        setting.save()
        set_secrets(setting, {"private_key": "prv"})

        provider = get_provider(prop, "payments")

        assert (provider.config, provider.secrets) == ({"environment": "sandbox"}, {"private_key": "prv"})

    def test_falls_back_to_simulated_and_raises_an_alert(self, prop, registry):
        register_provider("tra", "simulated", FakeSimulated)
        IntegrationSetting.objects.filter(pk=get_setting(prop, "tra").pk).update(mode="real")

        provider = get_provider(prop, "tra")

        assert isinstance(provider, FakeSimulated)
        alert = Alert.objects.get(property=prop, dedupe_key="integration:tra:fallback")
        assert (alert.severity, alert.resolved_at) == ("warning", None)

    def test_without_any_provider_raises_integration_not_available(self, prop, registry):
        with pytest.raises(IntegrationNotAvailable) as exc:
            get_provider(prop, "whatsapp")
        assert exc.value.code == "integration_not_available"

    def test_providers_for_lists_modes_of_one_kind(self, registry):
        register_provider("email", "real", FakeReal)
        register_provider("sire", "simulated", FakeSimulated)
        assert providers_for("email") == {"real": FakeReal}

    @pytest.mark.parametrize(("kind", "mode"), [("fax", "real"), ("email", "sandbox")])
    def test_register_provider_validates_kind_and_mode(self, registry, kind, mode):
        with pytest.raises(ValueError):
            register_provider(kind, mode, FakeReal)
