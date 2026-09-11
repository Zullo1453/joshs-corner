"""Lists and reusable list templates.  These routes deliberately keep every copy independent."""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Checklist, ListItem, ListSection, ListTemplate, ListTemplateItem, ListTemplateSection

lists_bp = Blueprint("lists", __name__, url_prefix="/lists")


def _text(field, limit, required=True):
    value = " ".join(request.form.get(field, "").split())
    if required and not value:
        abort(400, description=f"Enter a {field.replace('_', ' ')}.")
    if len(value) > limit:
        abort(400, description=f"{field.replace('_', ' ').title()} must be at most {limit} characters.")
    return value


def _detail(field="detail"):
    value = request.form.get(field, "").strip()
    if len(value) > 5000:
        abort(400, description="Details must be at most 5000 characters.")
    return value


def _list(list_id):
    item = db.session.scalar(select(Checklist).where(Checklist.id == list_id).options(
        selectinload(Checklist.sections).selectinload(ListSection.items), selectinload(Checklist.items)))
    if item is None:
        abort(404)
    return item


def _template(template_id):
    item = db.session.scalar(select(ListTemplate).where(ListTemplate.id == template_id).options(
        selectinload(ListTemplate.sections).selectinload(ListTemplateSection.items), selectinload(ListTemplate.items)))
    if item is None:
        abort(404)
    return item


def _next(items):
    return max((item.sort_order for item in items), default=-1) + 1


def _move(items, item_id):
    items = sorted(items, key=lambda item: (item.sort_order, item.id))
    index = next((index for index, item in enumerate(items) if item.id == item_id), None)
    action = request.form.get("action", "")
    if index is None or action not in {"up", "down", "top", "bottom"}:
        abort(400, description="Choose a valid move.")
    destination = {"up": index - 1, "down": index + 1, "top": 0, "bottom": len(items) - 1}[action]
    if 0 <= destination < len(items):
        item = items.pop(index)
        items.insert(destination, item)
    for position, item in enumerate(items):
        item.sort_order = position


def _copy_template(template, name):
    checklist = Checklist(name=name, description=template.description)
    db.session.add(checklist)
    db.session.flush()
    section_ids = {}
    for section in sorted(template.sections, key=lambda entry: (entry.sort_order, entry.id)):
        copy = ListSection(checklist_id=checklist.id, name=section.name, sort_order=section.sort_order)
        db.session.add(copy)
        db.session.flush()
        section_ids[section.id] = copy.id
    for item in sorted(template.items, key=lambda entry: (entry.sort_order, entry.id)):
        db.session.add(ListItem(checklist_id=checklist.id, section_id=section_ids.get(item.section_id), text=item.text,
                                detail=item.detail, sort_order=item.sort_order, is_completed=False))
    return checklist


def _copy_list(source, name):
    template = ListTemplate(name=name, description=source.description)
    db.session.add(template)
    db.session.flush()
    ids = {}
    for section in sorted(source.sections, key=lambda entry: (entry.sort_order, entry.id)):
        copy = ListTemplateSection(template_id=template.id, name=section.name, sort_order=section.sort_order)
        db.session.add(copy); db.session.flush(); ids[section.id] = copy.id
    for item in sorted(source.items, key=lambda entry: (entry.sort_order, entry.id)):
        db.session.add(ListTemplateItem(template_id=template.id, section_id=ids.get(item.section_id), text=item.text,
                                        detail=item.detail, sort_order=item.sort_order))
    return template


@lists_bp.get("/")
def index():
    archived = request.args.get("archived") == "1"
    lists = db.session.scalars(select(Checklist).where(Checklist.is_archived == archived).options(selectinload(Checklist.items)).order_by(
        Checklist.is_favorite.desc(), Checklist.sort_order, Checklist.name, Checklist.id)).all()
    templates = db.session.scalars(select(ListTemplate).order_by(ListTemplate.sort_order, ListTemplate.name, ListTemplate.id)).all()
    return render_template("lists/index.html", lists_page="lists", lists=lists, templates=templates, archived=archived)


