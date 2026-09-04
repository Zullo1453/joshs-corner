"""Explicit backup and migration rehearsal; never migrates the live DB itself."""
import argparse
import json
from pathlib import Path

from exercise_release_audit import ROOT, DATABASE, inspect_database, restored
from app.backup import create_rolling_backup_package, validate_backup_package

BASELINE=ROOT/'instance'/'exercise-refinement-baseline.json'
OLD_HEAD='e4b7a9c2d610'
NEW_HEAD='f6c8d2e4a910'


def schema_matches(database):
    import sqlite3
    from sqlalchemy import create_engine
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.extensions import db
    from app import models
    engine=create_engine('sqlite+pysqlite://',creator=lambda:sqlite3.connect(database.as_uri()+'?mode=ro',uri=True))
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn),db.metadata)==[]
    engine.dispose()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','verify']);mode=parser.parse_args().mode
    if mode=='prepare':
        assert not BASELINE.exists(),'Never overwrite an existing baseline.'
        head,tables=inspect_database(DATABASE)
        assert head==OLD_HEAD
        rolling=create_rolling_backup_package(DATABASE,ROOT/'instance'/'uploads',ROOT/'backups'/'rolling')
        monthly=max((ROOT/'backups'/'monthly').glob('*.zip'),key=lambda item:item.stat().st_mtime)
        validate_backup_package(rolling);validate_backup_package(monthly)
        trial=restored(rolling,'refinement-rehearsal')
        assert inspect_database(trial)==(head,tables)
        inspect_database(restored(monthly,'refinement-monthly'))
        from app import create_app
        from flask_migrate import upgrade
        isolated=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':f'sqlite:///{trial.as_posix()}'})
        with isolated.app_context():upgrade(directory=str(ROOT/'migrations'),revision=NEW_HEAD)
        assert inspect_database(trial,tables)==(NEW_HEAD,tables)
        schema_matches(trial)
        BASELINE.write_text(json.dumps({'tables':tables,'monthly':str(monthly.relative_to(ROOT))}),encoding='utf-8')
        print(json.dumps({'stage':'prepared','original_tables':len(tables),'counts':{key:value['count'] for key,value in tables.items()},'backups_and_restores':True,'migration_rehearsal_preserved_all_original_fields':True,'schema_matches':True}))
    else:
        baseline=json.loads(BASELINE.read_text(encoding='utf-8'));tables=baseline['tables']
        assert inspect_database(DATABASE,tables)==(NEW_HEAD,tables)
        schema_matches(DATABASE)
        backup=create_rolling_backup_package(DATABASE,ROOT/'instance'/'uploads',ROOT/'backups'/'rolling')
        assert inspect_database(restored(backup,'refinement-after'))==inspect_database(DATABASE)
        validate_backup_package(ROOT/baseline['monthly'])
        print(json.dumps({'stage':'verified','head':NEW_HEAD,'original_tables_preserved':len(tables),'integrity':'ok','foreign_keys':0,'schema_differences':0,'post_backup_restore':True}))


if __name__=='__main__':main()
