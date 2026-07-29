import os
from datetime import timezone
from pathlib import Path

from flask import Flask

from .extensions import csrf, db, migrate


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    database_path = Path(app.instance_path) / "joshs_corner.db"
    app.config.from_mapping(
        SECRET_KEY="local-development-only",
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{database_path.as_posix()}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        WTF_CSRF_TIME_LIMIT=None,
        BACKUP_SECONDARY_DIR=os.environ.get("JOSHS_CORNER_BACKUP_SECONDARY_DIR"),
    )

    if test_config:
        app.config.update(test_config)
    else:
        app.config.from_pyfile("local_config.py", silent=True)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    from .backup import create_backup, create_scheduled_backups

    @app.cli.command("backup-db")
    def backup_db_command():
        """Create and validate a local SQLite backup."""
        create_scheduled_backups(
            database_path, Path(app.root_path).parent / "backups",
            Path(app.config["BACKUP_SECONDARY_DIR"]) if app.config["BACKUP_SECONDARY_DIR"] else None,
        )

    from .on_this_day import OnThisDayService
    from .figure_of_day import FigureOfDayService

    app.extensions["on_this_day"] = app.config.get("ON_THIS_DAY_SERVICE") or OnThisDayService(
        Path(app.instance_path) / "on_this_day_cache.json"
    )
    app.extensions["figure_of_day"] = app.config.get("FIGURE_OF_DAY_SERVICE") or FigureOfDayService(
        Path(app.instance_path) / "figure_of_day_cache.json"
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

    from .note_content import sanitise_rich_text_html

    @app.template_filter("sanitise_html")
    def sanitise_html(value):
        return sanitise_rich_text_html(value)

    from .routes.games import games_bp
    from .routes.home import home_bp
    from .routes.journal import journal_bp
    from .routes.notes import notes_bp
    from .routes.reading import reading_bp
    from .routes.todos import todos_bp
    from .routes.watchlist import watchlist_bp

    for blueprint in (
        home_bp,
        journal_bp,
        notes_bp,
        todos_bp,
        games_bp,
        watchlist_bp,
        reading_bp,
    ):
        app.register_blueprint(blueprint)

    is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if not app.testing and database_path.exists() and (not app.debug or is_reloader_child):
        try:
            create_scheduled_backups(
                database_path,
                Path(app.root_path).parent / "backups",
                Path(app.config["BACKUP_SECONDARY_DIR"]) if app.config["BACKUP_SECONDARY_DIR"] else None,
            )
        except Exception:
            app.logger.exception("Startup database backup failed")

    return app