@lists_bp.post("/")
def create():
    checklist = Checklist(name=_text("name", 200), description=_detail("description"), sort_order=_next(db.session.scalars(select(Checklist)).all()))
    db.session.add(checklist); db.session.commit()
    return redirect(url_for("lists.detail", list_id=checklist.id))


@lists_bp.post("/from-template")
def from_template():
    template = _template(request.form.get("template_id", type=int))
    checklist = _copy_template(template, _text("name", 200, required=False) or template.name)
    db.session.commit(); flash(f"Created an independent copy of {template.name}.", "success")
    return redirect(url_for("lists.detail", list_id=checklist.id))


@lists_bp.get("/<int:list_id>")
def detail(list_id):
    checklist = _list(list_id)
    return render_template("lists/detail.html", lists_page="lists", checklist=checklist)


@lists_bp.post("/<int:list_id>/edit")
def edit(list_id):
    checklist = _list(list_id); checklist.name = _text("name", 200); checklist.description = _detail("description")
    db.session.commit(); return redirect(url_for("lists.detail", list_id=list_id))


@lists_bp.post("/<int:list_id>/favorite")
def favorite(list_id):
    checklist = _list(list_id); checklist.is_favorite = not checklist.is_favorite
    db.session.commit(); return redirect(request.referrer or url_for("lists.detail", list_id=list_id))


@lists_bp.post("/<int:list_id>/archive")
def archive(list_id):
    checklist = _list(list_id); checklist.is_archived = True
    db.session.commit(); flash("List archived. Its items are preserved.", "success")
    return redirect(url_for("lists.index"))


@lists_bp.post("/<int:list_id>/restore")
def restore(list_id):
    checklist = _list(list_id); checklist.is_archived = False
    db.session.commit(); return redirect(url_for("lists.index", archived=1))


@lists_bp.post("/<int:list_id>/delete")
def delete(list_id):
    if request.form.get("confirm") != "yes": abort(400, description="Confirm deletion.")
    db.session.delete(_list(list_id)); db.session.commit(); flash("List deleted.", "success")
    return redirect(url_for("lists.index"))


@lists_bp.post("/<int:list_id>/duplicate")
def duplicate(list_id):
    source = _list(list_id)
    copy = Checklist(name=f"Copy of {source.name}", description=source.description, sort_order=_next(db.session.scalars(select(Checklist)).all()))
    db.session.add(copy); db.session.flush(); section_ids = {}
    for section in source.sections:
        new = ListSection(checklist_id=copy.id, name=section.name, sort_order=section.sort_order); db.session.add(new); db.session.flush(); section_ids[section.id] = new.id
    for item in source.items:
        db.session.add(ListItem(checklist_id=copy.id, section_id=section_ids.get(item.section_id), text=item.text, detail=item.detail, sort_order=item.sort_order))
    db.session.commit(); return redirect(url_for("lists.detail", list_id=copy.id))


@lists_bp.post("/<int:list_id>/sections")
def add_section(list_id):
    checklist = _list(list_id); db.session.add(ListSection(checklist_id=checklist.id, name=_text("name", 160), sort_order=_next(checklist.sections)))
    db.session.commit(); return redirect(url_for("lists.detail", list_id=list_id))


@lists_bp.post("/<int:list_id>/sections/<int:section_id>/edit")
def edit_section(list_id, section_id):
    section = db.get_or_404(ListSection, section_id)
    if section.checklist_id != list_id: abort(404)
    section.name = _text("name", 160); db.session.commit(); return redirect(url_for("lists.detail", list_id=list_id))


@lists_bp.post("/<int:list_id>/sections/<int:section_id>/move")
def move_section(list_id, section_id):
    checklist = _list(list_id); _move(checklist.sections, section_id); db.session.commit(); return redirect(url_for("lists.detail", list_id=list_id))


@lists_bp.post("/<int:list_id>/sections/<int:section_id>/delete")
def delete_section(list_id, section_id):
    checklist = _list(list_id); section = next((entry for entry in checklist.sections if entry.id == section_id), None)
    if section is None: abort(404)
    if request.form.get("confirm") != "yes": abort(400, description="Confirm section deletion.")
    for item in section.items: item.section_id = None
    db.session.delete(section); db.session.commit(); flash("Section removed; its items are now unsectioned.", "success")
    return redirect(url_for("lists.detail", list_id=list_id))


