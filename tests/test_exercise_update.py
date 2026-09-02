"""Stage 4B uses fictional, isolated data; no live database is opened."""
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from flask_migrate import upgrade, downgrade
from sqlalchemy import select, text

from app import create_app
from app.extensions import db
from app.gym import exercise_volume, new_strength_pbs, strength_summary, progress_points
from app.models import Exercise, ExerciseSet, WorkoutExercise, WorkoutSession, WorkoutTemplate, WorkoutTemplateExercise, Run, RunRoute
from app.running import parse_duration, parse_distance, pace, format_pace, run_summary, run_pbs, comparable_elapsed_best, run_points
from test_gym import add_occurrence

DAY = date(2026, 9, 2)


def exercise(name='Press', part='Shoulders', order=0):
    item = Exercise(name=name, body_part=part, sort_order=order)
    db.session.add(item)
    db.session.commit()
    return item


def route(name='Fictional Loop'):
    item = RunRoute(name=name, name_key=name.casefold())
    db.session.add(item)
    db.session.commit()
    return item


def run(track, km, seconds, day=DAY):
    item = Run(route=track, distance_km=Decimal(str(km)), elapsed_seconds=seconds, run_date=day)
    db.session.add(item)
    db.session.commit()
    return item


def run_form(**changes):
    return dict(new_route='Fictional Loop', run_date=DAY.isoformat(), distance_km='6.42', duration='31:18', **changes)


def test_strength_records_strict_chronological_decimal_and_corrections(app, client):
    app.config['EXERCISE_TODAY'] = DAY
    item = exercise()
    baseline = add_occurrence(item, DAY-timedelta(days=3), [(20, 10), (22.5, 6), (25, 4)])
    assert new_strength_pbs(baseline) == []
    later = add_occurrence(item, DAY-timedelta(days=2), [(25, 6)])
    assert new_strength_pbs(later) == ['New rep PB at 25 kg']
    tied = add_occurrence(item, DAY-timedelta(days=1), [(25, 6)])
    assert new_strength_pbs(tied) == []
    current = add_occurrence(item, DAY, [(27.5, 4)])
    assert new_strength_pbs(current) == ['New weight PB']
    summary = strength_summary(item.id)
    assert summary['count'] == 4
    assert summary['last'].id == current.id
    assert summary['weight'] == Decimal('27.50')
    assert summary['reps'] == 4
    assert summary['volume'].id == baseline.id
    # A historical correction affects all derived views, without stored PB flags.
    response = client.post(f'/gym/sets/{baseline.sets[-1].id}/edit', data={'weight_kg':'30', 'reps':'6'})
    assert response.status_code == 302
    assert strength_summary(item.id)['weight'] == Decimal('30')
    assert 'New weight PB' not in new_strength_pbs(current)
    assert progress_points(item.id)[0]['max_weight'] == 30
    item.active = False
    db.session.commit()
    assert strength_summary(item.id)['count'] == 4
    page = client.get(f'/gym/exercises/{item.id}')
    assert page.status_code == 200 and b'Highest volume' in page.data
    assert client.get(f'/gym/history/{baseline.workout_session_id}').status_code == 200


def test_volume_record_600_to_625_and_no_future_comparison(app):
    item = exercise()
    previous = add_occurrence(item, DAY-timedelta(days=1), [(20, 10)]*3)
    current = add_occurrence(item, DAY, [(25, 25)])
    future = add_occurrence(item, DAY+timedelta(days=1), [(100, 100)])
    assert exercise_volume(previous) == Decimal('600')
    assert exercise_volume(current) == Decimal('625')
    assert 'New volume PB' in new_strength_pbs(current)
    decimal_item = exercise('Decimal Press')
    decimal_run = add_occurrence(decimal_item, DAY, [('22.55', 7), ('0.01', 1)])
    assert exercise_volume(decimal_run) == Decimal('157.86')
    assert future.id != current.id


