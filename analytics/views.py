import json
from decimal import Decimal

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from .forms import QueryForm
from .llm_service import answer_question
from .db_connector import (
    get_internal_source, prepare_from_upload,
    prepare_from_path, test_connection, excel_to_sqlite,
)


def _serialize_value(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v


def _palette(n: int) -> list:
    colors = [
        "rgba(99,102,241,0.75)", "rgba(16,185,129,0.75)",
        "rgba(245,158,11,0.75)", "rgba(239,68,68,0.75)",
        "rgba(59,130,246,0.75)", "rgba(168,85,247,0.75)",
        "rgba(20,184,166,0.75)", "rgba(249,115,22,0.75)",
    ]
    return [colors[i % len(colors)] for i in range(n)]


def _prepare_chart_data(columns: list, rows: list) -> dict:
    if not columns or not rows:
        return {}
    labels = [str(_serialize_value(row[0])) for row in rows]
    if len(columns) == 1:
        datasets = [{"label": columns[0], "data": [_serialize_value(r[0]) for r in rows], "backgroundColor": _palette(len(rows))}]
    elif len(columns) == 2:
        datasets = [{"label": columns[1], "data": [_serialize_value(r[1]) for r in rows], "backgroundColor": "rgba(99,102,241,0.75)", "borderColor": "rgba(99,102,241,1)", "borderWidth": 2}]
    else:
        pal = _palette(len(columns) - 1)
        datasets = [{"label": columns[i+1], "data": [_serialize_value(r[i+1]) for r in rows], "backgroundColor": pal[i % len(pal)], "borderColor": pal[i % len(pal)], "borderWidth": 2} for i in range(len(columns) - 1)]
    return {"labels": labels, "datasets": datasets}


_LABEL_FR = {
    "month": "Mois", "year": "Année", "day": "Jour", "date": "Date", "week": "Semaine",
    "total_commission": "Commission totale", "commission": "Commission",
    "avg_commission": "Commission moyenne", "commission_moyenne": "Commission moyenne",
    "total_amount": "Montant total", "amount": "Montant",
    "total_volume": "Volume total", "volume": "Volume",
    "count": "Nombre", "total_count": "Nombre total",
    "transaction_count": "Nombre de transactions", "nb_transactions": "Nombre de transactions",
    "agent_name": "Agent", "agent": "Agent",
    "country": "Pays", "source_country": "Pays source", "destination_country": "Pays destination",
    "status": "Statut", "currency": "Devise",
    "sender": "Expéditeur", "receiver": "Destinataire",
    "created_at": "Date de création",
}


def _humanize_label(name: str) -> str:
    """Colonne SQL brute (ex: total_commission) → libellé lisible (ex: Commission totale)."""
    if not name:
        return name
    key = str(name).strip().lower()
    if key in _LABEL_FR:
        return _LABEL_FR[key]
    # Repli générique : snake_case → phrase capitalisée
    words = [w for w in key.replace("-", "_").split("_") if w]
    if not words:
        return str(name)
    label = " ".join(words)
    return label[:1].upper() + label[1:]


def _format_kpi(val):
    if isinstance(val, float) and val == int(val):
        val = int(val)
    if isinstance(val, (int, float)):
        return f"{val:,.2f}".replace(",", "\u202f").replace(".", ",")
    return str(val)



def index(request):
    """Vue chat : historique en session, input fixé en bas."""

    # Source de données active (interne par défaut)
    if not request.session.get("db_source"):
        request.session["db_source"] = get_internal_source()
        request.session.modified = True
    db_source = request.session["db_source"]

    # Vider l'historique — PRG : redirect après POST
    if request.method == "POST" and request.POST.get("action") == "clear":
        request.session["chat_history"] = []
        request.session.modified = True
        return redirect("analytics:index")

    form = QueryForm()
    last_format = "kpi"

    if request.method == "POST":
        form = QueryForm(request.POST)
        if form.is_valid():
            question      = form.cleaned_data["question"]
            output_format = form.cleaned_data["output_format"]
            last_format   = output_format

            msg = {
                "question":        question,
                "output_format":   output_format,
                "intent":          "analytical",
                "chat_reply":      None,
                "sql":             "",
                "error":           None,
                "kpi_value":       None,
                "kpi_label":       None,
                "chart_data_json": "{}",
                "chart_type":      "bar",
                "columns":         [],
                "rows":            [],
                "dashboard_stats": {},
            }

            result = answer_question(
                question,
                db_path=db_source.get("sqlite_path"),
                table=db_source.get("active_table"),
            )
            msg["intent"]     = result.get("intent", "analytical")
            msg["chat_reply"] = result.get("chat_reply")
            msg["sql"]        = result.get("sql", "")

            if result.get("error"):
                msg["error"] = result["error"]
            elif result.get("intent") == "conversational":
                pass
            else:
                columns   = result["columns"]
                rows      = result["rows"]
                rows_s    = [[_serialize_value(c) for c in r] for r in rows]
                columns_h = [_humanize_label(c) for c in columns]  # libellés lisibles pour l'affichage
                msg["columns"] = columns_h
                msg["rows"]    = rows_s

                # Détecte si le résultat est un vrai scalaire unique
                is_scalar = len(rows) == 1 and len(columns) == 1

                if output_format == "kpi":
                    if not rows:
                        msg["kpi_value"] = "—"
                        msg["kpi_label"] = "Aucun résultat"
                    elif is_scalar:
                        # Vrai KPI : une seule valeur
                        msg["kpi_value"] = _format_kpi(_serialize_value(rows[0][0]))
                        msg["kpi_label"] = columns_h[0]
                    else:
                        # Résultat multi-lignes/colonnes → on bascule sur kpi_list
                        # pour un affichage en cartes plutôt qu'un chiffre isolé
                        msg["kpi_value"] = None
                        msg["kpi_label"] = None
                        msg["kpi_list"]  = [
                            {
                                "label": str(_serialize_value(row[0])),
                                "value": _format_kpi(_serialize_value(row[1])) if len(row) > 1 else _format_kpi(_serialize_value(row[0])),
                                "col":   columns_h[1] if len(columns_h) > 1 else columns_h[0],
                            }
                            for row in rows[:20]  # max 20 cartes
                        ]

                elif output_format == "chart":
                    msg["chart_data_json"] = json.dumps(_prepare_chart_data(columns_h, rows))
                    msg["chart_type"] = "bar" if len(columns_h) >= 2 else "doughnut"
                    # Label de l'axe Y = nom de la colonne numérique
                    msg["chart_y_label"] = columns_h[1] if len(columns_h) >= 2 else columns_h[0]
                    msg["chart_x_label"] = columns_h[0] if len(columns_h) >= 2 else ""

                elif output_format == "dashboard":
                    stats = {}
                    for idx, col in enumerate(columns_h):
                        vals = [_serialize_value(r[idx]) for r in rows if isinstance(_serialize_value(r[idx]), (int, float))]
                        if vals:
                            stats[col] = {"total": sum(vals), "avg": sum(vals)/len(vals), "min": min(vals), "max": max(vals)}
                    msg["dashboard_stats"] = stats

                    # Graphique automatique : mêmes données que le mode chart
                    chart_data = _prepare_chart_data(columns_h, rows)
                    if chart_data:
                        msg["chart_data_json"] = json.dumps(chart_data)
                        # bar si labels catégoriels, doughnut si 1 seule série courte
                        if len(rows) <= 6 and len(columns_h) == 2:
                            msg["chart_type"] = "doughnut"
                        else:
                            msg["chart_type"] = "bar"
                        msg["chart_y_label"] = columns_h[1] if len(columns_h) >= 2 else columns_h[0]
                        msg["chart_x_label"] = columns_h[0] if len(columns_h) >= 2 else ""

            history = request.session.get("chat_history", [])
            history.append(msg)
            request.session["chat_history"] = history[-20:]
            request.session["last_format"]  = output_format
            request.session.modified = True
            # PRG : redirect vers GET — élimine la confirmation "renvoyer le formulaire"
            return redirect("analytics:index")

    return render(request, "analytics/index.html", {
        "form":          QueryForm(initial={"output_format": request.session.get("last_format", "kpi")}),
        "history":       request.session.get("chat_history", []),
        "output_format": request.session.get("last_format", "kpi"),
        "db_source":     db_source,
    })


# ── Vues source de données ────────────────────────────────────────────────────

def source_setup(request):
    """Page de configuration d'une nouvelle source de données."""
    error   = None
    preview = None

    if request.method == "POST":
        action      = request.POST.get("action")
        source_type = request.POST.get("source_type", "internal")

        if action == "use_internal":
            request.session["db_source"]    = get_internal_source()
            request.session["chat_history"] = []
            request.session.modified = True
            return redirect("analytics:index")

        elif action in ("test", "confirm"):
            # Upload (un ou plusieurs fichiers) ou chemin manuel
            uploaded = request.FILES.getlist("db_file")
            manual_path = request.POST.get("manual_path", "").strip()

            if uploaded:
                res = prepare_from_upload(uploaded, source_type)
            elif manual_path:
                res = prepare_from_path(manual_path, source_type)
            else:
                error = "Veuillez choisir un fichier ou saisir un chemin."
                res   = {"ok": False}

            if res.get("ok"):
                cfg   = res["source_config"]
                # Active table depuis le POST si spécifiée
                chosen_table = request.POST.get("active_table", "").strip()
                if chosen_table:
                    cfg["active_table"] = chosen_table

                test = test_connection(cfg)
                if not test["ok"]:
                    error = test["error"]
                else:
                    cfg["active_table"] = test["active_table"]
                    preview = {
                        "tables":     test["tables"],
                        "table_info": test["table_info"],
                        "label":      cfg.get("label", cfg.get("original_name", "")),
                        "source_config_json": json.dumps(cfg),
                    }
                    if action == "confirm":
                        request.session["db_source"]    = cfg
                        request.session["chat_history"] = []
                        request.session.modified = True
                        return redirect("analytics:index")
            elif not error:
                error = res.get("error", "Erreur inconnue.")

    return render(request, "analytics/source_setup.html", {
        "error": error, "preview": preview,
        "current_source": request.session.get("db_source"),
    })


def source_test(request):
    """AJAX — teste une connexion et retourne tables + aperçu en JSON."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST requis."})

    source_type = request.POST.get("source_type", "sqlite")
    uploaded    = request.FILES.getlist("db_file")
    manual_path = request.POST.get("manual_path", "").strip()
    chosen_table = request.POST.get("active_table", "").strip()

    if uploaded:
        res = prepare_from_upload(uploaded, source_type)
    elif manual_path:
        res = prepare_from_path(manual_path, source_type)
    else:
        return JsonResponse({"ok": False, "error": "Aucun fichier ni chemin fourni."})

    if not res["ok"]:
        return JsonResponse({"ok": False, "error": res.get("error")})

    cfg = res["source_config"]
    if chosen_table:
        cfg["active_table"] = chosen_table
    test = test_connection(cfg)

    return JsonResponse({
        "ok":          test["ok"],
        "tables":      test.get("tables", []),
        "active_table": test.get("active_table"),
        "table_info":  test.get("table_info", {}),
        "error":       test.get("error"),
        "source_config": cfg,
    })


def source_confirm(request):
    """Valide et enregistre la source choisie en session."""
    if request.method != "POST":
        return redirect("analytics:source_setup")

    cfg_json = request.POST.get("source_config_json", "")
    try:
        cfg = json.loads(cfg_json)
    except (json.JSONDecodeError, ValueError):
        return redirect("analytics:source_setup")

    chosen_table = request.POST.get("active_table", "").strip()
    if chosen_table:
        cfg["active_table"] = chosen_table

    # Fichier pas encore converti (ex: Excel) — la conversion reelle n'a lieu
    # qu'ici, une fois la feuille/table choisie par l'utilisateur.
    if not cfg.get("sqlite_path") and cfg.get("raw_path"):
        conv = excel_to_sqlite(cfg["raw_path"], cfg.get("active_table") or "")
        if conv["error"]:
            messages.error(request, f"Conversion impossible : {conv['error']}")
            return redirect("analytics:source_setup")
        cfg["sqlite_path"]  = conv["sqlite_path"]
        cfg["active_table"] = conv["table_name"]

    request.session["db_source"]    = cfg
    request.session["chat_history"] = []
    request.session.modified = True
    return redirect("analytics:index")


