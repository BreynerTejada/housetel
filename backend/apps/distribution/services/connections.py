"""Connections to channels (plan C3 › API staff): create them with their mappings, change the mappings, pause,
resume, test, pull bookings, and configure the iCal/Channex integration from the wizard.

Mapping rules (validated by the API serializer, trusted here):
- BookSim, AirSim and Channex map categories (one mapping per category, each with its channel room id) and
  rate plans (`RateMapping`, with a markup; `room_type` set when the channel rate belongs to one room, as in
  Channex).
- iCal maps categories or single rooms (calendars); each mapping has its secret export URL and, optionally,
  the URL of the remote calendar to import. No rates.

After a mapping change the push channels get the whole horizon queued again, and the simulated OTA forgets the
rooms and rates it no longer has. Every change is audited (`distribution.*`).
"""

from django.db import IntegrityError, transaction

from apps.core import audit, integrations
from apps.core.errors import ConflictError, DomainError
from apps.core.runtime import simulations_enabled
from apps.distribution.errors import ChannelError
from apps.distribution.models import ChannelConnection, RateMapping, RoomMapping, SimOtaInventory, SyncLog
from apps.distribution.providers import CHANNEL_KINDS, SIM_CHANNELS, provider_for
from apps.distribution.services.logs import log
from apps.distribution.services.queue import PUSH_CHANNELS, enqueue_ari, full_sync

ICAL = ChannelConnection.Channel.ICAL
PULL_CHANNELS = (ChannelConnection.Channel.CHANNEX,)
SETTINGS_SCHEMA = {"import_all_events": bool}


class ChannelAlreadyConnected(ConflictError):
    code = "channel_already_connected"


def channel_label(code: str) -> str:
    return ChannelConnection.Channel(code).label


def delivery(channel_code: str) -> str:
    """How bookings arrive: `push` (the OTA sends them), `pull` (the PMS downloads them) or `ical`."""
    if channel_code == ICAL:
        return "ical"
    return "pull" if channel_code in PULL_CHANNELS else "push"


# --- integration (iCal / Channex) ---------------------------------------------------------------------------


def config_fields(kind: str) -> list[dict]:
    """The configuration fields of an integration kind (those of its real provider)."""
    provider = integrations.providers_for(kind).get("real")
    return list(getattr(provider, "CONFIG_FIELDS", []) or [])


def integration_info(prop, kind: str) -> dict:
    """Mode, state and non-secret configuration of an integration (secrets only by name); read-only."""
    from apps.core.models import IntegrationSetting

    setting = IntegrationSetting.objects.filter(property=prop, kind=kind).first()
    if setting is None:
        return {
            "kind": kind,
            "mode": integrations.default_mode(kind),
            "enabled": True,
            "config": {},
            "secrets": [],
        }
    public = {field["name"] for field in config_fields(kind) if not field.get("secret")}
    return {
        "kind": kind,
        "mode": setting.mode,
        "enabled": setting.enabled,
        "config": {key: value for key, value in (setting.config or {}).items() if key in public},
        "secrets": sorted(integrations.get_secrets(setting)),
    }


def configure_integration(prop, kind: str, *, mode=None, config=None, secrets=None, actor=None):
    """Set the mode, configuration and secrets of `channel_ical`/`channel_channex` (validated by the caller).
    Secrets are stored encrypted by `core.integrations.set_secrets` and never audited."""
    setting = integrations.get_setting(prop, kind)
    changes = {}
    fields = ["updated_at"]
    if mode and mode != setting.mode:
        changes["mode"] = [setting.mode, mode]
        setting.mode = mode
        fields.append("mode")
    before = dict(setting.config or {})
    if config and {**before, **config} != before:
        setting.config = {**before, **config}
        changes["config"] = [before, setting.config]
        fields.append("config")
    if len(fields) > 1:
        setting.save(update_fields=fields)
    if secrets:
        integrations.set_secrets(setting, secrets)
        changes["secrets"] = sorted(secrets)
    if changes:
        audit.record(
            action="distribution.integration_configured",
            target=setting,
            summary=f"Integración {kind} configurada desde Canales",
            actor=actor,
            property=prop,
            changes=changes,
        )
    return setting


# --- create / update / delete -------------------------------------------------------------------------------


