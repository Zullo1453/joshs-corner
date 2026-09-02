"""Explicit Stage 4B backup/snapshot checks. Never migrates or replaces live data.

Run --prepare with the normal server stopped, then migrate separately and run
--verify. Snapshot files and separate restore drills remain under ignored instance/.
Only counts, column names, and hashes are saved, never personal record content.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.backup import create_backup_package, validate_backup_package, restore_backup_package

DATABASE = ROOT/'instance'/'joshs_corner.db'
SNAPSHOT = ROOT/'instance'/'stage4b-release-baseline.json'
NEW_TABLES = ('run', 'run_route', 'workout_template', 'workout_template_exercise')


def quote(identifier):
    return '"' + identifier.replace('"','""') + '"'


def inspect_database(database, previous=None):
    with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as connection:
        assert connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
        head=connection.execute('SELECT version_num FROM alembic_version').fetchone()[0]
        tables=previous or {row[0]:None for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'")}
        result={}
        for table, old in tables.items():
            columns=old['columns'] if old else [row[1] for row in connection.execute('PRAGMA table_info('+quote(table)+')')]
            rows=connection.execute('SELECT '+','.join(map(quote,columns))+' FROM '+quote(table)).fetchall()
            digest=hashlib.sha256(json.dumps(sorted(rows,key=repr),default=repr,ensure_ascii=False).encode()).hexdigest()
            result[table]={'columns':columns,'count':len(rows),'sha256':digest}
        return head,result


def restored(package, label):
    folder=ROOT/'instance'/('stage4b-restore-'+label+'-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    destination=folder/'joshs_corner.db'
    restore_backup_package(package,destination,folder/'uploads')
    return destination


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['prepare','verify'])
    mode=parser.parse_args().mode
    if mode=='prepare':
        assert not SNAPSHOT.exists(), 'Existing baseline must not be silently replaced.'
        head,tables=inspect_database(DATABASE)
        assert head=='0dd8dae16435'
        assert not set(NEW_TABLES)&tables.keys()
        rolling=create_backup_package(DATABASE,ROOT/'instance'/'uploads',ROOT/'backups'/'rolling')
        monthly_files=sorted((ROOT/'backups'/'monthly').glob('*.zip'),key=lambda item:item.stat().st_mtime)
        assert monthly_files,'A validated monthly backup is required.'
        monthly=monthly_files[-1]
        for label,package in [('rolling',rolling),('monthly',monthly)]:
            validate_backup_package(package)
            restored_head,restored_tables=inspect_database(restored(package,label))
            if label=='rolling':
                assert restored_head==head and restored_tables==tables
        SNAPSHOT.write_text(json.dumps({'head':head,'tables':tables,'rolling':str(rolling.relative_to(ROOT)),'monthly':str(monthly.relative_to(ROOT))},indent=2),encoding='utf-8')
        print(json.dumps({'stage':'pre-migration','head':head,'integrity':'ok','foreign_keys':0,'counts':{key:value['count'] for key,value in tables.items()},'fresh_rolling_validated':True,'monthly_validated':True,'both_restore_drills':True}))
        return
    baseline=json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    head,original=inspect_database(DATABASE,baseline['tables'])
    assert head=='e4b7a9c2d610'
    assert original==baseline['tables'],'An original field or row changed.'
    with sqlite3.connect(DATABASE.as_uri()+'?mode=ro',uri=True) as conn:
        counts={table:conn.execute('SELECT count(*) FROM '+quote(table)).fetchone()[0] for table in NEW_TABLES}
        assert not any(counts.values()),'Real sample data is not allowed.'
        assert conn.execute('SELECT count(*) FROM exercise WHERE is_favorite != 0').fetchone()[0]==0
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine
    from app.extensions import db
    from app import models
    engine=create_engine('sqlite+pysqlite://',creator=lambda:sqlite3.connect(DATABASE.as_uri()+'?mode=ro',uri=True))
    with engine.connect() as conn:
        differences=compare_metadata(MigrationContext.configure(conn),db.metadata)
        assert differences==[],repr(differences)
    engine.dispose()
    config=Config();config.set_main_option('script_location',str(ROOT/'migrations'))
    assert ScriptDirectory.from_config(config).get_current_head()==head
    postbackup=create_backup_package(DATABASE,ROOT/'instance'/'uploads',ROOT/'backups'/'rolling')
    validate_backup_package(postbackup)
    assert inspect_database(restored(postbackup,'postmigration'))==inspect_database(DATABASE)
    validate_backup_package(ROOT/baseline['monthly'])
    print(json.dumps({'stage':'post-migration','head':head,'original_tables_unchanged':len(original),'counts':{key:value['count'] for key,value in original.items()},'new_tables':counts,'integrity':'ok','foreign_keys':0,'schema_differences':0,'fresh_backup_and_restore':True,'monthly_validated':True}))


if __name__=='__main__':
    main()
