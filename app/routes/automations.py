from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..flight_tracking import (
    TrackerValidationError, apply_tracker_input, parse_tracker_input, tracker_form_values,
)
from ..models import Automation, AutomationRun, FlightOffer, FlightTracker


automations_bp = Blueprint("automations", __name__, url_prefix="/automations")


def _tracker_or_404(tracker_id: int) -> FlightTracker:
    return db.get_or_404(FlightTracker, tracker_id)


def _flight_trackers(status: str | None = None):
    statement = db.select(FlightTracker).join(FlightTracker.automation).order_by(Automation.updated_at.desc())
    if status:
        statement = statement.where(Automation.status == status)
    return db.session.scalars(statement).all()


def _best_by_category(tracker: FlightTracker, category: str, current_only: bool = True):
    statement = db.select(FlightOffer).where(FlightOffer.tracker_id == tracker.id, FlightOffer.category == category)
    if current_only:
        statement = statement.where(FlightOffer.configuration_version == tracker.configuration_version)
    return db.session.scalar(statement.order_by(FlightOffer.total_price_cents.asc()))


def _overview_context():
    trackers = _flight_trackers("active")
    return {
        "trackers": trackers,
        "best_primary": {tracker.id: _best_by_category(tracker, "primary") for tracker in trackers},
        "recent_runs": db.session.scalars(
            db.select(AutomationRun).join(AutomationRun.automation)
            .order_by(AutomationRun.started_at.desc()).limit(8)
        ).all(),
    }


def _subnav_context(page: str, **context):
    context["automation_page"] = page
    return context


@automations_bp.get("")
def overview():
    return render_template("automations/index.html", **_subnav_context("overview", **_overview_context()))


@automations_bp.get("/trackers")
def trackers():
    return render_template(
        "automations/index.html",
        **_subnav_context(
            "trackers",
            active_trackers=_flight_trackers("active"),
            paused_trackers=_flight_trackers("paused"),
            archived_trackers=_flight_trackers("archived"),
        ),
    )


@automations_bp.route("/trackers/new", methods=["GET", "POST"])
def new_tracker():
    if request.method == "POST":
        try:
            values = parse_tracker_input(request.form)
        except TrackerValidationError as error:
            return render_template(
                "automations/tracker_form.html", form_values=tracker_form_values(submitted=request.form),
                errors=error.errors, tracker=None, is_edit=False,
            ), 400
        try:
            automation = Automation(name=values.name, automation_type="flight_tracker", status="active")
            tracker = FlightTracker(automation=automation)
            apply_tracker_input(tracker, values)
            db.session.add(automation)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        flash("Flight tracker created.", "success")
        return redirect(url_for("automations.tracker_detail", tracker_id=tracker.id))
    return render_template(
        "automations/tracker_form.html", form_values=tracker_form_values(), errors={}, tracker=None, is_edit=False
    )


@automations_bp.get("/trackers/<int:tracker_id>")
def tracker_detail(tracker_id: int):
    tracker = _tracker_or_404(tracker_id)
    current_offers = db.session.scalars(
        db.select(FlightOffer).where(
            FlightOffer.tracker_id == tracker.id,
            FlightOffer.configuration_version == tracker.configuration_version,
        ).order_by(FlightOffer.total_price_cents.asc())
    ).all()
    primary = [offer for offer in current_offers if offer.category == "primary"]
    secondary = [offer for offer in current_offers if offer.category == "secondary"]
    runs = db.session.scalars(
        db.select(AutomationRun).where(AutomationRun.automation_id == tracker.automation_id)
        .order_by(AutomationRun.started_at.desc())
    ).all()
    return render_template(
        "automations/tracker_detail.html", tracker=tracker, primary_offers=primary,
        secondary_offers=secondary, runs=runs, best_primary=_best_by_category(tracker, "primary"),
        previous_best=_previous_best(tracker), provider_configured=False,
    )