def create_connection(prop, data: dict, *, actor=None) -> tuple[ChannelConnection, dict | None]:
    """Create a connection with its mappings (`data` = validated API payload). Push channels are queued, or
    synced at once with `full_sync=True` (returns the sync summary)."""
    channel = data["channel_code"]
    if channel in SIM_CHANNELS and not simulations_enabled():
        raise DomainError(
            "Los simuladores de OTAs no están disponibles en este entorno",
            code="not_supported",
            fields={"channel_code": ["Canal no disponible"]},
        )
    with transaction.atomic():
        if channel != ICAL and ChannelConnection.objects.filter(property=prop, channel_code=channel).exists():
            raise ChannelAlreadyConnected(f"El hotel ya tiene una conexión con {channel_label(channel)}")
        _configure_from(prop, channel, data, actor)
        try:
            with transaction.atomic():
                connection = ChannelConnection.objects.create(
                    property=prop,
                    channel_code=channel,
                    name=(data.get("name") or "").strip() or channel_label(channel),
                    settings=data.get("settings") or {},
                )
        except IntegrityError:
            raise ChannelAlreadyConnected(
                f"El hotel ya tiene una conexión con {channel_label(channel)}"
            ) from None
        _replace_room_mappings(connection, data.get("room_mappings") or [])
        _replace_rate_mappings(connection, data.get("rate_mappings") or [])
        audit.record(
            action="distribution.connection_created",
            target=connection,
            summary=f"Conexión con {connection.name} creada",
            actor=actor,
            property=prop,
            changes={
                "channel_code": channel,
                "rooms": [m.external_room_id or str(m.room_type_id) for m in connection.room_mappings.all()],
                "rates": [m.external_rate_id for m in connection.rate_mappings.all()],
            },
        )
    return connection, _after_mapping_change(connection, sync_now=bool(data.get("full_sync")), actor=actor)


def update_connection(connection, data: dict, *, actor=None) -> tuple[ChannelConnection, dict | None]:
    """Change name, settings, integration and/or mappings (a mappings list replaces the current one: items
    with `id` are kept and updated, the rest created, missing ones deleted)."""
    prop = connection.property
    changes = {}
    with transaction.atomic():
        connection = (
            ChannelConnection.objects.select_for_update().select_related("property").get(pk=connection.pk)
        )
        _configure_from(prop, connection.channel_code, data, actor)
        fields = ["updated_at"]
        if "name" in data and (data["name"] or "").strip() and data["name"].strip() != connection.name:
            changes["name"] = [connection.name, data["name"].strip()]
            connection.name = data["name"].strip()
            fields.append("name")
        if "settings" in data and (data["settings"] or {}) != (connection.settings or {}):
            changes["settings"] = [connection.settings, data["settings"] or {}]
            connection.settings = data["settings"] or {}
            fields.append("settings")
        if len(fields) > 1:
            connection.save(update_fields=fields)
        mappings_changed = False
        if "room_mappings" in data:
            _replace_room_mappings(connection, data["room_mappings"] or [])
            mappings_changed = True
            changes["rooms"] = [
                m.external_room_id or str(m.room_type_id) for m in connection.room_mappings.all()
            ]
        if "rate_mappings" in data:
            _replace_rate_mappings(connection, data["rate_mappings"] or [])
            mappings_changed = True
            changes["rates"] = [m.external_rate_id for m in connection.rate_mappings.all()]
        if changes:
            audit.record(
                action="distribution.connection_updated",
                target=connection,
                summary=f"Conexión con {connection.name} modificada",
                actor=actor,
                property=prop,
                changes=changes,
            )
    summary = None
    if mappings_changed:
        summary = _after_mapping_change(connection, sync_now=bool(data.get("full_sync")), actor=actor)
    return connection, summary


def delete_connection(connection, *, actor=None) -> None:
    """Remove the connection, its mappings, queue, log and simulated OTA; the reservations stay in the PMS."""
    with transaction.atomic():
        audit.record(
            action="distribution.connection_deleted",
            target=connection,
            summary=f"Conexión con {connection.name} eliminada",
            actor=actor,
            property=connection.property,
            changes={"channel_code": connection.channel_code, "name": connection.name},
        )
        connection.delete()


def _configure_from(prop, channel, data, actor) -> None:
    kind = CHANNEL_KINDS.get(channel)
    integration = data.get("integration") or {}
    if kind and (data.get("mode") or integration.get("config") or integration.get("secrets")):
        configure_integration(
            prop,
            kind,
            mode=data.get("mode"),
            config=integration.get("config") or None,
            secrets=integration.get("secrets") or None,
            actor=actor,
        )


def _replace_room_mappings(connection, items: list[dict]) -> None:
    keep = {str(item["id"]) for item in items if item.get("id")}
    existing = {str(mapping.pk): mapping for mapping in connection.room_mappings.all()}
    connection.room_mappings.exclude(pk__in=keep).delete()
    # free the external ids first so they can move between mappings
    RoomMapping.objects.filter(pk__in=keep).update(external_room_id="")
    try:
        with transaction.atomic():
            for item in items:
                mapping = existing.get(str(item.get("id"))) or RoomMapping(connection=connection)
                mapping.room_type_id = item["room_type"]
                mapping.room_id = item.get("room")
                mapping.external_room_id = item.get("external_room_id") or ""
                mapping.ical_import_url = item.get("ical_import_url") or ""
                mapping.save()
    except IntegrityError:
        raise DomainError(
            "Hay categorías o códigos del canal repetidos en el mapeo",
            code="validation_error",
            fields={"room_mappings": ["Hay categorías o códigos del canal repetidos"]},
        ) from None


