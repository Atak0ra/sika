"""
interface/director/views/__init__.py
=======================================
Ré-exporte toutes les vues du package pour que director/urls.py
(`from . import views; views.dashboard`) fonctionne sans modification.

Organisation interne :
  _shared.py    — helpers communs + base_context
  dashboard.py  — dashboard + switch_year
  years.py      — manage_years, activate_year, close_year
  structure.py  — add_level, add_class, configure_pricing
  students.py   — students_list, register_student, student_detail,
                  class_detail, promote_class
  misc.py       — alerts, export_renvoyables, school_settings
"""

from .dashboard import dashboard, dashboard_refresh, secretary_dashboard, switch_year
from .fee_items import fee_item_create, fee_item_deactivate, fee_item_edit, fee_items_list
from .misc import alerts, export_renvoyables, school_settings
from .structure import add_class, add_level, configure_pricing
from .students import (
    class_detail,
    promote_class,
    register_student,
    student_detail,
    students_list,
)
from .years import activate_year, close_year, manage_years

__all__ = [
    "dashboard", "dashboard_refresh", "secretary_dashboard", "switch_year",
    "manage_years", "activate_year", "close_year",
    "add_level", "add_class", "configure_pricing",
    "fee_items_list", "fee_item_create", "fee_item_edit", "fee_item_deactivate",
    "students_list", "register_student", "student_detail",
    "class_detail", "promote_class",
    "alerts", "export_renvoyables", "school_settings",
]

