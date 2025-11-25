from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField
from wtforms.validators import DataRequired

class BookForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    authors = StringField("Authors")
    isbn = StringField("ISBN")
    publisher = StringField("Publisher")
    num_pages = IntegerField("Pages")
    stock = IntegerField("Stock", default=1)
    submit = SubmitField("Save")

class MemberForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    email = StringField("Email")
    phone = StringField("Phone")
    submit = SubmitField("Save")

class ImportForm(FlaskForm):
    count = IntegerField("Number of Books", default=20)
    title = StringField("Title Filter")
    authors = StringField("Author Filter")
    submit = SubmitField("Import")
