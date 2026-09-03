"""Fictional coverage for duration sets, anchored saves and same-route comparisons."""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Exercise, ExerciseSet, WorkoutExercise, WorkoutSession, RunRoute
from app.gym import new_strength_pbs, timed_summary, set_summary, exercise_volume, max_weight, max_reps, progress_points, set_values, total_reps
from app.running import route_progress
from test_exercise_update import DAY, exercise, route, run


def start(client, app, kind='timed'):
    app.config['EXERCISE_TODAY']=DAY
    client.post('/gym/exercises',data={'name':'Fictional Plank' if kind=='timed' else 'Fictional Press','body_part':'Core','tracking_type':kind})
    item=db.session.scalar(select(Exercise))
    client.post('/gym/today/start')
    response=client.post('/gym/today/exercises',data={'exercise_id':item.id})
    occurrence=db.session.scalar(select(WorkoutExercise))
    assert response.location.endswith(f'#exercise-{occurrence.id}')
    return item,occurrence


def test_timed_set_create_repeat_edit_and_history(app,client):
    item,occurrence=start(client,app)
    endpoint=f'/gym/today/workout-exercises/{occurrence.id}/sets'
    assert client.post(endpoint,data={'action':'same'}).status_code==302
    assert not occurrence.sets
    response=client.post(endpoint,data={'duration':'1:15'})
    assert response.location.endswith(f'#set-entry-{occurrence.id}')
    client.post(endpoint,data={'action':'same','duration':'not-used'})
    db.session.expire_all()
    assert [(entry.duration_seconds,entry.weight_kg,entry.reps) for entry in occurrence.sets]==[(75,None,None)]*2
    assert set_summary(occurrence.sets[0])=='1:15'
    assert exercise_volume(occurrence)==0 and max_weight(occurrence) is None
    assert new_strength_pbs(occurrence)==[]
    entry=occurrence.sets[0]
    response=client.post(f'/gym/sets/{entry.id}/edit',data={'duration':'90'})
    assert response.location.endswith(f'#saved-set-{entry.id}')
    assert entry.duration_seconds==90
    before=entry.duration_seconds
    client.post(f'/gym/sets/{entry.id}/edit',data={'duration':'-2'})
    assert entry.duration_seconds==before
    point=progress_points(item.id)[0]
    assert point['hold']==90 and point['total_time']==165
    assert point['max_weight'] is None
    for path in ['/gym',f'/gym/exercises/{item.id}','/gym/history',f'/gym/history/{occurrence.workout_session_id}']:
        page=client.get(path)
        assert page.status_code==200
        assert b'1:30' in page.data
        assert b'Weight (kg)' not in page.data
    assert b'Longest hold progression' in client.get(f'/gym/exercises/{item.id}').data
    # History cannot be reinterpreted by changing the exercise's tracking type.
    client.post(f'/gym/exercises/{item.id}/edit',data={'name':item.name,'body_part':'Core','tracking_type':'reps'})
    assert item.tracking_type=='timed'


def test_timed_pbs_copy_previous_historical_correction(app,client):
    item,current=start(client,app)
    prior=WorkoutSession(workout_date=DAY-timedelta(days=2),started_at=current.session.started_at-timedelta(days=2))
    older=WorkoutExercise(session=prior,exercise=item)
    older.sets.append(ExerciseSet(set_number=1,duration_seconds=45))
    db.session.add(prior);db.session.commit()
    client.post(f'/gym/today/workout-exercises/{current.id}/copy-previous')
    db.session.expire_all()
    assert current.sets[0].duration_seconds==45
    assert current.sets[0].id!=older.sets[0].id
    assert new_strength_pbs(current)==[]
    client.post(f'/gym/sets/{current.sets[0].id}/edit',data={'duration':'60'})
    assert new_strength_pbs(current)==['New longest hold PB','New total time PB']
    client.post(f'/gym/sets/{older.sets[0].id}/edit',data={'duration':'90'})
    assert new_strength_pbs(current)==[]
    assert timed_summary(item.id)['best'].id==older.id


def test_weighted_repeat_uses_saved_values_not_blank_form(app,client):
    item,occurrence=start(client,app,'reps')
    endpoint=f'/gym/today/workout-exercises/{occurrence.id}/sets'
    client.post(endpoint,data={'weight_kg':'22.55','reps':'7'})
    client.post(endpoint,data={'action':'same','weight_kg':'999','reps':'999'})
    db.session.expire_all()
    assert [(entry.weight_kg,entry.reps,entry.duration_seconds) for entry in occurrence.sets]==[(Decimal('22.55'),7,None)]*2
    assert b'Add same set' in client.get('/gym').data