def _replace_rate_mappings(connection, items: list[dict]) -> None:
    keep = {str(item["id"]) for item in items if item.get("id")}
    existing = {str(mapping.pk): mapping for mapping in connection.rate_mappings.all()}
    connection.rate_mappings.exclude(pk__in=keep).delete()
    try:
        with transaction.atomic():
            for item in items:
                mapping = existing.get(str(item.get("id"))) or RateMapping(connection=connection)
                mapping.rate_plan_id = item["rate_plan"]
                mapping.room_type_id = item.get("room_type")
                mapping.external_rate_id = item.get("external_rate_id") or ""
                mapping.markup_percent = item.get("markup_percent") or 0
                mapping.save()
    except IntegrityError:
        raise DomainError(
            "Hay planes repetidos en el mapeo de tarifas",
            code="validation_error",
            fields={"rate_mappings": ["Hay planes repetidos"]},
        ) from None


def _after_mapping_change(connection, *, sync_now: bool, actor) -> dict | None:
    """The simulated OTA forgets what is no longer mapped; push channels get everything queued (or synced)."""
    if (
        connection.channel_code in SIM_CHANNELS
        or connection.channel_code == ChannelConnection.Channel.CHANNEX
    ):
        rooms = [m.external_room_id for m in connection.room_mappings.all() if m.external_room_id]
        rates = [m.external_rate_id for m in connection.rate_mappings.all()]
        stale = SimOtaInventory.objects.filter(connection=connection).exclude(
            external_room_id__in=rooms, external_rate_id__in=[*rates, ""]
        )
        stale.delete()
    if connection.channel_code not in PUSH_CHANNELS or connection.status == ChannelConnection.Status.PAUSED:
        return None
    if sync_now:
        return full_sync(connection, actor=actor)
    enqueue_ari(connection.property, connection=connection)
    return None


# --- actions ------------------------------------------------------------------------------------------------


def pause_connection(connection, *, actor=None) -> ChannelConnection:
    """Stop sending ARI and pulling bookings (the queue is kept; resuming syncs everything)."""
    if connection.status != ChannelConnection.Status.PAUSED:
        connection.status = ChannelConnection.Status.PAUSED
        connection.save(update_fields=["status", "updated_at"])
        audit.record(
            action="distribution.connection_paused",
            target=connection,
            summary=f"Conexión con {connection.name} pausada",
            actor=actor,
            property=connection.property,
        )
    return connection


def resume_connection(connection, *, actor=None) -> tuple[ChannelConnection, dict | None]:
    """Back to active; push channels get a full sync at once (the channel may hold stale data)."""
    if connection.status == ChannelConnection.Status.PAUSED:
        connection.status = ChannelConnection.Status.ACTIVE
        connection.save(update_fields=["status", "updated_at"])
        audit.record(
            action="distribution.connection_resumed",
            target=connection,
            summary=f"Conexión con {connection.name} reanudada",
            actor=actor,
            property=connection.property,
        )
    summary = full_sync(connection, actor=actor) if connection.channel_code in PUSH_CHANNELS else None
    return connection, summary


def check_connection(connection) -> tuple[bool, str]:
    """Ask the provider whether the connection works; the answer is logged and, for iCal/Channex, stored as
    the integration status."""
    from django.utils import timezone

    try:
        ok, message = provider_for(connection).test_connection(connection)
    except ChannelError as exc:
        ok, message = False, exc.message
    log(
        connection,
        SyncLog.Direction.OUT,
        "test",
        SyncLog.Status.SUCCESS if ok else SyncLog.Status.ERROR,
        message,
    )
    kind = CHANNEL_KINDS.get(connection.channel_code)
    if kind:
        setting = integrations.get_setting(connection.property, kind)
        setting.status = "ok" if ok else "error"
        setting.status_message = (message or "")[:1000]
        setting.last_checked_at = timezone.now()
        setting.save(update_fields=["status", "status_message", "last_checked_at", "updated_at"])
    return ok, message


def pull_now(connection, *, actor=None) -> dict:
    """Import now what the channel has for us: remote calendars (iCal) or pending bookings (Channex)."""
    if connection.status == ChannelConnection.Status.PAUSED:
        raise ConflictError(
            "La conexión está pausada: reanúdala para descargar reservas", code="connection_paused"
        )
    if connection.channel_code == ICAL:
        from apps.distribution.services.ical import pull_ical

        return pull_ical(connection.property, connection=connection)
    if connection.channel_code in PULL_CHANNELS:
        from apps.distribution.services.pull import pull_bookings

        return pull_bookings(connection.property, connection=connection, actor=actor)
    raise DomainError(
        f"{connection.name} entrega sus reservas al momento: no hay nada que descargar", code="not_supported"
    )
