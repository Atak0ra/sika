"""
tests/test_register_school.py
================================
Tests pour RegisterSchoolUseCase et ActivateSchoolRegistrationUseCase.
"""
import uuid
import pytest

from economat.application.dto_identity import ActivateSchoolCommand, RegisterSchoolCommand
from economat.application.ports.email_sender import EmailSender, EmailSendError
from economat.application.use_cases.activate_school_registration import ActivateSchoolRegistrationUseCase
from economat.application.use_cases.register_school import RegisterSchoolUseCase
from economat.composition import get_registration_repo, get_create_school_use_case
from economat.infrastructure.persistence.identity_repositories import DjangoUserRepository


# ── Fake EmailSender (aucun appel réseau) ─────────────────────────────────────

class FakeEmailSender(EmailSender):
    def __init__(self, fail=False):
        self.sent = []
        self._fail = fail

    def send(self, *, to, subject, html):
        if self._fail:
            raise EmailSendError("Fake failure")
        self.sent.append({"to": to, "subject": subject})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _register_cmd(**kwargs):
    defaults = dict(
        school_name="École des Palmiers",
        city="Dakar",
        country_code="SN",
        manager_first_name="Kofi",
        manager_last_name="Mensah",
        manager_email="kofi.mensah@example.com",
        payment_methods=("ESPECES",),
    )
    defaults.update(kwargs)
    return RegisterSchoolCommand(**defaults)


@pytest.fixture
def sn_country(make_country):
    return make_country("SN")


@pytest.fixture
def register_uc():
    return RegisterSchoolUseCase(registration_repo=get_registration_repo())


@pytest.fixture
def fake_email():
    return FakeEmailSender()


@pytest.fixture
def activate_uc(fake_email):
    return ActivateSchoolRegistrationUseCase(
        registration_repo=get_registration_repo(),
        user_repo=DjangoUserRepository(),
        create_school_uc=get_create_school_use_case(),
        email_sender=fake_email,
    )


# ── Tests RegisterSchoolUseCase ───────────────────────────────────────────────

@pytest.mark.django_db
def test_register_creates_pending(sn_country, register_uc):
    result = register_uc.execute(_register_cmd())
    assert result.success
    reg = get_registration_repo().get(result.registration_id)
    assert reg["status"] == "PENDING"
    assert reg["school_name"] == "École des Palmiers"


@pytest.mark.django_db
def test_register_rejects_duplicate_email(sn_country, register_uc):
    register_uc.execute(_register_cmd())
    result = register_uc.execute(_register_cmd())
    assert not result.success
    assert "déjà en attente" in result.error_message


@pytest.mark.django_db
def test_register_idempotent_client_uuid(sn_country, register_uc):
    cuuid = str(uuid.uuid4())
    r1 = register_uc.execute(_register_cmd(client_uuid=cuuid))
    r2 = register_uc.execute(_register_cmd(client_uuid=cuuid, manager_email="autre@example.com"))
    assert r1.registration_id == r2.registration_id
    assert r2.already_exists is True


@pytest.mark.django_db
def test_register_mobile_money_requires_operator(sn_country, register_uc):
    result = register_uc.execute(_register_cmd(
        payment_methods=("MOBILE_MONEY",), mobile_operator="", mobile_number="",
    ))
    assert not result.success
    assert "opérateur" in result.error_message.lower()


@pytest.mark.django_db
def test_register_mobile_money_requires_number(sn_country, register_uc):
    result = register_uc.execute(_register_cmd(
        payment_methods=("MOBILE_MONEY",), mobile_operator="Orange Money", mobile_number="",
    ))
    assert not result.success
    assert "numéro" in result.error_message.lower()


@pytest.mark.django_db
def test_register_invalid_operator_for_country(sn_country, register_uc):
    result = register_uc.execute(_register_cmd(
        payment_methods=("MOBILE_MONEY",),
        mobile_operator="Opérateur Inconnu",
        mobile_number="771234567",
    ))
    assert not result.success
    assert "Opérateur Inconnu" in result.error_message


