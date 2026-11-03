"""Fixed source-family identities; layout alone does not prove hook support."""

DECOMPOSED_GATEWAY_TARGETS = (
    "gateway/run_turn.py", "gateway/run_turn_persistence.py", "gateway/run_turn_prepare.py", "gateway/run_turn_hygiene.py", "gateway/run_turn_progress.py", "gateway/run_turn_runner.py", "gateway/run_inbound.py",
    "gateway/run_busy.py", "gateway/run_startup.py", "gateway/run_notifications.py",
)
DECOMPOSED_TARGETS = (*DECOMPOSED_GATEWAY_TARGETS,
                      "cron/scheduler_delivery.py", "gateway/platforms/base.py")


DECOMPOSED_MANIFEST_VERSION = 4
DECOMPOSED_LAYOUT = "gateway-decomposed-v1"
MANIFEST_NAME = ".hermes_feishu_card_manifest"
BACKUP_SUFFIX = ".hermes_feishu_card.bak"
DECOMPOSED_SOURCE_TARGETS = (
    "gateway/run.py", *DECOMPOSED_GATEWAY_TARGETS,
    "cron/scheduler.py", "cron/scheduler_delivery.py", "gateway/platforms/base.py",
)

# LOCAL PATCH (PATCH-039): read-only references for the inherited completion
# ownership proof. Hermes 0.22.6 (6cfdb53323) moved background-turn execution
# out of gateway/run_turn.py into gateway/run_background.py and put
# GatewayBackgroundMixin first in GatewayTurnMixin's bases, so proving the
# earlier base cannot shadow the persistence mixin needs that module's source.
# It is read, parsed and never rendered: not a patch target, not a manifest
# entry, not a backup, never written.
COMPLETION_REFERENCE_SOURCES = ("gateway/run_background.py",)