def _previous_best(tracker: FlightTracker):
    run = db.session.scalar(
        db.select(AutomationRun).where(
            AutomationRun.automation_id == tracker.automation_id,
            AutomationRun.status == "succeeded",
            AutomationRun.configuration_version == tracker.configuration_version,
        ).order_by(AutomationRun.started_at.desc()).offset(1)
    )
    if run is None:
        return None
    return db.session.scalar(
        db.select(FlightOffer).where(FlightOffer.run_id == run.id, FlightOffer.category == "primary")
        .order_by(FlightOffer.total_price_cents.asc())
    )


@automations_bp.route("/trackers/<int:tracker_id>/edit", methods=["GET", "POST"])
def edit_tracker(tracker_id: int):
    tracker = _tracker_or_404(tracker_id)
    if request.method == "POST":
        try:
            values = parse_tracker_input(request.form)
        except TrackerValidationError as error:
            return render_template(
                "automations/tracker_form.html", form_values=tracker_form_values(submitted=request.form),
                errors=error.errors, tracker=tracker, is_edit=True,
            ), 400
        material_change = apply_tracker_input(tracker, values)
        db.session.commit()
        flash(
            "Tracker updated. A new search series begins for the changed route, date, or cabin." if material_change else "Tracker updated.",
            "success",
        )
        return redirect(url_for("automations.tracker_detail", tracker_id=tracker.id))
    return render_template(
        "automations/tracker_form.html", form_values=tracker_form_values(tracker), errors={}, tracker=tracker, is_edit=True
    )


@automations_bp.post("/trackers/<int:tracker_id>/pause")
def pause_tracker(tracker_id: int):
    tracker = _tracker_or_404(tracker_id)
    if tracker.automation.status != "active":
        abort(409)
    tracker.automation.status = "paused"
    db.session.commit()
    flash("Tracker paused. Its saved history is unchanged.", "success")
    return redirect(url_for("automations.tracker_detail", tracker_id=tracker.id))


@automations_bp.post("/trackers/<int:tracker_id>/resume")
def resume_tracker(tracker_id: int):
    tracker = _tracker_or_404(tracker_id)
    if tracker.automation.status != "paused":
        abort(409)
    tracker.automation.status = "active"
    db.session.commit()
    flash("Tracker resumed.", "success")
    return redirect(url_for("automations.tracker_detail", tracker_id=tracker.id))


@automations_bp.post("/trackers/<int:tracker_id>/archive")
def archive_tracker(tracker_id: int):
    tracker = _tracker_or_404(tracker_id)
    if tracker.automation.status not in {"active", "paused"}:
        abort(409)
    tracker.automation.status = "archived"
    db.session.commit()
    flash("Tracker archived. Its configuration and history are retained.", "success")
    return redirect(url_for("automations.trackers"))


@automations_bp.post("/trackers/<int:tracker_id>/restore")
def restore_tracker(tracker_id: int):
    tracker = _tracker_or_404(tracker_id)
    if tracker.automation.status != "archived":
        abort(409)
    tracker.automation.status = "paused"
    db.session.commit()
    flash("Tracker restored as paused. Resume it when ready.", "success")
    return redirect(url_for("automations.tracker_detail", tracker_id=tracker.id))


@automations_bp.post("/trackers/<int:tracker_id>/check-now")
def check_now(tracker_id: int):
    tracker = _tracker_or_404(tracker_id)
    if tracker.automation.status != "active":
        abort(409)
    flash("Flight provider not configured. Add local provider credentials before checking.", "notice")
    return redirect(url_for("automations.tracker_detail", tracker_id=tracker.id))


@automations_bp.get("/alerts")
def alerts():
    return render_template("automations/index.html", **_subnav_context("alerts"))


@automations_bp.get("/history")
def history():
    runs = db.session.scalars(
        db.select(AutomationRun).join(AutomationRun.automation)
        .order_by(AutomationRun.started_at.desc())
    ).all()
    return render_template("automations/index.html", **_subnav_context("history", recent_runs=runs))
