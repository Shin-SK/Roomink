import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import Store, StorePhoneNumber


SID_PATTERNS = {
    "TWILIO_ACCOUNT_SID": r"AC[0-9a-fA-F]{32}",
    "TWILIO_BYOC_TRUNK_SID": r"BY[0-9a-fA-F]{32}",
    "TWILIO_BYOC_TERMINATION_DOMAIN_SID": r"SD[0-9a-fA-F]{32}",
    "TWILIO_SIP_REGISTRATION_DOMAIN_SID": r"SD[0-9a-fA-F]{32}",
    "TWILIO_BYOC_CREDENTIAL_LIST_SID": r"CL[0-9a-fA-F]{32}",
    "TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID": r"AL[0-9a-fA-F]{32}",
    "TWILIO_SIP_CREDENTIAL_LIST_SID": r"CL[0-9a-fA-F]{32}",
}


class Command(BaseCommand):
    help = "クラコールBYOC→Twilio→Roomink→受付SIP端末とSMSの開通準備を読み取り検査する"

    def add_arguments(self, parser):
        parser.add_argument("--store-id", type=int)
        parser.add_argument(
            "--live",
            action="store_true",
            help="Twilio APIへ読み取り接続し、BYOC TrunkとSIP Domainも検査する",
        )

    def handle(self, *args, **options):
        failures = []
        expected_voice_url = (
            f"{settings.TWILIO_WEBHOOK_PUBLIC_BASE_URL}/api/webhook/twilio/voice/"
        )
        expected_status_url = (
            f"{settings.TWILIO_WEBHOOK_PUBLIC_BASE_URL}/api/webhook/twilio/status/"
        )

        self._check_sid("TWILIO_ACCOUNT_SID", settings.TWILIO_ACCOUNT_SID, failures)
        self._check_present("TWILIO_AUTH_TOKEN", settings.TWILIO_AUTH_TOKEN, failures)
        if not re.fullmatch(r"\+[1-9]\d{7,14}", settings.TWILIO_FROM_PHONE or ""):
            failures.append("TWILIO_FROM_PHONE is missing or malformed")
        self._check_sid("TWILIO_SIP_CREDENTIAL_LIST_SID", settings.TWILIO_SIP_CREDENTIAL_LIST_SID, failures)
        self._check_sid(
            "TWILIO_SIP_REGISTRATION_DOMAIN_SID",
            settings.TWILIO_SIP_REGISTRATION_DOMAIN_SID,
            failures,
        )
        self._check_sid("TWILIO_BYOC_TRUNK_SID", settings.TWILIO_BYOC_TRUNK_SID, failures)
        self._check_sid(
            "TWILIO_BYOC_TERMINATION_DOMAIN_SID",
            settings.TWILIO_BYOC_TERMINATION_DOMAIN_SID,
            failures,
        )
        byoc_credential_sid = settings.TWILIO_BYOC_CREDENTIAL_LIST_SID
        byoc_ip_acl_sid = settings.TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID
        if not byoc_ip_acl_sid:
            failures.append("BYOC carrier IP ACL SID is missing")
        if byoc_credential_sid:
            self._check_sid(
                "TWILIO_BYOC_CREDENTIAL_LIST_SID",
                byoc_credential_sid,
                failures,
            )
            failures.append(
                "submitted carrier connection must use IP ACL without call credentials"
            )
        if byoc_ip_acl_sid:
            self._check_sid(
                "TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID",
                byoc_ip_acl_sid,
                failures,
            )
        if not settings.TWILIO_WEBHOOK_PUBLIC_BASE_URL.startswith("https://"):
            failures.append("TWILIO_WEBHOOK_PUBLIC_BASE_URL must be an https URL")
        if settings.TWILIO_WEBHOOK_ALLOW_UNSIGNED:
            failures.append("TWILIO_WEBHOOK_ALLOW_UNSIGNED must be disabled")

        stores = Store.objects.all()
        if options.get("store_id"):
            stores = stores.filter(pk=options["store_id"])
        stores = stores.filter(phone_numbers__is_active=True).distinct()
        if not stores.exists():
            failures.append("active StorePhoneNumber is missing")
        checked_stores = list(stores)
        for store in checked_stores:
            self._check_store(store, failures)

        if options["live"] and not failures:
            self._check_twilio_live(
                expected_voice_url,
                expected_status_url,
                {store.sip_domain for store in checked_stores},
                failures,
            )

        if failures:
            for message in failures:
                self.stderr.write(self.style.ERROR(f"NG: {message}"))
            raise CommandError(f"voice readiness failed ({len(failures)} issue(s))")

        mode = "live" if options["live"] else "local"
        self.stdout.write(self.style.SUCCESS(f"VOICE READY ({mode})"))

    def _check_present(self, name, value, failures):
        if not value:
            failures.append(f"{name} is missing")

    def _check_sid(self, name, value, failures):
        pattern = SID_PATTERNS[name]
        if not re.fullmatch(pattern, value or ""):
            failures.append(f"{name} is missing or malformed")

    def _check_store(self, store, failures):
        numbers = list(
            StorePhoneNumber.objects.filter(store=store, is_active=True)
            .values_list("phone", flat=True)
        )
        if any(not re.fullmatch(r"\d{10,15}", number or "") for number in numbers):
            failures.append(f"store {store.pk}: active phone must contain 10-15 digits only")
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.sip\.twilio\.com", store.sip_domain or ""):
            failures.append(f"store {store.pk}: Twilio reception SIP Domain is missing")
        if not store.sip_reception_devices.filter(
            is_active=True,
            provisioned_at__isnull=False,
        ).exists():
            failures.append(f"store {store.pk}: no active provisioned reception device")

    def _check_twilio_live(
        self,
        expected_voice_url,
        expected_status_url,
        expected_sip_domains,
        failures,
    ):
        from twilio.rest import Client

        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            trunk = client.voice.v1.byoc_trunks(
                settings.TWILIO_BYOC_TRUNK_SID
            ).fetch()
            termination_domain = client.api.v2010.account.sip.domains(
                settings.TWILIO_BYOC_TERMINATION_DOMAIN_SID
            ).fetch()
            registration_domain = client.api.v2010.account.sip.domains(
                settings.TWILIO_SIP_REGISTRATION_DOMAIN_SID
            ).fetch()
            sms_numbers = client.incoming_phone_numbers.list(
                phone_number=settings.TWILIO_FROM_PHONE,
                limit=1,
            )
        except Exception as exc:
            failures.append(f"Twilio read-only API check failed: {exc.__class__.__name__}")
            return

        if trunk.voice_url != expected_voice_url or str(trunk.voice_method).upper() != "POST":
            failures.append("BYOC Trunk voice webhook is not the Roomink POST endpoint")
        if trunk.status_callback_url != expected_status_url:
            failures.append("BYOC Trunk status callback is not the Roomink endpoint")
        if str(trunk.status_callback_method).upper() != "POST":
            failures.append("BYOC Trunk status callback method is not POST")
        if termination_domain.byoc_trunk_sid != settings.TWILIO_BYOC_TRUNK_SID:
            failures.append("termination SIP Domain is not linked to the configured BYOC Trunk")
        if termination_domain.domain_name != settings.TWILIO_BYOC_TERMINATION_DOMAIN_NAME:
            failures.append(
                "termination SIP Domain does not match the submitted Clocall SIP Domain"
            )
        auth_types = {
            value.strip()
            for value in str(termination_domain.auth_type or "").split(",")
            if value.strip()
        }
        if not auth_types.intersection({"CREDENTIAL_LIST", "IP_ACL"}):
            failures.append("termination SIP Domain has no supported authentication")
        call_credential_mappings = termination_domain.credential_list_mappings.list(limit=50)
        if call_credential_mappings or "CREDENTIAL_LIST" in auth_types:
            failures.append(
                "submitted carrier connection must not require call credentials"
            )
        if settings.TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID:
            mappings = termination_domain.ip_access_control_list_mappings.list(limit=50)
            if settings.TWILIO_BYOC_IP_ACCESS_CONTROL_LIST_SID not in {
                getattr(item, "ip_access_control_list_sid", None) or item.sid
                for item in mappings
            }:
                failures.append("BYOC IP ACL is not mapped to the termination domain")
        if termination_domain.secure:
            failures.append(
                "carrier SIP Domain must accept the submitted UDP/5060 transport"
            )
        if termination_domain.domain_name in expected_sip_domains:
            failures.append(
                "carrier SIP Domain and reception-device registration Domain must be separate"
            )

        if registration_domain.domain_name not in expected_sip_domains:
            failures.append(
                "reception-device SIP Domain does not match the store configuration"
            )
        if registration_domain.domain_name == termination_domain.domain_name:
            failures.append(
                "reception-device SIP Domain must not reuse the carrier SIP Domain"
            )
        if registration_domain.byoc_trunk_sid:
            failures.append(
                "reception-device SIP Domain must not be linked to the carrier BYOC Trunk"
            )
        if not registration_domain.sip_registration:
            failures.append("reception-device SIP registration is disabled")
        if registration_domain.secure:
            failures.append(
                "reception-device SIP Domain requires unsupported mandatory secure media"
            )
        registration_mappings = registration_domain.auth.registrations.credential_list_mappings.list(limit=50)
        if settings.TWILIO_SIP_CREDENTIAL_LIST_SID not in {
            getattr(item, "credential_list_sid", None) or item.sid
            for item in registration_mappings
        }:
            failures.append(
                "reception device Credential List is not mapped to SIP registration"
            )
        device_call_mappings = registration_domain.credential_list_mappings.list(limit=50)
        if settings.TWILIO_SIP_CREDENTIAL_LIST_SID not in {
            getattr(item, "credential_list_sid", None) or item.sid
            for item in device_call_mappings
        }:
            failures.append(
                "reception device Credential List is not mapped to SIP calls"
            )
        if not sms_numbers or not bool((sms_numbers[0].capabilities or {}).get("sms")):
            failures.append("TWILIO_FROM_PHONE is not an SMS-capable Twilio number")