def test_favorite_order_group_isolation_and_persistence(app, client):
    items = [exercise(name, order=i) for i, name in enumerate('ABCD')]
    other = exercise('Other', 'Back', 42)
    old = add_occurrence(items[2], DAY, [(20, 3)])
    client.post(f'/gym/exercises/{items[2].id}/move', data={'action':'up'})
    names = lambda: [item.name for item in db.session.scalars(select(Exercise).where(Exercise.body_part=='Shoulders').order_by(Exercise.sort_order))]
    assert names() == ['A', 'C', 'B', 'D']
    client.post(f'/gym/exercises/{items[2].id}/move', data={'action':'top'})
    assert names() == ['C', 'A', 'B', 'D']
    client.post(f'/gym/exercises/{items[2].id}/move', data={'action':'bottom'})
    assert names() == ['A', 'B', 'D', 'C']
    target_id = items[2].id
    client.post(f'/gym/exercises/{target_id}/favorite')
    db.session.expire_all()
    assert db.session.get(Exercise, target_id).is_favorite
    page = client.get('/gym/exercises').data.decode()
    assert page.index('value="C"') < page.index('value="A"')
    assert db.session.get(Exercise, other.id).sort_order == 42
    assert exercise_volume(old) == 60
    assert new_strength_pbs(old) == []
    assert client.post(f'/gym/exercises/{target_id}/move', data={'action':'sideways'}).status_code == 400
    client.post(f'/gym/exercises/{target_id}/favorite')
    assert not db.session.get(Exercise, target_id).is_favorite


def build_template(client, items):
    response = client.post('/gym/templates', data={'name':'Fictional Push'})
    assert response.status_code == 302
    template = db.session.scalar(select(WorkoutTemplate))
    for item in items:
        assert client.post(f'/gym/templates/{template.id}/exercises', data={'exercise_id':item.id}).status_code == 302
    db.session.expire_all()
    return template


def test_template_independent_copy_editing_and_safe_active_workout(app, client):
    app.config['EXERCISE_TODAY'] = DAY
    a, b, c, d = [exercise(name) for name in 'ABCD']
    template = build_template(client, [a, b, c])
    template_id = template.id
    assert client.get(f'/gym/templates/{template_id}').status_code == 200
    client.post('/gym/today/from-template', data={'template_id':template_id})
    current = db.session.scalar(select(WorkoutSession))
    assert [entry.exercise_id for entry in current.workout_exercises] == [a.id,b.id,c.id]
    occurrence_b = next(entry for entry in current.workout_exercises if entry.exercise_id==b.id)
    client.post(f'/gym/today/workout-exercises/{occurrence_b.id}/remove')
    client.post('/gym/today/exercises', data={'exercise_id':d.id})
    db.session.expire_all()
    occurrence_d = next(entry for entry in current.workout_exercises if entry.exercise_id==d.id)
    client.post(f'/gym/today/workout-exercises/{occurrence_d.id}/move', data={'action':'top'})
    db.session.expire_all()
    assert [entry.exercise_id for entry in current.workout_exercises] == [d.id,a.id,c.id]
    assert [entry.exercise_id for entry in template.exercises] == [a.id,b.id,c.id]
    # Editing a template does not sync backwards into today's copy.
    b_entry = next(entry for entry in template.exercises if entry.exercise_id==b.id)
    client.post(f'/gym/templates/{template_id}/exercises/{b_entry.id}/remove')
    client.post(f'/gym/templates/{template_id}/rename', data={'name':'Renamed Push'})
    db.session.expire_all()
    assert [entry.exercise_id for entry in current.workout_exercises] == [d.id,a.id,c.id]
    client.post('/gym/today/from-template', data={'template_id':template_id})
    db.session.expire_all()
    assert len(current.workout_exercises) == 3
    assert client.post(f'/gym/templates/{template_id}/delete').status_code == 400
    assert client.post(f'/gym/templates/{template_id}/delete', data={'confirm':'yes'}).status_code == 302
    db.session.expire_all()
    assert len(current.workout_exercises) == 3