@lists_bp.post("/<int:list_id>/items")
def add_item(list_id):
    checklist = _list(list_id); section_id = request.form.get("section_id", type=int)
    if section_id and not any(section.id == section_id for section in checklist.sections): abort(400)
    siblings = [item for item in checklist.items if item.section_id == section_id and not item.is_completed]
    item = ListItem(checklist_id=list_id, section_id=section_id, text=_text("text", 500), detail=_detail(), sort_order=_next(siblings))
    db.session.add(item); db.session.commit()
    if request.accept_mimetypes.best == "application/json":
        return jsonify(id=item.id, text=item.text, detail=item.detail, section_id=item.section_id)
    return redirect(url_for("lists.detail", list_id=list_id, _anchor=f"list-item-{item.id}"))


def _item_for_list(list_id, item_id):
    item = db.get_or_404(ListItem, item_id)
    if item.checklist_id != list_id: abort(404)
    return item


@lists_bp.post("/<int:list_id>/items/<int:item_id>/edit")
def edit_item(list_id, item_id):
    item = _item_for_list(list_id, item_id); item.text = _text("text", 500); item.detail = _detail()
    db.session.commit(); return redirect(url_for("lists.detail", list_id=list_id, _anchor=f"list-item-{item_id}"))


@lists_bp.post("/<int:list_id>/items/<int:item_id>/toggle")
def toggle_item(list_id, item_id):
    item = _item_for_list(list_id, item_id); item.is_completed = not item.is_completed
    db.session.commit()
    if request.accept_mimetypes.best == "application/json": return jsonify(id=item.id, completed=item.is_completed, section_id=item.section_id)
    return redirect(url_for("lists.detail", list_id=list_id, _anchor=f"list-item-{item_id}"))


@lists_bp.post("/<int:list_id>/items/<int:item_id>/move")
def move_item(list_id, item_id):
    item = _item_for_list(list_id, item_id); checklist = _list(list_id)
    _move([entry for entry in checklist.items if entry.section_id == item.section_id and entry.is_completed == item.is_completed], item.id)
    db.session.commit(); return redirect(url_for("lists.detail", list_id=list_id))


@lists_bp.post("/<int:list_id>/items/<int:item_id>/delete")
def delete_item(list_id, item_id):
    if request.form.get("confirm") != "yes": abort(400, description="Confirm item deletion.")
    db.session.delete(_item_for_list(list_id, item_id)); db.session.commit(); return redirect(url_for("lists.detail", list_id=list_id))


@lists_bp.post("/<int:list_id>/clear-completed")
def clear_completed(list_id):
    if request.form.get("confirm") != "yes": abort(400, description="Confirm completed-item deletion.")
    checklist = _list(list_id)
    for item in [item for item in checklist.items if item.is_completed]: db.session.delete(item)
    db.session.commit(); return redirect(url_for("lists.detail", list_id=list_id))


@lists_bp.post("/<int:list_id>/reset-completed")
def reset_completed(list_id):
    checklist = _list(list_id)
    for item in checklist.items: item.is_completed = False
    db.session.commit(); return redirect(url_for("lists.detail", list_id=list_id))


@lists_bp.post("/<int:list_id>/mark-all")
def mark_all(list_id):
    checklist = _list(list_id)
    for item in checklist.items: item.is_completed = request.form.get("completed") == "yes"
    db.session.commit(); return redirect(url_for("lists.detail", list_id=list_id))


@lists_bp.get("/templates")
def templates():
    return render_template("lists/templates.html", lists_page="templates", templates=db.session.scalars(select(ListTemplate).options(selectinload(ListTemplate.items)).order_by(ListTemplate.sort_order, ListTemplate.name, ListTemplate.id)).all())


@lists_bp.post("/templates")
def create_template():
    template = ListTemplate(name=_text("name", 200), description=_detail("description"), sort_order=_next(db.session.scalars(select(ListTemplate)).all()))
    db.session.add(template); db.session.commit(); return redirect(url_for("lists.template_detail", template_id=template.id))


@lists_bp.get("/templates/<int:template_id>")
def template_detail(template_id):
    return render_template("lists/template_detail.html", lists_page="templates", template=_template(template_id))


