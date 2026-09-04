import os
from datetime import timezone
from pathlib import Path

from flask import Flask, request, url_for

from .extensions import csrf, db, migrate
from .runtime import RuntimePaths, configured_database_uri


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    paths = RuntimePaths.for_project(Path(app.root_path).parent)
    app.config.from_mapping(
        SECRET_KEY="local-development-only",
        SQLALCHEMY_DATABASE_URI=configured_database_uri(app.instance_path),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        WTF_CSRF_TIME_LIMIT=None,
        BACKUP_SECONDARY_DIR=os.environ.get("JOSHS_CORNER_BACKUP_SECONDARY_DIR"),
    )

    if test_config:
        app.config.update(test_config)
    else:
        app.config.from_pyfile("local_config.py", silent=True)

    app.config["RUNTIME_PATHS"] = paths
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    from .backup import create_scheduled_backups

    @app.cli.command("backup-db")
    def backup_db_command():
        """Create and validate a local SQLite backup."""
        create_scheduled_backups(
            paths.local_database, paths.backups,
            Path(app.config["BACKUP_SECONDARY_DIR"]) if app.config["BACKUP_SECONDARY_DIR"] else None,
        )

    from .on_this_day import OnThisDayService
    from .figure_of_day import FigureOfDayService

    app.extensions["on_this_day"] = app.config.get("ON_THIS_DAY_SERVICE") or OnThisDayService(
        paths.on_this_day_cache
    )
    app.extensions["figure_of_day"] = app.config.get("FIGURE_OF_DAY_SERVICE") or FigureOfDayService(
        paths.figure_of_day_cache
    )

    @app.template_filter("local_saved_time")
    def local_saved_time(value):
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        local_value = value.astimezone()
        hour = local_value.strftime("%I").lstrip("0") or "12"
        return f"{hour}:{local_value.strftime('%M %p').lower()}"

    @app.template_filter("local_note_datetime")
    def local_note_datetime(value):
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        local_value = value.astimezone()
        hour = local_value.strftime("%I").lstrip("0") or "12"
        return (
            f"{local_value.day} {local_value.strftime('%B %Y')} "
            f"at {hour}:{local_value.strftime('%M %p').lower()}"
        )

    @app.template_filter("local_australian_date")
    def local_australian_date(value):
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        local_value = value.astimezone()
        return f"{local_value.day} {local_value.strftime('%B %Y')}"

    from .gym import format_kg, format_volume, set_summary

    app.add_template_filter(format_kg, "gym_kg")
    app.add_template_filter(format_volume, "gym_volume")
    app.add_template_filter(set_summary, "gym_set_summary")
    from .running import format_duration, format_pace, pace, format_distance
    from .gym import format_number
    app.add_template_filter(format_duration, "run_duration")
    app.add_template_filter(format_pace, "run_pace")
    app.add_template_filter(pace, "run_pace_value")
    app.add_template_filter(format_distance, "run_distance")
    app.add_template_filter(format_number, "exercise_number")
    from .gym import longest_hold, total_time, occurrence_summary
    app.add_template_filter(longest_hold, "gym_longest_hold")
    app.add_template_filter(total_time, "gym_total_time")
    app.add_template_filter(occurrence_summary, "gym_occurrence_summary")

    from .deadlines import human_date

    app.add_template_filter(human_date, "deadline_date")
    from .upcoming import human_time
    app.add_template_filter(human_time, "upcoming_time")

    from .note_content import rich_text_preview, sanitise_rich_text_html

    @app.template_filter("sanitise_html")
    def sanitise_html(value):
        return sanitise_rich_text_html(value)

    @app.template_filter("rich_preview")
    def rich_preview(value, limit=92):
        return rich_text_preview(value, limit)

    from .routes.games import games_bp
    from .routes.home import home_bp
    from .routes.journal import journal_bp
    from .routes.notes import notes_bp
    from .routes.reading import reading_bp
    from .routes.todos import todos_bp
    from .routes.watchlist import watchlist_bp
    from .routes.attachments import attachments_bp
    from .routes.automations import automations_bp
    from .routes.gym import gym_bp
    from .routes.exercise import exercise_bp
    from .routes.deadlines import deadlines_bp
    from .routes.upcoming import upcoming_bp
    from .routes.search import search_bp

    for blueprint in (
        home_bp,
        journal_bp,
        notes_bp,
        todos_bp,
        games_bp,
        watchlist_bp,
        reading_bp,
        attachments_bp,
        automations_bp,
        gym_bp,
        exercise_bp,
        deadlines_bp,
        upcoming_bp,
        search_bp,
    ):
        app.register_blueprint(blueprint)

    @app.context_processor
    def application_section_context():
        """Expose one canonical top-level section to every page template."""
        current_section = (
            "gym" if request.blueprint in ("gym", "exercise") else "automations" if request.blueprint == "automations" else "hub"
        )
        home_endpoint = {
            "gym": "gym.today",
            "automations": "automations.overview",
            "hub": "home.index",
        }[current_section]
        return {
            "current_section": current_section,
            "section_home_url": url_for(home_endpoint),
            "section_home_label": {
                "gym": "Exercise Today",
                "automations": "Intelligence home",
                "hub": "Hub home",
            }[current_section],
        }


    return app
