"""
tests/test_identity.py — Tests unitaires du domaine Identity (sans DB).
"""
import pytest
from economat.domain.identity.value_objects import Role, Email, MembershipId
from economat.domain.identity.entities import Membership
from economat.domain.school.value_objects import SchoolId
from economat.domain.shared.errors import DomainError, DuplicateEntityError


def make_membership(role, active=True):
    return Membership(
        id=MembershipId.generate(), user_id="42",
        school_id=SchoolId.generate(), role=role,
        display_name="Test User", login="test.user", is_active=active,
    )


class TestEmail:
    def test_valid(self): assert Email("m@ecole.sn").value == "m@ecole.sn"
    def test_minuscules(self): assert Email("M@ECOLE.SN").value == "m@ecole.sn"
    def test_invalide(self):
        with pytest.raises(ValueError): Email("pas-email")
    def test_vide(self):
        with pytest.raises(ValueError): Email("")


class TestMembershipPermissions:
    def test_director_tout(self):
        m = make_membership(Role.DIRECTOR)
        assert all([m.can_record_payment(), m.can_register_student(),
                    m.can_configure_pricing(), m.can_manage_team(),
                    m.can_view_dashboard(), m.can_use_chat()])

    def test_econome_seulement_paiement(self):
        m = make_membership(Role.ECONOME)
        assert m.can_record_payment()
        assert not m.can_configure_pricing()
        assert not m.can_manage_team()
        assert not m.can_view_dashboard()

    def test_secretary_inscriptions(self):
        m = make_membership(Role.SECRETARY)
        assert m.can_register_student() and m.can_record_payment()
        assert not m.can_configure_pricing() and not m.can_manage_team()

    def test_inactif_ne_peut_rien(self):
        m = make_membership(Role.DIRECTOR, active=False)
        assert not m.can_record_payment()
        assert not m.can_configure_pricing()

    def test_guard_config_econome(self):
        with pytest.raises(DomainError): make_membership(Role.ECONOME).guard_configure_pricing()

    def test_guard_equipe_secretary(self):
        with pytest.raises(DomainError): make_membership(Role.SECRETARY).guard_manage_team()

    def test_director_guards_ok(self):
        m = make_membership(Role.DIRECTOR)
        m.guard_configure_pricing()
        m.guard_manage_team()

    def test_desactiver_director_interdit(self):
        with pytest.raises(DomainError): make_membership(Role.DIRECTOR).deactivate()

    def test_desactiver_econome_ok(self):
        m = make_membership(Role.ECONOME)
        m.deactivate()
        assert not m.is_active

    def test_can_manage_structure_director(self):
        assert make_membership(Role.DIRECTOR).can_manage_structure()

    def test_can_manage_structure_secretary(self):
        assert make_membership(Role.SECRETARY).can_manage_structure()

    def test_cannot_manage_structure_econome(self):
        assert not make_membership(Role.ECONOME).can_manage_structure()

    def test_guard_manage_structure_econome(self):
        with pytest.raises(DomainError):
            make_membership(Role.ECONOME).guard_manage_structure()

    def test_guard_manage_structure_director_ok(self):
        make_membership(Role.DIRECTOR).guard_manage_structure()

    def test_guard_manage_structure_secretary_ok(self):
        make_membership(Role.SECRETARY).guard_manage_structure()

    # ── Annulation de paiement ────────────────────────────────────────────────

    def test_can_cancel_payment_director(self):
        assert make_membership(Role.DIRECTOR).can_cancel_payment()

    def test_cannot_cancel_payment_secretary(self):
        assert not make_membership(Role.SECRETARY).can_cancel_payment()

    def test_cannot_cancel_payment_econome(self):
        assert not make_membership(Role.ECONOME).can_cancel_payment()

    def test_cannot_cancel_payment_inactive(self):
        assert not make_membership(Role.DIRECTOR, active=False).can_cancel_payment()

    def test_guard_cancel_payment_director_ok(self):
        make_membership(Role.DIRECTOR).guard_cancel_payment()  # ne doit pas lever

    def test_guard_cancel_payment_secretary_raises(self):
        with pytest.raises(DomainError):
            make_membership(Role.SECRETARY).guard_cancel_payment()

    def test_guard_cancel_payment_econome_raises(self):
        with pytest.raises(DomainError):
            make_membership(Role.ECONOME).guard_cancel_payment()

    def test_director_guards_ok_includes_cancel(self):
        m = make_membership(Role.DIRECTOR)
        m.guard_configure_pricing()
        m.guard_manage_team()
        m.guard_cancel_payment()

    # ── Saisie de paiement (tous rôles actifs) ──────────────────────────────

    def test_can_record_payment_director(self):
        assert make_membership(Role.DIRECTOR).can_record_payment()

    def test_can_record_payment_secretary(self):
        assert make_membership(Role.SECRETARY).can_record_payment()

    def test_can_record_payment_econome(self):
        assert make_membership(Role.ECONOME).can_record_payment()

    def test_cannot_record_payment_inactive(self):
        assert not make_membership(Role.DIRECTOR, active=False).can_record_payment()

    def test_guard_record_payment_director_ok(self):
        make_membership(Role.DIRECTOR).guard_record_payment()  # ne doit pas lever

    def test_guard_record_payment_secretary_ok(self):
        make_membership(Role.SECRETARY).guard_record_payment()  # ne doit pas lever

    def test_guard_record_payment_inactive_raises(self):
        with pytest.raises(DomainError):
            make_membership(Role.SECRETARY, active=False).guard_record_payment()