def test_template_archived_skip_reorder_duplicate_and_append(app, client):
    app.config['EXERCISE_TODAY'] = DAY
    a, b, c, d = [exercise(name) for name in 'ABCD']
    template = build_template(client, [a,b,c])
    client.post(f'/gym/templates/{template.id}/exercises', data={'exercise_id':c.id})
    assert len(template.exercises) == 3
    c_entry = next(item for item in template.exercises if item.exercise_id==c.id)
    client.post(f'/gym/templates/{template.id}/exercises/{c_entry.id}/move', data={'action':'top'})
    db.session.expire_all()
    assert [item.exercise_id for item in template.exercises] == [c.id,a.id,b.id]
    client.post(f'/gym/exercises/{b.id}/archive')
    assert client.post(f'/gym/templates/{template.id}/exercises', data={'exercise_id':b.id}).status_code == 400
    page = client.post('/gym/today/from-template', data={'template_id':template.id}, follow_redirects=True)
    assert b'1 archived exercise was skipped' in page.data
    current = db.session.scalar(select(WorkoutSession))
    assert [item.exercise_id for item in current.workout_exercises] == [c.id,a.id]
    assert not b.active
    client.post(f'/gym/templates/{template.id}/exercises/{c_entry.id}/remove')
    client.post(f'/gym/templates/{template.id}/exercises', data={'exercise_id':d.id})
    db.session.expire_all()
    assert [item.exercise_id for item in template.exercises] == [a.id,b.id,d.id]


def test_removing_workout_with_sets_needs_confirmation_and_renumber_is_safe(app, client):
    app.config['EXERCISE_TODAY'] = DAY
    item = exercise()
    occurrence = add_occurrence(item, DAY, [(20,2),(20,3),(20,4)])
    assert client.post(f'/gym/today/workout-exercises/{occurrence.id}/remove').status_code == 400
    assert client.post(f'/gym/sets/{occurrence.sets[0].id}/remove').status_code == 302
    db.session.expire_all()
    assert [(item.set_number,item.reps) for item in occurrence.sets] == [(1,3),(2,4)]
    assert client.post(f'/gym/today/workout-exercises/{occurrence.id}/remove', data={'confirm':'yes'}).status_code == 302
    assert db.session.scalar(select(db.func.count(ExerciseSet.id))) == 0


@pytest.mark.parametrize('raw,seconds',[('31:18',1878),('1:05:42',3942),('65:42',3942),('0:01',1),('168:00:00',604800)])
def test_duration_parsing(raw,seconds):
    assert parse_duration(raw) == seconds


@pytest.mark.parametrize('raw',['','31','-1:20','0:00','1:60','1:60:00','169:00:00','abc','NaN','1:2:3:4'])
def test_invalid_duration(raw):
    with pytest.raises(ValueError):
        parse_duration(raw)


@pytest.mark.parametrize('raw',['0','-1','NaN','Infinity','1000.001','.0001','6.4211',''])
def test_invalid_distance(raw):
    with pytest.raises(ValueError):
        parse_distance(raw)


def test_pace_decimal_and_run_input_route_identity(app,client):
    assert parse_distance('6.42') == Decimal('6.42')
    first = client.post('/gym/runs', data=run_form())
    assert first.status_code == 302
    entry = db.session.scalar(select(Run))
    assert pace(entry) == Decimal(1878)/Decimal('6.42')
    assert format_pace(pace(entry)) == '4:53 /km'
    assert run_pbs(entry,[entry]) == []
    fields=run_form();fields.update(new_route='  FICTIONAL   loop ',duration='1:05:42',run_time='09:25')
    assert client.post('/gym/runs',data=fields).status_code == 302
    assert db.session.scalar(select(db.func.count(RunRoute.id))) == 1
    page=client.get(first.location)
    assert page.status_code == 200 and b'4:53 /km' in page.data
    for path in ['/gym/runs','/gym/history?kind=runs',f'/gym/runs/routes/{entry.route_id}']:
        assert client.get(path).status_code == 200


@pytest.mark.parametrize('changes',[{'distance_km':'0'},{'duration':'bad'},{'run_date':'bad'},{'run_time':'99:00'},{'notes':'x'*10001},{'new_route':''},{'new_route':'x'*161}])
def test_invalid_run_does_not_create_orphan_route(app,client,changes):
    fields=run_form();fields.update(changes)
    response=client.post('/gym/runs',data=fields)
    assert response.status_code == 400
    assert db.session.scalar(select(db.func.count(Run.id))) == 0
    assert db.session.scalar(select(db.func.count(RunRoute.id))) == 0


