from flask import Blueprint, render_template

from ..models import Automation, AutomationRun


automations_bp = Blueprint("automations", __name__, url_prefix="/automations")


@automations_bp.get("")
def overview():
    return render_template(
        "automations/index.html",
        automation_page="overview",
        automations=Automation.query.order_by(Automation.created_at.desc()).all(),
        recent_runs=AutomationRun.query.order_by(AutomationRun.started_at.desc()).limit(8).all(),
    )


@automations_bp.get("/trackers")
def trackers():
    return render_template("automations/index.html", automation_page="trackers")


@automations_bp.get("/alerts")
def alerts():
    return render_template("automations/index.html", automation_page="alerts")


@automations_bp.get("/history")
def history():
    return render_template(
        "automations/index.html",
        automation_page="history",
        recent_runs=AutomationRun.query.order_by(AutomationRun.started_at.desc()).all(),
    )