class FakeUserRepo:
    def __init__(self): self._u = {}; self._c = 100
    def create_user(self, username, password, first_name="", last_name="", email=""):
        self._c += 1; uid = str(self._c)
        self._u[username] = {"id": uid, "username": username}
        return uid
    def find_by_username(self, username): return self._u.get(username)
    def username_exists(self, username): return username in self._u
    def set_password(self, uid, pw): pass


class FakeMembershipRepo:
    def __init__(self): self._s = {}
    def find_by_id(self, mid): return self._s.get(mid.value)
    def find_by_user_and_school(self, uid, sid):
        return next((m for m in self._s.values()
                     if m.user_id == uid and m.school_id == sid and m.is_active), None)
    def find_by_user(self, uid): return [m for m in self._s.values() if m.user_id == uid]
    def find_by_school(self, sid): return [m for m in self._s.values() if m.school_id == sid]
    def save(self, m): self._s[m.id.value] = m
    def next_id(self): return MembershipId.generate()
    def count_directors(self, sid):
        return sum(1 for m in self._s.values()
                   if m.school_id == sid and m.role == Role.DIRECTOR and m.is_active)


from economat.application.use_cases.signup_director import SignUpDirectorUseCase
from economat.application.dto_identity import SignUpDirectorCommand


class TestSignUpDirectorUseCase:
    def _uc(self): return SignUpDirectorUseCase(FakeUserRepo())

    def test_ok(self):
        r = self._uc().execute(SignUpDirectorCommand(
            username="m.diallo", password="secret123", first_name="Mamadou", last_name="Diallo"
        ))
        assert r.success and r.username == "m.diallo" and r.user_id

    def test_username_vide(self):
        r = self._uc().execute(SignUpDirectorCommand(
            username="", password="secret123", first_name="X", last_name="Y"
        ))
        assert not r.success

    def test_mdp_trop_court(self):
        r = self._uc().execute(SignUpDirectorCommand(
            username="user1", password="12", first_name="X", last_name="Y"
        ))
        assert not r.success

    def test_doublon_username(self):
        repo = FakeUserRepo(); repo.create_user("m.diallo", "pw")
        r = SignUpDirectorUseCase(repo).execute(SignUpDirectorCommand(
            username="m.diallo", password="secret123", first_name="A", last_name="B"
        ))
        assert not r.success and "éjà utilisé" in r.error_message


from economat.application.use_cases.create_collaborator import CreateCollaboratorUseCase
from economat.application.dto_identity import CreateCollaboratorCommand


def _director_membership(uid, school_id):
    return Membership(
        id=MembershipId.generate(), user_id=uid, school_id=school_id,
        role=Role.DIRECTOR, display_name="Dir", login="dir", is_active=True,
    )


class TestCreateCollaboratorUseCase:
    def _setup(self):
        ur, mr = FakeUserRepo(), FakeMembershipRepo()
        sid = SchoolId.generate()
        mr.save(_director_membership("42", sid))
        return CreateCollaboratorUseCase(ur, mr), ur, mr, sid

    def test_creation_econome_ok(self):
        uc, _, _, sid = self._setup()
        r = uc.execute(CreateCollaboratorCommand(
            director_user_id="42", school_id=str(sid),
            username="a.sow", password="pass123",
            first_name="A", last_name="Sow", role="ECONOME",
        ))
        assert r.success and r.username == "a.sow" and r.role == "ECONOME"

    def test_non_directeur_refuse(self):
        uc, _, mr, sid = self._setup()
        eco = Membership(id=MembershipId.generate(), user_id="99", school_id=sid,
                         role=Role.ECONOME, display_name="E", login="e", is_active=True)
        mr.save(eco)
        r = uc.execute(CreateCollaboratorCommand(
            director_user_id="99", school_id=str(sid),
            username="new", password="pass123", first_name="X", last_name="Y", role="ECONOME",
        ))
        assert not r.success

    def test_username_deja_pris(self):
        uc, ur, _, sid = self._setup()
        ur.create_user("a.sow", "pw")
        r = uc.execute(CreateCollaboratorCommand(
            director_user_id="42", school_id=str(sid),
            username="a.sow", password="pass123", first_name="A", last_name="S", role="ECONOME",
        ))
        assert not r.success and "éjà utilisé" in r.error_message

    def test_role_invalide(self):
        uc, _, _, sid = self._setup()
        r = uc.execute(CreateCollaboratorCommand(
            director_user_id="42", school_id=str(sid),
            username="x", password="pass123", first_name="X", last_name="Y", role="SUPER",
        ))
        assert not r.success