@pytest.mark.django_db
def test_register_valid_mobile_money(sn_country, register_uc):
    result = register_uc.execute(_register_cmd(
        payment_methods=("ESPECES", "MOBILE_MONEY"),
        mobile_operator="Orange Money",
        mobile_number="771234567",
    ))
    assert result.success
    reg = get_registration_repo().get(result.registration_id)
    assert "MOBILE_MONEY" in reg["payment_methods"]


@pytest.mark.django_db
def test_register_missing_school_name(sn_country, register_uc):
    result = register_uc.execute(_register_cmd(school_name=""))
    assert not result.success



# ── Tests ActivateSchoolRegistrationUseCase ───────────────────────────────────

@pytest.mark.django_db
def test_activate_creates_entities_and_sends_email(sn_country, register_uc, activate_uc, fake_email):
    reg = register_uc.execute(_register_cmd(manager_email="act.test@example.com"))
    act = activate_uc.execute(ActivateSchoolCommand(registration_id=reg.registration_id))
    assert act.success
    assert act.username is not None
    assert act.temp_password is not None
    assert act.email_sent is True
    assert fake_email.sent[0]["to"] == "act.test@example.com"


@pytest.mark.django_db
def test_activate_marks_activated(sn_country, register_uc, activate_uc):
    reg = register_uc.execute(_register_cmd(manager_email="status.test@example.com"))
    activate_uc.execute(ActivateSchoolCommand(registration_id=reg.registration_id))
    data = get_registration_repo().get(reg.registration_id)
    assert data["status"] == "ACTIVATED"
    assert data["created_school_id"] is not None
    assert data["activated_user_id"] is not None


@pytest.mark.django_db
def test_activate_twice_fails(sn_country, register_uc, activate_uc):
    reg = register_uc.execute(_register_cmd(manager_email="twice@example.com"))
    activate_uc.execute(ActivateSchoolCommand(registration_id=reg.registration_id))
    result2 = activate_uc.execute(ActivateSchoolCommand(registration_id=reg.registration_id))
    assert not result2.success
    assert "déjà activé" in result2.error_message


@pytest.mark.django_db
def test_activate_dry_run_does_not_persist(sn_country, register_uc, activate_uc, fake_email):
    reg = register_uc.execute(_register_cmd(manager_email="dryrun@example.com"))
    act = activate_uc.execute(ActivateSchoolCommand(registration_id=reg.registration_id, dry_run=True))
    assert act.success and act.dry_run is True and act.email_sent is False
    assert len(fake_email.sent) == 0
    assert get_registration_repo().get(reg.registration_id)["status"] == "PENDING"


@pytest.mark.django_db
def test_activate_unknown_id_fails(activate_uc):
    result = activate_uc.execute(ActivateSchoolCommand(registration_id=str(uuid.uuid4())))
    assert not result.success
    assert "Aucun dossier" in result.error_message


@pytest.mark.django_db
def test_activate_email_failure_still_creates_school(sn_country):
    repo = get_registration_repo()
    uc = ActivateSchoolRegistrationUseCase(
        registration_repo=repo,
        user_repo=DjangoUserRepository(),
        create_school_uc=get_create_school_use_case(),
        email_sender=FakeEmailSender(fail=True),
    )
    reg = RegisterSchoolUseCase(registration_repo=repo).execute(
        _register_cmd(manager_email="emailfail@example.com")
    )
    result = uc.execute(ActivateSchoolCommand(registration_id=reg.registration_id))
    assert result.success
    assert result.email_sent is False
    assert "non envoyé" in result.error_message


@pytest.mark.django_db
def test_activate_username_collision_adds_suffix(sn_country, register_uc, fake_email):
    repo = get_registration_repo()
    reg1 = register_uc.execute(_register_cmd(manager_email="first@example.com"))
    reg2 = register_uc.execute(_register_cmd(manager_email="second@example.com", school_name="École Deux"))
    uc = ActivateSchoolRegistrationUseCase(
        registration_repo=repo,
        user_repo=DjangoUserRepository(),
        create_school_uc=get_create_school_use_case(),
        email_sender=fake_email,
    )
    act1 = uc.execute(ActivateSchoolCommand(registration_id=reg1.registration_id))
    act2 = uc.execute(ActivateSchoolCommand(registration_id=reg2.registration_id))
    assert act1.success and act2.success
    assert act1.username != act2.username
    assert "2" in act2.username

