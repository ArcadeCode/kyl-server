from flask_sqlalchemy import SQLAlchemy

from models.base import Base

# `model_class=Base` makes db.metadata the same metadata object our models
# register their tables on, so `db.create_all()` sees every table.
db = SQLAlchemy(model_class=Base)