def test_run_pbs_qualifying_distances_and_no_inferred_splits(app):
    track=route()
    ten=run(track,'10',3000,DAY-timedelta(days=2))
    summary=run_summary([ten],DAY)
    assert summary['distance_bests'][10] == ten
    assert summary['distance_bests'][1] is None and summary['distance_bests'][5] is None
    one=run(track,'1',240,DAY-timedelta(days=1))
    five=run(track,'5',1200)
    longer=run(track,'12',4000,DAY+timedelta(days=1))
    entries=[ten,one,five,longer]
    summary=run_summary(entries,DAY)
    assert summary['longest']==longer and summary['fastest']==five
    assert summary['distance_bests']=={1:one,5:five,10:ten}
    assert 'New longest run PB' in run_pbs(longer,entries)
    assert 'New route pace PB' in run_pbs(one,entries)
    assert 'New average pace PB' in run_pbs(one,entries)
    assert 'New route pace PB' not in run_pbs(five,entries)  # equal pace
    assert comparable_elapsed_best(entries) is None
    assert run_points(entries)[0]['duration']=='50:00'


@pytest.mark.parametrize('distance,raw,qualifies',[(1,'0.980',True),(1,'1.020',True),(1,'1.021',False),(5,'4.950',True),(5,'5.050',True),(5,'4.949',False),(10,'9.900',True),(10,'10.100',True),(10,'10.101',False)])
def test_distance_pb_window_boundaries(app,distance,raw,qualifies):
    entry=run(route(),raw,900)
    assert (run_summary([entry],DAY)['distance_bests'][distance] is entry) == qualifies


def test_route_elapsed_comparability(app):
    track=route()
    a=run(track,'5',1500)
    b=run(track,'5.05',1450)
    assert comparable_elapsed_best([a,b])==b
    c=run(track,'5.051',1400)
    assert comparable_elapsed_best([a,b,c]) is None


@pytest.mark.parametrize('today,dates,week,month',[
    (date(2026,9,2),['2026-08-30','2026-08-31','2026-09-01','2026-09-06','2026-09-07'],3,3),
    (date(2027,1,1),['2026-12-27','2026-12-28','2026-12-31','2027-01-01','2027-01-03','2027-01-04'],4,3),
])
def test_week_month_and_year_boundaries(app,today,dates,week,month):
    track=route()
    entries=[run(track,'1',300,date.fromisoformat(day)) for day in dates]
    summary=run_summary(entries,today)
    assert summary['week']==Decimal(week)
    assert summary['month']==Decimal(month)


def test_edit_delete_recalculates_and_strength_run_coexist(app,client):
    app.config['EXERCISE_TODAY']=DAY
    track=route()
    a=run(track,'5',1200)
    b=run(track,'5',1500)
    longest=run(track,'10',4000)
    assert run_summary([a,b,longest],DAY)['fastest']==a
    fields=dict(route_id=track.id,run_date=DAY.isoformat(),distance_km='5',duration='30:00',notes='Corrected')
    assert client.post(f'/gym/runs/{a.id}/edit',data=fields).status_code==302
    assert run_summary([a,b,longest],DAY)['fastest']==b
    invalid=dict(fields,duration='bad',new_route='Should not exist')
    assert client.post(f'/gym/runs/{a.id}/edit',data=invalid).status_code==400
    db.session.expire_all()
    assert a.elapsed_seconds==1800
    assert db.session.scalar(select(db.func.count(RunRoute.id)))==1
    assert client.get(f'/gym/runs/{longest.id}/delete').status_code==405
    assert client.post(f'/gym/runs/{longest.id}/delete').status_code==400
    assert client.post(f'/gym/runs/{longest.id}/delete',data={'confirm':'yes'}).status_code==302
    remaining=list(db.session.scalars(select(Run)))
    assert run_summary(remaining,DAY)['longest'].distance_km==5
    item=exercise()
    client.post('/gym/today/start')
    client.post('/gym/today/exercises',data={'exercise_id':item.id})
    page=client.get('/gym').data
    assert b'Log a run' in page and b'Today' in page
    assert db.session.scalar(select(WorkoutSession)).workout_date==DAY
    assert len(remaining)==2


