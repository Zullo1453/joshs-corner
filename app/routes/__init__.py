from flask import render_template


def section_placeholder(section_name):
    return render_template("section_placeholder.html", section_name=section_name)