@lists_bp.post("/templates/<int:template_id>/edit")
def edit_template(template_id):
    template = _template(template_id); template.name = _text("name", 200); template.description = _detail("description")
    db.session.commit(); return redirect(url_for("lists.template_detail", template_id=template_id))


@lists_bp.post("/templates/<int:template_id>/delete")
def delete_template(template_id):
    if request.form.get("confirm") != "yes": abort(400, description="Confirm template deletion.")
    db.session.delete(_template(template_id)); db.session.commit(); return redirect(url_for("lists.templates"))


@lists_bp.post("/templates/<int:template_id>/sections")
def add_template_section(template_id):
    template = _template(template_id); db.session.add(ListTemplateSection(template_id=template.id, name=_text("name", 160), sort_order=_next(template.sections)))
    db.session.commit(); return redirect(url_for("lists.template_detail", template_id=template_id))


@lists_bp.post("/templates/<int:template_id>/sections/<int:section_id>/edit")
def edit_template_section(template_id, section_id):
    template = _template(template_id); section = next((entry for entry in template.sections if entry.id == section_id), None)
    if section is None: abort(404)
    section.name = _text("name", 160); db.session.commit(); return redirect(url_for("lists.template_detail", template_id=template_id))


@lists_bp.post("/templates/<int:template_id>/sections/<int:section_id>/move")
def move_template_section(template_id, section_id):
    template = _template(template_id); _move(template.sections, section_id); db.session.commit()
    return redirect(url_for("lists.template_detail", template_id=template_id))


@lists_bp.post("/templates/<int:template_id>/sections/<int:section_id>/delete")
def delete_template_section(template_id, section_id):
    template = _template(template_id); section = next((entry for entry in template.sections if entry.id == section_id), None)
    if section is None: abort(404)
    if request.form.get("confirm") != "yes": abort(400, description="Confirm section deletion.")
    for item in section.items: item.section_id = None
    db.session.delete(section); db.session.commit(); flash("Section removed; its template items are unsectioned.", "success")
    return redirect(url_for("lists.template_detail", template_id=template_id))


@lists_bp.post("/templates/<int:template_id>/items")
def add_template_item(template_id):
    template = _template(template_id); section_id = request.form.get("section_id", type=int)
    if section_id and not any(section.id == section_id for section in template.sections): abort(400)
    siblings = [item for item in template.items if item.section_id == section_id]
    db.session.add(ListTemplateItem(template_id=template.id, section_id=section_id, text=_text("text", 500), detail=_detail(), sort_order=_next(siblings)))
    db.session.commit(); return redirect(url_for("lists.template_detail", template_id=template_id))


def _template_item(template_id, item_id):
    item = db.get_or_404(ListTemplateItem, item_id)
    if item.template_id != template_id: abort(404)
    return item


@lists_bp.post("/templates/<int:template_id>/items/<int:item_id>/edit")
def edit_template_item(template_id, item_id):
    item = _template_item(template_id, item_id); item.text = _text("text", 500); item.detail = _detail()
    db.session.commit(); return redirect(url_for("lists.template_detail", template_id=template_id))


@lists_bp.post("/templates/<int:template_id>/items/<int:item_id>/move")
def move_template_item(template_id, item_id):
    item = _template_item(template_id, item_id); template = _template(template_id)
    _move([entry for entry in template.items if entry.section_id == item.section_id], item.id)
    db.session.commit(); return redirect(url_for("lists.template_detail", template_id=template_id))


@lists_bp.post("/templates/<int:template_id>/items/<int:item_id>/delete")
def delete_template_item(template_id, item_id):
    if request.form.get("confirm") != "yes": abort(400, description="Confirm item deletion.")
    db.session.delete(_template_item(template_id, item_id)); db.session.commit()
    return redirect(url_for("lists.template_detail", template_id=template_id))


@lists_bp.post("/templates/<int:template_id>/to-list")
def template_to_list(template_id):
    template = _template(template_id); checklist = _copy_template(template, _text("name", 200, required=False) or template.name)
    db.session.commit(); return redirect(url_for("lists.detail", list_id=checklist.id))