def test_search_route_names_but_not_individual_numeric_runs(app,client):
    from test_search import search as request_search
    search = lambda query: request_search(client, query)
    track=route('Fictional Creek')
    run(track,'6.42',1878)
    results=search('Creek')
    assert len(results)==1
    assert results[0]['result_type']=='Exercise · Run route'
    assert results[0]['destination_url']==f'/gym/runs/routes/{track.id}'
    assert search('1878')==[] and search('6.42')==[]


def test_new_posts_require_csrf():
    secure=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:','WTF_CSRF_ENABLED':True})
    paths=['/gym/templates','/gym/templates/1/rename','/gym/templates/1/delete','/gym/templates/1/exercises',
           '/gym/templates/1/exercises/1/remove','/gym/templates/1/exercises/1/move','/gym/today/from-template',
           '/gym/exercises/1/favorite','/gym/exercises/1/move','/gym/today/workout-exercises/1/move',
           '/gym/today/workout-exercises/1/remove','/gym/runs','/gym/runs/1/edit','/gym/runs/1/delete']
    with secure.app_context():
        db.create_all()
        for path in paths:
            assert secure.test_client().post(path).status_code==400
        db.drop_all()


def test_additive_migration_preserves_raw_strength_and_matches_models(tmp_path):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    database=tmp_path/'stage4b.db'
    isolated=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':f'sqlite:///{database.as_posix()}'})
    migrations=str(Path(__file__).resolve().parents[1]/'migrations')
    with isolated.app_context():
        upgrade(directory=migrations,revision='0dd8dae16435')
        with db.engine.begin() as conn:
            conn.execute(text("INSERT INTO exercise (id,name,body_part,sort_order,active,created_at,updated_at) VALUES (1,'Fictional Press','Shoulders',7,1,'2026-09-01','2026-09-01')"))
            conn.execute(text("INSERT INTO workout_session (id,workout_date,started_at,created_at,updated_at) VALUES (1,'2026-09-01','2026-09-01 09:00:00','2026-09-01','2026-09-01')"))
            conn.execute(text("INSERT INTO workout_exercise (id,workout_session_id,exercise_id,sort_order,created_at,updated_at) VALUES (1,1,1,3,'2026-09-01','2026-09-01')"))
            conn.execute(text("INSERT INTO exercise_set (id,workout_exercise_id,set_number,weight_kg,reps,created_at,updated_at) VALUES (1,1,1,22.55,7,'2026-09-01','2026-09-01')"))
        def raw():
            with db.engine.connect() as conn:
                    return {name:conn.execute(text(f"SELECT {'id,workout_exercise_id,set_number,weight_kg,reps,created_at,updated_at' if name == 'exercise_set' else '*'} FROM {name}")).all() for name in ['workout_session','workout_exercise','exercise_set']}
        before=raw()
        upgrade(directory=migrations,revision='head')
        assert raw()==before
        assert not db.session.get(Exercise,1).is_favorite
        assert db.session.get(Exercise,1).tracking_type=='reps'
        assert db.session.get(ExerciseSet,1).duration_seconds is None
        for model in [Run,RunRoute,WorkoutTemplate,WorkoutTemplateExercise]:
            assert db.session.scalar(select(db.func.count(model.id)))==0
        with db.engine.connect() as conn:
            assert conn.execute(text('PRAGMA integrity_check')).scalar()=='ok'
            assert conn.execute(text('PRAGMA foreign_key_check')).all()==[]
            assert compare_metadata(MigrationContext.configure(conn),db.metadata)==[]
        db.session.remove()
        downgrade(directory=migrations,revision='0dd8dae16435')
        assert raw()==before
        upgrade(directory=migrations,revision='head')
        assert raw()==before