def test_reps_only_set_create_repeat_edit_and_progress(app, client):
    item, occurrence = start(client, app, 'bodyweight')
    endpoint = f'/gym/today/workout-exercises/{occurrence.id}/sets'
    page = client.get('/gym').data
    assert b'<option value="bodyweight" selected>Reps</option>' in client.get('/gym/exercises').data
    assert b'Weight (kg)' not in page and b'<span>Reps</span>' in page
    client.post(endpoint, data={'reps': '12'})
    client.post(endpoint, data={'action': 'same'})
    db.session.expire_all()
    assert [(entry.weight_kg, entry.reps, entry.duration_seconds) for entry in occurrence.sets] == [(None, 12, None)] * 2
    assert set_summary(occurrence.sets[0]) == '12 reps'
    assert max_reps(occurrence) == 12 and total_reps(occurrence) == 24
    assert exercise_volume(occurrence) == 0 and max_weight(occurrence) is None
    entry = occurrence.sets[0]
    client.post(f'/gym/sets/{entry.id}/edit', data={'reps': '15'})
    assert entry.weight_kg is None and entry.reps == 15
    point = progress_points(item.id)[0]
    assert point['max_reps'] == 15 and point['total_reps'] == 27
    for path in ['/gym', f'/gym/exercises/{item.id}', '/gym/history', f'/gym/history/{occurrence.workout_session_id}']:
        assert client.get(path).status_code == 200
    detail = client.get(f'/gym/exercises/{item.id}').data
    assert b'Best set progression' in detail and b'Weight Progression' not in detail


@pytest.mark.parametrize('raw',['0','-1','1:60','abc','24:00:01','86401','','NaN'])
def test_invalid_hold_duration(app,raw):
    item=Exercise(tracking_type='timed')
    with pytest.raises(ValueError):set_values(item,{'duration':raw})


@pytest.mark.parametrize('values',[{}, {'duration_seconds':0}, {'duration_seconds':86401}, {'duration_seconds':30,'weight_kg':5,'reps':2}, {'weight_kg':5}])
def test_database_rejects_ambiguous_set_measurements(app,client,values):
    _,occurrence=start(client,app)
    db.session.add(ExerciseSet(workout_exercise=occurrence,set_number=1,**values))
    with pytest.raises(IntegrityError):db.session.commit()
    db.session.rollback()


def test_route_distance_comparison_keeps_actual_runs_and_separates_routes(app,client):
    a=route('Fictional Course');a.distance_km=Decimal('5');db.session.commit()
    b=route('Other Course');b.distance_km=Decimal('5');db.session.commit()
    first=run(a,'5',1800,DAY-timedelta(days=21))
    later=run(a,'5.01',1600,DAY-timedelta(days=7))
    latest=run(a,'5',1500)
    outlier=run(a,'3',500)
    run(b,'5',1000)
    values=[first,later,latest,outlier]
    progress=route_progress(a,values)
    assert progress['change']==300 and progress['best']==latest
    assert progress['excluded']==1
    assert [item.id for item in progress['runs']]==[first.id,later.id,latest.id]
    response=client.get('/gym/runs/progress',query_string={'route_id':a.id})
    assert response.location.endswith(f'/gym/runs/routes/{a.id}')
    page=client.get(response.location)
    assert b'5:00 quicker' in page.data and b'Completion time over time' in page.data
    assert b'Progress by route' in client.get('/gym/runs').data
    client.post(f'/gym/runs/routes/{a.id}/distance',data={'distance_km':'3'})
    assert a.distance_km==3 and latest.distance_km==5
    assert route_progress(a,values)['best']==outlier
    client.post(f'/gym/runs/routes/{a.id}/distance',data={'distance_km':'0'})
    assert a.distance_km==3


def test_new_route_saves_reference_legacy_route_requires_choice(app,client):
    legacy=route()
    entry=run(legacy,'5',1500)
    assert not route_progress(legacy,[entry])['runs']
    fields={'new_route':'Fictional New Course','distance_km':'6.42','duration':'31:18','run_date':DAY.isoformat()}
    client.post('/gym/runs',data=fields)
    fresh=db.session.scalar(select(RunRoute).where(RunRoute.name=='Fictional New Course'))
    assert fresh.distance_km==Decimal('6.42')
    fields.update(distance_km='7',new_route=' fictional   new course ')
    client.post('/gym/runs',data=fields)
    assert fresh.distance_km==Decimal('6.42')


def test_empty_run_history_has_separate_action_and_run_labels(app,client):
    page=client.get('/gym/history?kind=runs').data
    assert b'No runs logged yet' in page and b'Log a run' in page
    page=client.get('/gym/runs').data
    assert b'<span>Route</span>' in page and b'<span>Or a new route</span>' in page
