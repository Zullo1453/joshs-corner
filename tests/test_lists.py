from sqlalchemy import select

from app.extensions import db
from app.models import Checklist, ListItem, ListSection, ListTemplate, ListTemplateItem, ListTemplateSection
from app.search import UniversalSearchService


def test_lists_navigation_order_and_pages(client):
    page = client.get("/lists/")
    assert page.status_code == 200
    body = page.data.decode()
    assert body.index(">Hub<") < body.index(">Exercise<") < body.index(">Lists<") < body.index(">Intelligence<") < body.index(">Search<")
    assert 'href="/lists/"' in body
    assert client.get("/lists/templates").status_code == 200


def test_lists_refined_ui_keeps_clear_buttons_and_auto_growing_fields(client):
    overview = client.get("/lists/").data.decode()
    assert "Create a new list" in overview
    assert "View archived lists" in overview
    assert "✓ My lists" in overview and "▦ Templates" in overview
    css = client.get("/static/css/lists.css").data.decode()
    javascript = client.get("/static/js/lists.js").data.decode()
    assert "resize: none" in css and ".editor-panel[open]" in css
    assert "resizeTextarea" in javascript


def test_list_sections_items_completion_and_template_copy(client, app):
    created = client.post("/lists/", data={"name": "Groceries", "description": "Fresh food"})
    assert created.status_code == 302
    with app.app_context():
        checklist = db.session.scalar(select(Checklist)); list_id = checklist.id
    client.post(f"/lists/{list_id}/sections", data={"name": "Produce"})
    with app.app_context():
        section = db.session.scalar(select(ListSection)); section_id = section.id
    client.post(f"/lists/{list_id}/items", data={"text": "Milk", "detail": "Oat milk", "section_id": section_id})
    with app.app_context():
        item = db.session.scalar(select(ListItem)); item_id = item.id
    response = client.post(f"/lists/{list_id}/items/{item_id}/toggle", headers={"Accept": "application/json"})
    assert response.json["completed"] is True
    client.post(f"/lists/{list_id}/sections/{section_id}/delete", data={"confirm": "yes"})
    with app.app_context():
        item = db.session.get(ListItem, item_id)
        assert item.section_id is None and item.is_completed is True
    client.post(f"/lists/{list_id}/duplicate")
    with app.app_context():
        copied = db.session.scalars(select(Checklist).where(Checklist.name.like("Copy of%"))).one()
        assert copied.is_favorite is False and copied.is_archived is False
        assert copied.items[0].is_completed is False and copied.items[0].detail == "Oat milk"


def test_template_copies_content_without_live_link(client, app):
    response = client.post("/lists/templates", data={"name": "Camping", "description": "Pack carefully"})
    assert response.status_code == 302
    with app.app_context(): template = db.session.scalar(select(ListTemplate)); template_id = template.id
    client.post(f"/lists/templates/{template_id}/sections", data={"name": "Kitchen"})
    with app.app_context(): section = db.session.scalar(select(ListTemplateSection)); section_id = section.id
    client.post(f"/lists/templates/{template_id}/items", data={"text": "Mug", "detail": "Metal", "section_id": section_id})
    page = client.get(f"/lists/templates/{template_id}")
    assert b"Use this template" in page.data and b"Edit section" in page.data and b"Save changes" in page.data
    created = client.post(f"/lists/templates/{template_id}/to-list", data={"name": "Blue Mountains"})
    assert created.status_code == 302
    with app.app_context():
        checklist = db.session.scalar(select(Checklist).where(Checklist.name == "Blue Mountains"))
        assert checklist and checklist.sections[0].name == "Kitchen" and checklist.items[0].detail == "Metal"
    client.post(f"/lists/templates/{template_id}/delete", data={"confirm": "yes"})
    with app.app_context(): assert db.session.get(Checklist, checklist.id) is not None


def test_list_search_routes_item_to_its_list_and_keeps_completed(client, app):
    with app.app_context():
        checklist = Checklist(name="Shopping"); db.session.add(checklist); db.session.flush()
        active = ListItem(checklist_id=checklist.id, text="Milk", detail="Oat milk")
        completed = ListItem(checklist_id=checklist.id, text="Milk powder", is_completed=True)
        db.session.add_all([active, completed]); db.session.commit()
        checklist_id, active_id = checklist.id, active.id
    response = client.post("/search", json={"query": "milk"})
    matches = [result for result in response.json["results"] if result["result_type"] == "List item"]
    assert len(matches) == 2
    assert matches[0]["destination_url"] == f"/lists/{checklist_id}#list-item-{active_id}"
    assert matches[1]["status"] == "Completed"
